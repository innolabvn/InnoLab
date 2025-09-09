# src/app/api/routers/knowledge.py
"""
Thêm doc, semantic search, stats, delete
"""
import os
from typing import List, Dict, Any, Union, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from src.app.adapters.llm.google_genai import client, EMBEDDING_MODEL, GENERATION_MODEL
from src.app.repositories.mongo import MongoDBManager

root_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))), '.env')
load_dotenv(root_env_path)

# Lazy resources
embedding_model = None
llm_model = None
mongo_manager: Optional[MongoDBManager] = None

def ensure_inited():
    global embedding_model, llm_model, mongo_manager
    if mongo_manager is None:
        mongo_manager = MongoDBManager()

router = APIRouter()

class DocumentInput(BaseModel):
    content: str = Field(..., min_length=10, description="Document cần thêm vào knowledge base")
    metadata: Dict[str, Any] = Field(default={})

class SearchInput(BaseModel):
    query: Union[str, List[str]]
    limit: int = Field(default=5, ge=1, le=20)
    combine_mode: str = Field(default="OR", pattern="^(OR|AND)$")

class SearchResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]]
    query: str

async def get_gemini_embedding(text: str) -> List[float]:
    ensure_inited()
    try:
        res = client.models.embed_content(model=EMBEDDING_MODEL, contents=text)
        return res.embeddings[0].values
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating embedding: {str(e)}")

async def generate_answer_with_gemini(query: str, context_docs: List[Dict]) -> str:
    try:
        context = "\n\n".join([f"Document {i+1}: {doc.get('content','')}" for i, doc in enumerate(context_docs)])
        prompt = f"""
Bạn là AI assistant. Dựa trên thông tin dưới đây, trả lời chính xác, tiếng Việt.
Thông tin:
{context}

Câu hỏi: {query}

Nếu không đủ dữ liệu, hãy nói không đủ thông tin.
"""
        resp = client.models.generate_content(model=GENERATION_MODEL, contents=prompt)
        return resp.text
    except Exception as e:
        return f"Error generating answer: {str(e)}"

@router.get("/")
async def root():
    return {
        "message": "Knowledge base with MongoDB & Gemini Flash 2.0 is running!",
        "version": "2.0.0",
        "features": [
            "MongoDB document storage",
            "Gemini embeddings",
            "Gemini generation",
            "Semantic search",
        ],
        "endpoints": {"add_document": "POST /add", "search": "POST /search", "stats": "GET /stats"},
    }

@router.get("/health")
async def health_check():
    ensure_inited()
    try:
        mongo_manager.client.admin.command("ping")
        return {"status": "healthy", "database": "connected", "ai_model": "gemini-2.0-flash-exp"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

@router.post("/add")
async def add_document(doc_input: DocumentInput):
    ensure_inited()
    try:
        emb = await get_gemini_embedding(doc_input.content[:4000])
        doc_id = mongo_manager.add_document(content=doc_input.content, embedding=emb, metadata=doc_input.metadata)
        return {"message": "Document added successfully", "document_id": str(doc_id), "content_length": len(doc_input.content), "embedding_model": "gemini-2.0-flash-exp"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding document: {str(e)}")

@router.post("/search", response_model=SearchResponse)
async def search_documents(search_input: SearchInput):
    ensure_inited()
    try:
        if isinstance(search_input.query, str):
            query_text = search_input.query
            emb = await get_gemini_embedding(query_text)
            results = mongo_manager.search_by_embedding(query_embedding=emb, top_k=search_input.limit)
        else:
            query_text = " ".join(search_input.query)
            all_results = []
            for q in search_input.query:
                emb = await get_gemini_embedding(q)
                all_results.extend(mongo_manager.search_by_embedding(query_embedding=emb, top_k=search_input.limit))
            if search_input.combine_mode.upper() == "AND":
                counts = {}
                for doc in all_results:
                    doc_id = doc.get("_id", str(doc))
                    if doc_id not in counts:
                        counts[doc_id] = {"count": 0, "doc": doc, "total_score": 0}
                    counts[doc_id]["count"] += 1
                    counts[doc_id]["total_score"] += doc.get("similarity_score", 0)
                num_q = len(search_input.query)
                results = [{**v["doc"], "similarity_score": v["total_score"]/v["count"]} for v in counts.values() if v["count"] == num_q]
            else:
                seen, results = set(), []
                for doc in all_results:
                    doc_id = doc.get("_id", str(doc))
                    if doc_id not in seen:
                        seen.add(doc_id)
                        results.append(doc)
            results = sorted(results, key=lambda x: x.get("similarity_score", 0), reverse=True)[:search_input.limit]

        if not results:
            return SearchResponse(answer="Xin lỗi, tôi không tìm thấy thông tin liên quan.", sources=[], query=query_text)

        answer = await generate_answer_with_gemini(query_text, results)
        sources = [{
            "content": d["content"][:200] + "..." if len(d["content"]) > 200 else d["content"],
            "metadata": d.get("metadata", {}),
            "similarity_score": d.get("similarity_score", 0),
        } for d in results]
        return SearchResponse(answer=answer, sources=sources, query=query_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during search: {str(e)}")

@router.get("/stats")
async def get_stats():
    ensure_inited()
    try:
        count = mongo_manager.get_document_count()
        return {"status": "active", "document_count": count, "database": "MongoDB", "embedding_model": "gemini-2.0-flash-exp", "llm_model": "gemini-2.0-flash-exp", "storage_type": "MongoDB with vector embeddings"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting stats: {str(e)}")

@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    ensure_inited()
    try:
        ok = mongo_manager.delete_document(doc_id)
        if ok:
            return {"message": "Document deleted successfully", "document_id": doc_id}
        raise HTTPException(status_code=404, detail="Document not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting document: {str(e)}")
