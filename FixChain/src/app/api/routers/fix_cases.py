# src/app/api/routers/fix_cases.py
"""
Import case, vector search, mark FIXED, suggest-fix, stats
"""
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from bson import ObjectId
from src.app.adapters.llm.google_genai import client, EMBEDDING_MODEL, GENERATION_MODEL
from src.app.repositories.mongo import get_mongo_manager

root_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))), '.env')
load_dotenv(root_env_path)

router = APIRouter()

class BugRAGItem(BaseModel):
    name: str
    description: str
    type: str = "BUG"
    severity: str = "MEDIUM"
    status: str = "OPEN"
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    code_snippet: Optional[str] = None
    labels: List[str] = Field(default_factory=list)
    project: Optional[str] = None
    component: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class BugRAGImportRequest(BaseModel):
    bugs: List[BugRAGItem]
    collection_name: str = "bug_rag_documents"
    generate_embeddings: bool = True

class BugFixRequest(BaseModel):
    bug_id: str
    fix_description: str
    fixed_code: Optional[str] = None
    fix_type: str = "MANUAL"
    fixed_by: Optional[str] = None
    fix_notes: Optional[str] = None

class BugSearchRequest(BaseModel):
    query: str
    collection_name: str = "bug_rag_documents"
    top_k: int = 5
    filters: Dict[str, Any] = Field(default_factory=dict)

class BugFixSuggestionRequest(BaseModel):
    bug_id: str
    collection_name: str = "bug_rag_documents"
    include_similar_fixes: bool = True

def generate_gemini_embedding(text: str) -> List[float]:
    try:
        r = client.models.embed_content(model=EMBEDDING_MODEL, contents=text)
        return r.embeddings[0].values
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return [0.0] * 768  # 768-dim embedding

def format_bug_for_rag(bug: BugRAGItem) -> str:
    parts = [
        f"Bug Name: {bug.name}",
        f"Description: {bug.description}",
        f"Type: {bug.type}",
        f"Severity: {bug.severity}",
        f"Status: {bug.status}",
    ]
    if bug.file_path: parts.append(f"File: {bug.file_path}")
    if bug.line_number: parts.append(f"Line: {bug.line_number}")
    if bug.code_snippet: parts.append(f"Code Snippet:\n{bug.code_snippet}")
    if bug.labels: parts.append(f"Labels: {', '.join(bug.labels)}")
    if bug.project: parts.append(f"Project: {bug.project}")
    if bug.component: parts.append(f"Component: {bug.component}")
    return "\n".join(parts)

def create_bug_rag_metadata(bug: BugRAGItem) -> Dict[str, Any]:
    md = {
      "bug_name": bug.name,
      "bug_type": bug.type,
      "severity": bug.severity,
      "status": bug.status,
      "labels": bug.labels,
      "created_at": datetime.utcnow(),
      "document_type": "bug_rag",
    }
    if bug.file_path: md["file_path"] = bug.file_path
    if bug.line_number: md["line_number"] = bug.line_number
    if bug.project: md["project"] = bug.project
    if bug.component: md["component"] = bug.component
    md.update(bug.metadata)
    return md

def convert_objectid_to_str(obj):
    if isinstance(obj, ObjectId): return str(obj)
    if isinstance(obj, datetime): return obj.isoformat()
    if isinstance(obj, dict): return {k: convert_objectid_to_str(v) for k, v in obj.items()}
    if isinstance(obj, list): return [convert_objectid_to_str(i) for i in obj]
    return obj

@router.post("/import")
async def import_bugs_as_rag(request: BugRAGImportRequest):
    try:
        mongo_manager = get_mongo_manager()
        collection = mongo_manager.get_collection(request.collection_name)
        imported = []
        for bug in request.bugs:
            content = format_bug_for_rag(bug)[:4000]
            embedding = generate_gemini_embedding(content) if request.generate_embeddings else None
            metadata = create_bug_rag_metadata(bug)
            doc = {
                "content": content,
                "metadata": metadata,
                "embedding": embedding,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
            result = collection.insert_one(doc)
            imported.append({"bug_id": str(result.inserted_id), "bug_name": bug.name, "status": "imported"})
        return {
            "message": f"Successfully imported {len(imported)} bugs as RAG documents",
            "collection": request.collection_name,
            "imported_bugs": imported,
            "total_imported": len(imported),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error importing bugs: {str(e)}")

@router.post("/search")
async def search_bugs_in_rag(request: BugSearchRequest):
    try:
        mongo_manager = get_mongo_manager()
        collection = mongo_manager.get_collection(request.collection_name)
        query_embedding = generate_gemini_embedding(request.query)
        pipeline = [
            {
                "$vectorSearch": {
                    "index": "vector_index",
                    "path": "embedding",
                    "queryVector": query_embedding,
                    "numCandidates": request.top_k * 20,
                    "limit": request.top_k
                }
            },
            { "$set": { "similarity_score": { "$meta": "searchScore" } } }
        ]
        if request.filters:
            match_stage = {"$match": {}}
            for k, v in request.filters.items():
                match_stage["$match"][f"metadata.{k}"] = v
            pipeline.append(match_stage)
        docs = list(collection.aggregate(pipeline))
        # Chuẩn hoá field 'similarity_score' để các router khác dùng chung
        for d in docs:
            if "similarity" in d and "similarity_score" not in d:
                d["similarity_score"] = d["similarity"]
        results = convert_objectid_to_str(docs)
        return {"query": request.query, "results": results, "total_found": len(results), "collection": request.collection_name}
    except Exception:
        # fallback text search
        try:
            mongo_manager = get_mongo_manager()
            collection = mongo_manager.get_collection(request.collection_name)
            search_filter = {"$or": [
                {"content": {"$regex": request.query, "$options": "i"}},
                {"metadata.bug_name": {"$regex": request.query, "$options": "i"}},
                {"metadata.description": {"$regex": request.query, "$options": "i"}},
            ]}
            for k, v in request.filters.items():
                search_filter[f"metadata.{k}"] = v
            results = list(collection.find(search_filter).limit(request.top_k))
            results = convert_objectid_to_str(results)
            return {"query": request.query, "results": results, "total_found": len(results), "collection": request.collection_name, "search_type": "text_fallback"}
        except Exception as fallback_error:
            raise HTTPException(status_code=500, detail=f"Error searching bugs: {str(fallback_error)}")

@router.post("/fix")
async def fix_bug(request: BugFixRequest):
    try:
        mongo_manager = get_mongo_manager()
        collection = mongo_manager.get_collection("bug_rag_documents")
        bug_doc = collection.find_one({"_id": ObjectId(request.bug_id)})
        if not bug_doc:
            raise HTTPException(status_code=404, detail="Bug not found")
        fix_record = {
            "fix_description": request.fix_description,
            "fixed_code": request.fixed_code,
            "fix_type": request.fix_type,
            "fixed_by": request.fixed_by,
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
            fix_content = f"\n\nFIX APPLIED:\nDescription: {request.fix_description}\nFixed Code:\n{request.fixed_code}"
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
        collection = mongo_manager.get_collection(request.collection_name)
        bug_doc = collection.find_one({"_id": ObjectId(request.bug_id)})
        if not bug_doc:
            raise HTTPException(status_code=404, detail="Bug not found")
        bug_content = bug_doc["content"]
        similar_fixes = []
        if request.include_similar_fixes:
            search_filter = {"metadata.status": "FIXED", "metadata.bug_type": bug_doc["metadata"].get("bug_type"), "_id": {"$ne": ObjectId(request.bug_id)}}
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
            prompt += "\nSIMILAR FIXES FOR REFERENCE:\n"
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

@router.get("/stats")
async def get_rag_bug_stats():
    try:
        mongo_manager = get_mongo_manager()
        collection = mongo_manager.get_collection("bug_rag_documents")
        total_bugs = collection.count_documents({})
        status_stats = list(collection.aggregate([{"$group": {"_id": "$metadata.status", "count": {"$sum": 1}}}]))
        type_stats = list(collection.aggregate([{"$group": {"_id": "$metadata.bug_type", "count": {"$sum": 1}}}]))
        severity_stats = list(collection.aggregate([{"$group": {"_id": "$metadata.severity", "count": {"$sum": 1}}}]))
        return {
            "total_bugs": total_bugs,
            "by_status": {s["_id"]: s["count"] for s in status_stats},
            "by_type": {s["_id"]: s["count"] for s in type_stats},
            "by_severity": {s["_id"]: s["count"] for s in severity_stats},
            "collection": "bug_rag_documents",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting stats: {str(e)}")

@router.get("/health")
async def health_check():
    try:
        mongo_manager = get_mongo_manager()
        mongo_manager.client.admin.command("ping")
        return {"status": "healthy", "mongodb": "connected", "gemini": "configured", "timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e), "timestamp": datetime.utcnow().isoformat()}
