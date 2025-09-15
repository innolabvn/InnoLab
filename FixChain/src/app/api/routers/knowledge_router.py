# src/app/api/routers/knowledge.py
"""
Thêm doc, semantic search, stats, delete
"""
from datetime import datetime
import os
from typing import List, Dict, Any, Union, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from src.app.adapters.llm.google_genai import client, EMBEDDING_MODEL, GENERATION_MODEL
from src.app.repositories.mongo import get_mongo_manager
from src.app.services.log_service import logger

root_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))), '.env')
load_dotenv(root_env_path)

router = APIRouter()

class DocumentInput(BaseModel):
    content: str
    metadata: Dict[str, Any]

class SearchInput(BaseModel):
    query: Union[str, List[str]]
    limit: int = Field(default=5, ge=1, le=20)
    combine_mode: str = Field(default="OR", pattern="^(OR|AND)$")
    # NEW: chọn collection & filters để tách Scanner/Fixer
    collection_name: str
    filters: Dict[str, Any]

class SearchResponse(BaseModel):
    query: str
    answer: str
    sources: List[Dict[str, Any]]

async def get_gemini_embedding(text: str) -> List[float]:
    try:
        res = client.models.embed_content(model=EMBEDDING_MODEL, contents=text)
        res_embeddings = getattr(res, "embeddings", None)
        if not res_embeddings or not res_embeddings[0]:
            embedding = [0.0] * 768
            logger.warning("Empty embedding received, returning zero vector")
        else:
            embedding = res_embeddings[0].values
            logger.debug(f"Generated embedding of length {len(embedding)}")
        return embedding
    except Exception as e:
        logger.error(f"Error generating embedding: {str(e)}")
        raise

async def generate_answer_with_gemini(query: str, context_docs: List[Dict]) -> str:
    try:
        context = "\n".join([f"Document {i+1}: {doc.get('content','')}" for i, doc in enumerate(context_docs)])
        prompt = f"""
                Bạn là AI assistant. Dựa trên thông tin dưới đây, trả lời chính xác, tiếng Việt.
                Thông tin:
                {context}

                Question {query}

                Nếu không đủ dữ liệu, hãy nói không đủ thông tin.
                """
        resp = client.models.generate_content(model=GENERATION_MODEL, contents=prompt)
        response_content = resp.text or ""
        logger.debug(f"LLM response: {response_content}")
        return response_content.strip()
    except Exception as e:
        return f"Error generating answer: {str(e)}"

@router.get("/health")
async def health_check():
    mongo_manager = get_mongo_manager()
    try:
        stat = mongo_manager.client.admin.command("ping")
        if stat.get("ok") != 1:
            raise RuntimeError("MongoDB ping failed")
        return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e), "timestamp": datetime.utcnow().isoformat()}

@router.post("/add")
async def add_document(doc_input: DocumentInput):
    mongo_manager = get_mongo_manager()
    try:
        emb = await get_gemini_embedding(doc_input.content[:4000])
        logger.debug(f"Generated embedding {emb} for document")
        doc_id = mongo_manager.add_document(content=doc_input.content, embedding=emb, metadata=doc_input.metadata)
        logger.debug(f"Document added with ID: {doc_id}, content length: {len(doc_input.content)}")
        return {"message": "Document added successfully", "document_id": str(doc_id), "content_length": len(doc_input.content)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding document: {str(e)}")

@router.post("/search", response_model=SearchResponse)
async def search_documents(search_input: SearchInput):
    mongo_manager = get_mongo_manager()
    try:
        collection_name = search_input.collection_name
        extra_filters = search_input.filters or {}
        if isinstance(search_input.query, str):
            # Chọn collection (nếu không truyền, dùng default của manager)
            query_text = search_input.query
            emb = await get_gemini_embedding(query_text)
            results = mongo_manager.search_by_embedding(
                query_embedding=emb,
                top_k=search_input.limit,
                collection_name=collection_name,
                filters=extra_filters,
            )
        else:
            query_text = " ".join(search_input.query)
            all_results = []
            for q in search_input.query:
                emb = await get_gemini_embedding(q)
                all_results.extend(mongo_manager.search_by_embedding(
                    query_embedding=emb, 
                    top_k=search_input.limit,
                    collection_name=collection_name,
                    filters=extra_filters,
                ))
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
        sources = []
        for d in results:
            content = d.get("content", "")
            sources.append({
                "content": content[:200] + "..." if len(content) > 200 else content,
                "metadata": d.get("metadata", {}),
                "similarity_score": d.get("similarity_score", d.get("similarity", 0)),
            })
        return SearchResponse(answer=answer, sources=sources, query=query_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during search: {str(e)}")
