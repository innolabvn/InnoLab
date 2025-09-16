from pathlib import Path
from dotenv import load_dotenv
from fastapi import APIRouter, Request, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Dict, Any
import os
from datetime import datetime
from src.app.repositories.mongo import get_mongo_manager
from src.app.repositories.mongo_utlis import ensure_collection
from src.app.adapters.llm.google_genai import client, EMBEDDING_MODEL

root_env_path = Path(__file__).resolve().parents[5] / '.env'
load_dotenv(root_env_path)

router = APIRouter()
SCANNER_COLLECTION = os.getenv("SCANNER_RAG_COLLECTION", "scanner_rag_collection")

class ScannerResult(BaseModel):
    text: str = Field(..., max_length=1000)
    label: Literal["BUG", "CODE_SMELL"]
    severity: Literal["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
    id: Optional[str] = None
    lang: Optional[str] = None
    source: str

class ScannerSearchRequest(BaseModel):
    query: str
    limit: int = 5
    filters: Dict[str, Any] = {}

class ScannerSearchResponse(BaseModel):
    query: str
    sources: List[Dict[str, Any]]

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
def import_signals(items: List[ScannerResult]):
    mm = get_mongo_manager()
    col = mm.get_collection(SCANNER_COLLECTION)
    docs = []

    for it in items:
        embedding = client.models.embed_content(model=EMBEDDING_MODEL, contents=it.text)
        r_embeddings = getattr(embedding, "embeddings", None)
        if not r_embeddings or not r_embeddings[0]:
            raise RuntimeError("No embeddings returned from Gemini API")
        docs.append({
            "content": it.text,
            "metadata": {
                "kind": "scanner",
                "label": it.label,
                "severity": it.severity,
                "id": it.id,
                "lang": it.lang,
                "source": it.source,
                "created_at": datetime.utcnow()
            },
            "embedding": r_embeddings[0].values
        })
    r = col.insert_many(docs)
    return {"success": True, "inserted": len(r.inserted_ids), "ids": [str(x) for x in r.inserted_ids]}

@router.post("/search", response_model=ScannerSearchResponse)
async def search_scanner(req: ScannerSearchRequest):
    try:
        mm = get_mongo_manager()
        emb = client.models.embed_content(model=EMBEDDING_MODEL, contents=req.query)
        r_embeddings = getattr(emb, "embeddings", None)
        if not r_embeddings or not r_embeddings[0]:
            raise RuntimeError("No embeddings returned from Gemini API")
        results = mm.search_by_embedding(
            query_embedding=r_embeddings[0].values,
            top_k=int(req.limit),
            collection_name=SCANNER_COLLECTION,
            filters=req.filters or {},
        )
        return {"query": req.query, "sources": results or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during scanner search: {str(e)}")