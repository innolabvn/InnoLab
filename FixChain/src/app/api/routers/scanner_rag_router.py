from pathlib import Path
import uuid
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Dict, Any
import os
from pymongo.errors import BulkWriteError
from pymongo import UpdateOne
from src.app.repositories.mongo import get_mongo_manager
from src.app.repositories.mongo_utlis import ensure_collection
from src.app.adapters.llm.google_genai import client, EMBEDDING_MODEL

root_env_path = Path(__file__).resolve().parents[4] / '.env'
load_dotenv(root_env_path)

router = APIRouter()
SCANNER_COLLECTION = os.getenv("SCANNER_RAG_COLLECTION", "scanner_rag_collection")

class ScannerSignalIn(BaseModel):
    key: str
    id: Optional[str] = None
    title: str = Field("", max_length=200)
    description: str = Field("", max_length=4000)
    code_snippet: str = Field("", max_length=8000)
    file_name: Optional[str] = None
    line_number: Optional[int] = None
    severity: Optional[Literal["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]] = None
    tags: Optional[List[str]] = None
    source: Optional[str] = "bearer"

class ScannerUpdatePatch(BaseModel):
    id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    code_snippet: Optional[str] = None
    file_name: Optional[str] = None
    line_number: Optional[int] = None
    severity: Optional[Literal["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]] = None
    tags: Optional[List[str]] = None
    source: Optional[str] = None
    # Dify fields
    dify_bug_id: Optional[str] = None
    dify_classification: Optional[str] = None
    dify_label: Optional[str] = None
    dify_reason: Optional[str] = None

class ScannerSearchRequest(BaseModel):
    query: str
    limit: int = 5
    filters: Dict[str, Any] = {}

class ScannerSearchResponse(BaseModel):
    query: str
    sources: List[Dict[str, Any]]

class ScannerUpsertItem(BaseModel):
    key: str = Field(..., description="Unique key for idempotent upsert (e.g., <repo>:<file>:<line> or a hash)")
    text: str = Field(..., max_length=5000)
    label: Literal["BUG", "CODE_SMELL"]
    severity: Literal["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
    id: Optional[str] = None
    source: str
    extra: Dict[str, Any] = Field(default_factory=dict, description="Optional extra metadata (file_name, line_number, tags, etc.)")

class ScannerUpsertRequest(BaseModel):
    signals: List[ScannerSignalIn]

class ScannerUpdateRequest(BaseModel):
    key: str
    patch: ScannerUpdatePatch

def _compose_content(it: Dict[str, Any]) -> str:
    """Ghép nội dung để embed từ shape B (không nhận shape A)."""
    title = (it.get("title") or "").strip()
    desc = (it.get("description") or "").strip()
    code = (it.get("code_snippet") or "").strip()
    loc = ""
    if it.get("file_name"):
        loc = f"{it.get('file_name')}:{it.get('line_number')}" if it.get("line_number") is not None else it.get("file_name")
    parts = [p for p in (title, desc, loc, code) if p]
    return "\n".join(parts)[:16000]  # giới hạn an toàn

def _embed_text(text: str) -> List[float]:
    embedding = client.models.embed_content(model=EMBEDDING_MODEL, contents=text)
    r_embeddings = getattr(embedding, "embeddings", None)
    if not r_embeddings or not r_embeddings[0]:
        raise RuntimeError("No embeddings returned from Gemini API")
    return r_embeddings[0].values

@router.get("/health")
async def health():
    """
    Kiểm tra & tự tạo collection cho Scanner RAG nếu chưa có.
    """
    result = ensure_collection(
        SCANNER_COLLECTION,
        # Index gợi ý cho dữ liệu scan
        indexes=[
            {"keys": [("scan_id", 1)], "name": "idx_scan_id", "unique": False},
            {"keys": [("severity", 1), ("created_at", 1)], "name": "idx_severity_created", "unique": False},
        ],
    )
    return {
        "service": "scanner_rag_router",
        **result
    }

@router.post("/import")
def import_signals(items: List[ScannerSignalIn]):
    if not items:
        return {"success": True, "inserted": 0, "ids": []}
    mm = get_mongo_manager()
    col = mm.collection(SCANNER_COLLECTION)
    docs = []
    ids = []

    for it in items:
        d = it.dict()
        content = _compose_content(d)
        if not content:
            continue
        emb = _embed_text(content)
        doc = {
            "key": it.key,
            "content": content,
            "embedding": emb,
            "embedding_dimension": len(emb),
            "metadata": {
                "id": it.id,
                "title": it.title,
                "description": it.description,
                "code_snippet": it.code_snippet,
                "file_name": it.file_name,
                "line_number": it.line_number,
                "severity": it.severity,
                "tags": it.tags or [],
                "source": it.source or "bearer",
            }
        }

        doc_id = (doc.get("key") or str(uuid.uuid4()))
        doc["doc_id"] = str(doc_id)
        docs.append(
            UpdateOne(
                {"doc_id": doc["doc_id"]},
                {"$set": doc},
                upsert=True
            )
        )
        ids.append(doc["doc_id"])

    if not docs:
        return {"success": True, "inserted": 0, "ids": []}
    
    try:
        res = col.bulk_write(docs, ordered=False)
        inserted = (res.upserted_count or 0) + (res.inserted_count or 0)
        return {"success": True, "inserted": inserted, "ids": ids}
    except BulkWriteError as e:
        return {"success": False, "error": "BulkWriteError", "details": e.details}

@router.post("/update")
def update_scanner_signal(req: ScannerUpdateRequest):
    """
    Cập nhật 1 signal theo key. Nếu patch có 'text'/'content', sẽ re-embed tự động.
    """
    mm = get_mongo_manager()
    col = mm.collection(SCANNER_COLLECTION)

    existing = col.find_one({"key": req.key})
    if not existing:
        raise HTTPException(status_code=404, detail=f"Signal not found for key={req.key}")
    
    meta = existing.get("metadata", {}) or {}
    merged = {
        "title": req.patch.title if req.patch.title is not None else meta.get("title", ""),
        "description": req.patch.description if req.patch.description is not None else meta.get("description", ""),
        "code_snippet": req.patch.code_snippet if req.patch.code_snippet is not None else meta.get("code_snippet", ""),
        "file_name": req.patch.file_name if req.patch.file_name is not None else meta.get("file_name"),
        "line_number": req.patch.line_number if req.patch.line_number is not None else meta.get("line_number"),
    }

    must_reembed = any(
        v is not None for v in (req.patch.title, req.patch.description, req.patch.code_snippet, req.patch.file_name, req.patch.line_number)
    )

    update_set: Dict[str, Any] = {}

    # cập nhật metadata phẳng
    for f in ["id", "title", "description", "code_snippet", "file_name", "line_number", "severity", "source"]:
        val = getattr(req.patch, f, None)
        if val is not None:
            update_set[f"metadata.{f}"] = val
    if req.patch.tags is not None:
        update_set["metadata.tags"] = req.patch.tags

    # Dify fields
    for f in ["dify_bug_id", "dify_label", "dify_classification", "dify_reason"]:
        val = getattr(req.patch, f, None)
        if val is not None:
            update_set[f"{f}"] = val

    # nếu có thay đổi thành phần content -> re-embed
    if must_reembed:
        new_content = _compose_content(merged)
        emb = _embed_text(new_content)
        update_set["content"] = new_content
        update_set["embedding"] = emb
        update_set["embedding_dimension"] = len(emb)

    res = col.update_one({"key": req.key}, {"$set": update_set})
    return {"success": True, "matched": res.matched_count, "modified": res.modified_count}

@router.post("/upsert")
def upsert_scanner_signals(body: ScannerUpsertRequest):
    """
    Bulk upsert theo key. Idempotent.
    - Nếu chưa có: insert với created_at.
    - Nếu đã có: update content/metadata/embedding + updated_at.
    """
    if not body.signals:
        return {"success": True, "upserted": 0, "modified": 0}

    mm = get_mongo_manager()
    col = mm.collection(SCANNER_COLLECTION)

    ops: List[UpdateOne] = []

    for it in body.signals:
        d = it.dict()
        content = _compose_content(d)
        if not content:
            # bỏ qua record trống
            continue
        emb = _embed_text(content)
        doc = {
            "key": it.key,
            "content": content,
            "embedding": emb,
            "embedding_dimension": len(emb),
            "metadata": {
                "id": it.id,
                "title": it.title,
                "description": it.description,
                "code_snippet": it.code_snippet,
                "file_name": it.file_name,
                "line_number": it.line_number,
                "severity": it.severity,
                "tags": it.tags or [],
                "source": it.source or "bearer",
            },
        }
        ops.append(
            UpdateOne(
                {"key": it.key},
                {"$set": doc, "$setOnInsert": {}},
                upsert=True,
            )
        )

    if not ops:
        return {"success": True, "upserted": 0, "modified": 0}

    res = col.bulk_write(ops, ordered=False)
    return {
        "success": True,
        "upserted": int(res.upserted_count or 0),
        "modified": int(res.modified_count or 0),
    }

@router.post("/search", response_model=ScannerSearchResponse)
async def search_scanner(req: ScannerSearchRequest):
    try:
        mm = get_mongo_manager()
        q_emb = _embed_text(req.query)
        results = mm.search_by_embedding(
            query_embedding=q_emb,
            top_k=int(req.limit),
            collection_name=SCANNER_COLLECTION,
            filters=req.filters or {},
        )
        return {"query": req.query, "sources": results or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during scanner search: {str(e)}")