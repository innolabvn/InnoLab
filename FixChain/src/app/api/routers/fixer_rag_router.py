# src/app/api/routers/fix_cases.py
"""
Fixer RAG router
- /health
- /import
- /search
- /fix
- /suggest-fix
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from src.app.adapters.llm.google_genai import client, EMBEDDING_MODEL
from src.app.repositories.mongo import get_mongo_manager
from src.app.repositories.mongo_utlis import ensure_collection
from src.app.services.log_service import logger

root_env_path = Path(__file__).resolve().parents[4] / '.env'
load_dotenv(root_env_path)

FIXER_COLLECTION = os.getenv("FIXER_RAG_COLLECTION", "fixer_rag_collection")

class BugSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    filters: Dict[str, Any] = {}

class SearchResponse(BaseModel):
    query: str
    sources: List[Dict[str, Any]]

def generate_gemini_embedding(text: str) -> List[float]:
    res = client.models.embed_content(model=EMBEDDING_MODEL, contents=text)
    res_embeddings = getattr(res, "embeddings", None)
    if not res_embeddings or not res_embeddings[0]:
        logger.warning("Empty embedding received, returning zero vector")
        return [0.0] * 768
    else:
        return res_embeddings[0].values

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
async def import_bugs_as_rag(bugs: List[Dict[str, Any]]):
    try:
        mongo_manager = get_mongo_manager()
        collection = mongo_manager.collection(FIXER_COLLECTION)
        try:
            collection.create_index("doc_id", unique=True)
        except Exception:
            pass

        imported: List[Dict[str, Any]] = []
        for idx, bug in enumerate(bugs):
            if not isinstance(bug, dict):
                raise ValueError("Each bug item must be a JSON object")
            doc_id = bug.get("doc_id")
            if not doc_id:
                raise ValueError("Missing 'doc_id' in bug item")
            
            logger.debug("Import #%d: doc_id=%s", idx, doc_id)
            meta = bug.get("metadata") or {}
            if not isinstance(meta, dict):
                meta = {}
            emb_text = json.dumps(bug, ensure_ascii=False)
            try:
                embedding = generate_gemini_embedding(emb_text)
            except Exception as e:
                logger.warning("Embedding failed for %s: %s; fallback empty embedding", doc_id, e)
                embedding = []

            doc = {
                "content": bug,
                "metadata": meta,
                "embedding": embedding,
            }

            result = collection.update_one({"doc_id": doc_id}, {"$set": doc}, upsert=True)

            status = "inserted" if result.upserted_id is not None else ("updated" if result.modified_count else "unchanged")
            imported.append({"bug_id": doc_id, "status": status})
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