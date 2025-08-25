import os
import asyncio
from typing import List, Dict, Any, Union, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import google.generativeai as genai
from dotenv import load_dotenv
import numpy as np
from modules.mongodb_service import MongoDBManager
import uvicorn

# Load environment variables from root directory
root_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.env')
load_dotenv(root_env_path)

# Resources initialized on startup
embedding_model = None
llm_model = None
mongo_manager: Optional[MongoDBManager] = None

def init_resources():
    global embedding_model, llm_model, mongo_manager
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if embedding_model is None or llm_model is None:
        if not gemini_api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        genai.configure(api_key=gemini_api_key)
        embedding_model = genai.GenerativeModel('gemini-2.0-flash-exp')
        llm_model = genai.GenerativeModel('gemini-2.0-flash-exp')
    if mongo_manager is None:
        mongo_manager = MongoDBManager()

# APIRouter
app = APIRouter()

@app.on_event("startup")
async def startup_event():
    init_resources()

# Pydantic models
class DocumentInput(BaseModel):
    content: str = Field(
        ..., 
        description="Nội dung document cần thêm vào knowledge base",
        min_length=10,
        example="Python là một ngôn ngữ lập trình mạnh mẽ và dễ học. Nó được sử dụng rộng rãi trong phát triển web, data science, và AI."
    )
    metadata: Dict[str, Any] = Field(
        default={}, 
        description="Metadata bổ sung cho document (category, tags, author, etc.)",
        example={
            "category": "programming",
            "language": "python",
            "level": "beginner",
            "tags": ["tutorial", "basics"]
        }
    )

class SearchInput(BaseModel):
    query: Union[str, List[str]] = Field(
        ..., 
        description="Câu hỏi tìm kiếm (string) hoặc danh sách các từ khóa (array of strings)",
        examples=[
            "How to optimize Python performance?",
            ["Python", "performance", "optimization"]
        ]
    )
    limit: int = Field(
        default=5, 
        description="Số lượng documents tối đa trả về",
        ge=1, 
        le=20
    )
    combine_mode: str = Field(
        default="OR", 
        description="Cách kết hợp multiple queries: 'OR' (tìm documents khớp BẤT KỲ query nào) hoặc 'AND' (tìm documents khớp TẤT CẢ queries)",
        pattern="^(OR|AND)$"
    )

class SearchResponse(BaseModel):
    answer: str = Field(
        ..., 
        description="Câu trả lời được tạo bởi AI dựa trên documents tìm được",
        example="Python có thể được tối ưu hóa thông qua việc sử dụng các thư viện như NumPy, tránh loops không cần thiết..."
    )
    sources: List[Dict[str, Any]] = Field(
        ..., 
        description="Danh sách documents liên quan được tìm thấy",
        example=[
            {
                "content": "Python performance can be improved by...",
                "metadata": {"category": "programming", "language": "python"},
                "similarity_score": 0.95
            }
        ]
    )
    query: str = Field(
        ..., 
        description="Query đã được xử lý (kết hợp từ array nếu có)",
        example="Python performance optimization"
    )

# Helper functions
async def get_gemini_embedding(text: str) -> List[float]:
    """Get embedding from Gemini Flash 2.0"""
    try:
        # Use Gemini's embedding task
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type="retrieval_document"
        )
        return result['embedding']
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating embedding: {str(e)}")

async def generate_answer_with_gemini(query: str, context_docs: List[Dict]) -> str:
    """Generate answer using Gemini Flash 2.0"""
    try:
        # Prepare context from retrieved documents
        context = "\n\n".join([
            f"Document {i+1}: {doc.get('content', '')}" 
            for i, doc in enumerate(context_docs)
        ])
        
        prompt = f"""
Bạn là một AI assistant thông minh. Dựa trên thông tin được cung cấp, hãy trả lời câu hỏi một cách chính xác và chi tiết.

Thông tin tham khảo:
{context}

Câu hỏi: {query}

Hãy trả lời bằng tiếng Việt, dựa trên thông tin được cung cấp. Nếu không có thông tin liên quan, hãy nói rằng bạn không có đủ thông tin để trả lời.
"""
        
        response = llm_model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Xin lỗi, tôi không thể tạo câu trả lời do lỗi: {str(e)}"

# API endpoints

@app.get("/")
async def root():
    return {
        "message": "RAG API with MongoDB & Gemini Flash 2.0 is running!",
        "version": "2.0.0",
        "features": [
            "MongoDB document storage",
            "Gemini Flash 2.0 embeddings",
            "Gemini Flash 2.0 generation",
            "Semantic search",
            "Vietnamese support"
        ],
        "endpoints": {
            "add_document": "POST /reasoning/add",
            "search": "POST /reasoning/search",
            "stats": "GET /reasoning/stats"
        }
    }

@app.get("/health")
async def health_check():
    try:
        # Test MongoDB connection
        mongo_manager.client.admin.command('ping')
        return {"status": "healthy", "database": "connected", "ai_model": "gemini-2.0-flash-exp"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

@app.post("/reasoning/add")
async def add_document(doc_input: DocumentInput):
    """Add a document to MongoDB with Gemini embeddings"""
    try:
        # Generate embedding using Gemini
        embedding = await get_gemini_embedding(doc_input.content)
        
        # Add document to MongoDB
        doc_id = mongo_manager.add_document(
            content=doc_input.content,
            embedding=embedding,
            metadata=doc_input.metadata
        )
        
        return {
            "message": "Document added successfully",
            "document_id": str(doc_id),
            "content_length": len(doc_input.content),
            "embedding_model": "gemini-2.0-flash-exp"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding document: {str(e)}")

@app.post("/reasoning/search", response_model=SearchResponse)
async def search_documents(search_input: SearchInput):
    """
    Tìm kiếm documents sử dụng Gemini embeddings và tạo câu trả lời AI
    
    Hỗ trợ hai loại tìm kiếm:
    - **Single Query**: Tìm kiếm với một câu hỏi duy nhất
    - **Array Search**: Tìm kiếm với nhiều từ khóa, hỗ trợ OR/AND mode
    
    **OR Mode**: Tìm documents khớp với BẤT KỲ query nào (mặc định)
    **AND Mode**: Tìm documents khớp với TẤT CẢ queries
    
    **Ví dụ Single Query:**
    ```json
    {
        "query": "How to optimize Python performance?",
        "limit": 5
    }
    ```
    
    **Ví dụ Array Search - OR Mode:**
    ```json
    {
        "query": ["Python", "performance", "optimization"],
        "limit": 5,
        "combine_mode": "OR"
    }
    ```
    
    **Ví dụ Array Search - AND Mode:**
    ```json
    {
        "query": ["database", "Python", "connection"],
        "limit": 3,
        "combine_mode": "AND"
    }
    ```
    """
    try:
        # Handle both single query and array of queries
        if isinstance(search_input.query, str):
            # Single query
            query_text = search_input.query
            query_embedding = await get_gemini_embedding(query_text)
            
            results = mongo_manager.search_by_embedding(
                query_embedding=query_embedding,
                top_k=search_input.limit
            )
        else:
            # Multiple queries (array)
            query_text = " ".join(search_input.query)  # Combine for answer generation
            all_results = []
            
            for single_query in search_input.query:
                query_embedding = await get_gemini_embedding(single_query)
                single_results = mongo_manager.search_by_embedding(
                    query_embedding=query_embedding,
                    top_k=search_input.limit
                )
                all_results.extend(single_results)
            
            # Remove duplicates and combine results based on mode
            if search_input.combine_mode.upper() == "AND":
                # For AND mode, only keep documents that appear in all query results
                doc_counts = {}
                for doc in all_results:
                    doc_id = doc.get("_id", str(doc))
                    if doc_id not in doc_counts:
                        doc_counts[doc_id] = {"count": 0, "doc": doc, "total_score": 0}
                    doc_counts[doc_id]["count"] += 1
                    doc_counts[doc_id]["total_score"] += doc.get("similarity_score", 0)
                
                # Only keep docs that appear in all queries
                num_queries = len(search_input.query)
                results = [
                    {**item["doc"], "similarity_score": item["total_score"] / item["count"]}
                    for item in doc_counts.values() 
                    if item["count"] == num_queries
                ]
            else:
                # For OR mode (default), combine all results and remove duplicates
                seen_docs = set()
                results = []
                for doc in all_results:
                    doc_id = doc.get("_id", str(doc))
                    if doc_id not in seen_docs:
                        seen_docs.add(doc_id)
                        results.append(doc)
            
            # Sort by similarity score and limit
            results = sorted(results, key=lambda x: x.get("similarity_score", 0), reverse=True)[:search_input.limit]
        
        if not results:
            return SearchResponse(
                answer="Xin lỗi, tôi không tìm thấy thông tin liên quan đến câu hỏi của bạn.",
                sources=[],
                query=query_text
            )
        
        # Generate answer using Gemini
        answer = await generate_answer_with_gemini(query_text, results)
        
        # Format sources
        sources = [
            {
                "content": doc["content"][:200] + "..." if len(doc["content"]) > 200 else doc["content"],
                "metadata": doc.get("metadata", {}),
                "similarity_score": doc.get("similarity_score", 0)
            }
            for doc in results
        ]
        
        return SearchResponse(
            answer=answer,
            sources=sources,
            query=query_text
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during search: {str(e)}")

@app.get("/reasoning/stats")
async def get_stats():
    """Get system statistics"""
    try:
        doc_count = mongo_manager.get_document_count()
        return {
            "status": "active",
            "document_count": doc_count,
            "database": "MongoDB",
            "embedding_model": "gemini-2.0-flash-exp",
            "llm_model": "gemini-2.0-flash-exp",
            "storage_type": "MongoDB with vector embeddings"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting stats: {str(e)}")

@app.delete("/reasoning/documents/{doc_id}")
async def delete_document(doc_id: str):
    """Delete a document from MongoDB"""
    try:
        success = mongo_manager.delete_document(doc_id)
        if success:
            return {"message": "Document deleted successfully", "document_id": doc_id}
        else:
            raise HTTPException(status_code=404, detail="Document not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting document: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(
        "rag_mongodb_gemini:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )