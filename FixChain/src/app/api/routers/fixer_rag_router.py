# src/app/api/routers/fix_cases.py
"""
Fixer RAG router
- /health
- /import
- /search
- /fix
- /suggest-fix
"""
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Literal, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from bson import ObjectId
from src.app.adapters.llm.google_genai import client, EMBEDDING_MODEL, GENERATION_MODEL
from src.app.repositories.mongo import get_mongo_manager
from src.app.repositories.mongo_utlis import ensure_collection
from src.app.services.log_service import logger

root_env_path = Path(__file__).resolve().parents[4] / '.env'
load_dotenv(root_env_path)

FIXER_COLLECTION = os.getenv("FIXER_RAG_COLLECTION", "fixer_rag_collection")

class BugItem(BaseModel):
    key: str
    label: Literal["BUG", "CODE_SMELL"]
    id: str
    reason: str
    title: str
    lang: str
    severity: str
    line_number: str
    file_name: str
    code_snippet: str
    metadata: Dict[str, Any]

class BugImportRequest(BaseModel):
    bugs: List[BugItem]

class BugFixRequest(BaseModel):
    bug_id: str
    fix_description: str
    fixed_code: Optional[str] = None
    fix_notes: Optional[str] = None

class BugSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    filters: Dict[str, Any] = {}

class SearchResponse(BaseModel):
    query: str
    sources: List[Dict[str, Any]]

class BugFixSuggestionRequest(BaseModel):
    bug_id: str
    collection_name: str = FIXER_COLLECTION
    include_similar_fixes: bool = True

def generate_gemini_embedding(text: str) -> List[float]:
    res = client.models.embed_content(model=EMBEDDING_MODEL, contents=text)
    res_embeddings = getattr(res, "embeddings", None)
    if not res_embeddings or not res_embeddings[0]:
        logger.warning("Empty embedding received, returning zero vector")
        return [0.0] * 768
    else:
        return res_embeddings[0].values

def format_bug_content_for_rag(bug: BugItem) -> str:
    parts = [
        f"ID: {bug.id}",
        f"\nTitle: {bug.title}",
        f"\nLang: {bug.lang}",
        f"\nReason: {bug.reason}"
    ]
    return "".join(parts)

def create_bug_rag_metadata(bug: BugItem) -> Dict[str, Any]:
    md = {
        "severity": {bug.severity},
        "file_name": {bug.file_name},
        "line_number": {bug.line_number},
        "code_snippet": {bug.code_snippet}
    }
    md.update(bug.metadata or {})
    return md

router = APIRouter()
@router.get("/health")
async def health_check():
    """
    Kiểm tra & tự tạo collection cho Fixer RAG nếu chưa có.
    """
    result = ensure_collection(
            FIXER_COLLECTION,
            # Có thể bổ sung index đặc thù cho Fixer ở đây
            indexes=[
                {"keys": [("bug_id", 1)], "name": "idx_bug_id", "unique": False},
                {"keys": [("file_path", 1), ("line", 1)], "name": "idx_file_line", "unique": False},
            ],
        )
    return {"service": "fixer_rag_router", **result}

@router.post("/import")
async def import_bugs_as_rag(request: Any):
    try:
        mongo_manager = get_mongo_manager()
        collection = mongo_manager.collection(FIXER_COLLECTION)
        try:
            collection.create_index("doc_id", unique=True)
        except Exception:
            pass

        imported = []
        for bug in request:
            logger.debug(bug)
            embedding = generate_gemini_embedding(bug)
            metadata = create_bug_rag_metadata(bug)
            doc = {
                "content": bug,
                "metadata": metadata,
                "embedding": embedding,
            }
            result = collection.update_one(
                {"doc_id": bug.key},
                {
                    "$set": doc,
                },
                upsert=True,
            )
            status = "inserted" if result.upserted_id is not None else ("updated" if result.modified_count else "unchanged")
            imported.append({"bug_id": bug.key, "status": status})
        return {
            "imported_bugs": imported,
            "message": f"Successfully imported {len(imported)} bugs as RAG documents",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error importing bugs: {str(e)}")

@router.post("/search", response_model=SearchResponse)
async def search_fixers(req: BugSearchRequest):
    try:
        mongo_manager = get_mongo_manager()
        emb = generate_gemini_embedding(req.query)
        results = mongo_manager.search_by_embedding(
            query_embedding=emb,
            top_k=int(req.top_k),
            collection_name=FIXER_COLLECTION,
            filters=req.filters or {},
        )
        return {"query": req.query, "sources": results or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during fixer search: {str(e)}")