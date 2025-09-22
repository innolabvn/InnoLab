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
async def import_bugs_as_rag(request: BugImportRequest):
    try:
        mongo_manager = get_mongo_manager()
        collection = mongo_manager.collection(FIXER_COLLECTION)
        try:
            collection.create_index("doc_id", unique=True)
        except Exception:
            pass

        imported = []
        for bug in request.bugs:
            content = format_bug_content_for_rag(bug)
            embedding = generate_gemini_embedding(content)
            metadata = create_bug_rag_metadata(bug)
            doc = {
                "content": content,
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

router.post("/search", response_model=SearchResponse)
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

@router.post("/fix")
async def fix_bug(request: BugFixRequest):
    try:
        mongo_manager = get_mongo_manager()
        collection = mongo_manager.collection(FIXER_COLLECTION)
        bug_doc = collection.find_one({"_id": ObjectId(request.bug_id)})
        if not bug_doc:
            raise HTTPException(status_code=404, detail="Bug not found")
        fix_record = {
            "fix_description": request.fix_description,
            "fixed_code": request.fixed_code,
            "fix_notes": request.fix_notes,
            "fixed_at": datetime.utcnow(),
        }
        update_data = {
            "$set": {
                "metadata.status": "FIXED",
                "metadata.fix_record": fix_record,
                "updated_at": datetime.utcnow(),
            }
        }
        if request.fixed_code:
            fix_content = f"FIX APPLIED:\nDescription: {request.fix_description}\nFixed Code: {request.fixed_code}"
            update_data["$set"]["content"] = bug_doc["content"] + fix_content
            new_embedding = generate_gemini_embedding(update_data["$set"]["content"])
            update_data["$set"]["embedding"] = new_embedding
        result = collection.update_one({"_id": ObjectId(request.bug_id)}, update_data)
        if result.modified_count == 0:
            raise HTTPException(status_code=500, detail="Failed to update bug")
        return {"message": "Bug fixed successfully", "bug_id": request.bug_id, "fix_record": fix_record, "status": "FIXED"}
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=500, detail=f"Error fixing bug: {str(e)}")

@router.post("/suggest-fix")
async def suggest_bug_fix(request: BugFixSuggestionRequest):
    try:
        mongo_manager = get_mongo_manager()
        collection = mongo_manager.collection(FIXER_COLLECTION)
        bug_doc = collection.find_one({"_id": ObjectId(request.bug_id)})
        if not bug_doc:
            raise HTTPException(status_code=404, detail="Bug not found")
        bug_content = bug_doc["content"]
        similar_fixes = []
        if request.include_similar_fixes:
            search_filter = {
                "metadata.status": "FIXED",
                "metadata.bug_type": bug_doc.get("metadata", {}).get("bug_type"),
                "_id": {"$ne": ObjectId(request.bug_id)},
            }
            similar_bugs = list(collection.find(search_filter).limit(3))
            for sb in similar_bugs:
                if "fix_record" in sb.get("metadata", {}):
                    similar_fixes.append({
                        "bug_name": sb["metadata"].get("bug_name"),
                        "fix_description": sb["metadata"]["fix_record"].get("fix_description"),
                        "fixed_code": sb["metadata"]["fix_record"].get("fixed_code"),
                    })
        prompt = f"""
Analyze the following bug and provide fix suggestions:

BUG INFORMATION:
{bug_content}
"""
        if similar_fixes:
            prompt += "\nSIMILAR FIXES FOR REFERENCE: "
            for i, fx in enumerate(similar_fixes, 1):
                prompt += f"\n{i}. {fx['bug_name']}\n   Fix: {fx['fix_description']}\n"
                if fx['fixed_code']:
                    prompt += f"   Code: {fx['fixed_code']}\n"
        prompt += """
Please provide:
1. Root cause analysis
2. Recommended fix approach
3. Code suggestions (if applicable)
4. Risks/considerations
5. Testing recommendations
"""
        response = client.models.generate_content(model=GENERATION_MODEL, contents=prompt)
        return {
            "bug_id": request.bug_id,
            "bug_content": bug_content,
            "ai_suggestion": response.text,
            "similar_fixes": similar_fixes,
            "generated_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=500, detail=f"Error generating fix suggestion: {str(e)}")