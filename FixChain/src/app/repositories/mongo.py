import os
import math
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from pymongo import MongoClient, ASCENDING, TEXT
from pymongo.collection import Collection
from pymongo.errors import OperationFailure
from dotenv import load_dotenv
from src.app.services.log_service import logger

# Load environment variables from root directory
root_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), '.env')
load_dotenv(root_env_path)


def now_utc():
    return datetime.now(timezone.utc)


class MongoDBManager:
    """
    Chuẩn hoá:
    - Document chính lưu luôn field `embedding` (float[]), `embedding_dimension`.
    - search_by_embedding: ưu tiên $vectorSearch (index: vector_index, path: embedding), fallback cosine.
    - Giữ tương thích ngược: vẫn có `embeddings_collection` nếu dữ liệu cũ còn đó.
    """
    def __init__(self):
        self.client: Optional[MongoClient] = None
        self.db = None
        self.documents_collection: Optional[Collection] = None
        self.embeddings_collection: Optional[Collection] = None
        self.connect()

    # -------------- Connection --------------
    def connect(self):
        """Connect to MongoDB & prepare collections/indexes"""
        try:
            default_url = "mongodb://localhost:27017/"
            if os.getenv("DOCKER_ENV") == "true":
                # giữ tương thích docker-compose hiện tại
                default_url = "mongodb://admin:password123@mongodb:27017/"

            mongo_url = os.getenv("MONGODB_URI") or default_url
            db_name = os.getenv("MONGODB_DATABASE") or "rag_db"

            self.client = MongoClient(mongo_url)
            self.db = self.client[db_name]

            # Collections mặc định
            self.documents_collection = self.db["documents"]
            self.embeddings_collection = self.db["embeddings"]  # legacy

            # Ping
            self.client.admin.command("ping")
            logger.info("Connected to MongoDB successfully")

            # Indexes cơ bản (an toàn khi tạo nhiều lần)
            # 1) Text index cho content (fallback search)
            try:
                self.documents_collection.create_index([("content", TEXT)])
            except Exception as e:
                logger.warning(f"Create TEXT index failed (content): {e}")

            # 2) Một số index filter thường dùng
            try:
                self.documents_collection.create_index([("metadata.document_type", ASCENDING)])
                self.documents_collection.create_index([("metadata.project", ASCENDING)])
                self.documents_collection.create_index([("doc_id", ASCENDING)], unique=True)
            except Exception as e:
                logger.warning(f"Create B-tree indexes failed: {e}")

            # Lưu ý: Atlas Vector Index 'vector_index' cần tạo ở Atlas UI/API:
            # - index name: vector_index
            # - path: embedding
            # - type: knnVector (dimensions = embedding_dimension, similarity = cosine)

        except Exception as e:
            logger.error(f"Error connecting to MongoDB: {e}")
            raise e

    # -------------- CRUD --------------
    def add_document(self, content: str, metadata: Dict | None, embedding: List[float] | None) -> str:
        """Add document; lưu embedding ngay trong document (ưu tiên mới), vẫn tương thích dữ liệu cũ."""
        try:
            metadata = metadata or {}

            # Generate document ID (giữ kiểu cũ để không phá controller khác)
            doc_id = f"doc_{datetime.now().timestamp()}"

            document = {
                "doc_id": doc_id,
                "content": content,
                "metadata": {
                    **metadata,
                    "timestamp": now_utc().isoformat(),
                    "created_at": now_utc(),
                },
                "created_at": now_utc(),
                "updated_at": now_utc(),
            }

            # Lưu embedding trong document (mới)
            if embedding:
                document["embedding"] = embedding
                document["embedding_dimension"] = len(embedding)

            # Insert document
            self.documents_collection.insert_one(document)

            # Viết legacy sang embeddings_collection (nếu embedding có) để không hỏng code cũ dùng cosine
            if embedding:
                try:
                    self.embeddings_collection.insert_one({
                        "doc_id": doc_id,
                        "vector": embedding,
                        "dimension": len(embedding),
                        "created_at": now_utc(),
                    })
                except Exception as e:
                    logger.warning(f"Legacy embeddings insert failed (safe to ignore): {e}")

            return doc_id

        except Exception as e:
            raise Exception(f"Error adding document to MongoDB: {str(e)}")

    def get_document_count(self) -> int:
        try:
            return self.documents_collection.count_documents({})
        except Exception:
            return 0

    def delete_document(self, doc_id: str) -> bool:
        """Delete document (và legacy embedding nếu có)."""
        try:
            doc_result = self.documents_collection.delete_one({"doc_id": doc_id})
            try:
                self.embeddings_collection.delete_one({"doc_id": doc_id})
            except Exception as e:
                logger.warning(f"Legacy embeddings delete failed: {e}")
            return doc_result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting document: {e}")
            return False

    def get_collection(self, collection_name: str) -> Collection:
        """Lấy collection bất kỳ (dùng cho fix_cases, dataset, v.v.)."""
        try:
            if self.db is None:
                raise Exception("Database not connected")
            return self.db[collection_name]
        except Exception as e:
            raise Exception(f"Error getting collection {collection_name}: {str(e)}")

    def insert_rag_document(
        self,
        content: str,
        metadata: Dict[str, Any] = None,
        embedding: List[float] = None,
        collection_name: str = "rag_documents",
    ) -> str:
        """Insert RAG document vào collection xác định (dùng cho fix_cases/knowledge)."""
        try:
            metadata = metadata or {}
            doc_id = f"doc_{datetime.now().timestamp()}"
            col = self.get_collection(collection_name)
            doc = {
                "doc_id": doc_id,
                "content": content,
                "metadata": {
                    **metadata,
                    "timestamp": now_utc().isoformat(),
                    "created_at": now_utc(),
                },
                "created_at": now_utc(),
                "updated_at": now_utc(),
            }
            if embedding:
                doc["embedding"] = embedding
                doc["embedding_dimension"] = len(embedding)
            col.insert_one(doc)
            return doc_id
        except Exception as e:
            raise Exception(f"Error adding RAG document to {collection_name}: {str(e)}")

    # -------------- Search --------------
    def search_documents(self, query: str, top_k: int = 5) -> List[Dict]:
        """Text search fallback (Mongo TEXT index)."""
        try:
            cursor = self.documents_collection.find(
                {"$text": {"$search": query}},
                {"score": {"$meta": "textScore"}},
            ).sort([("score", {"$meta": "textScore"})]).limit(top_k)

            docs = []
            for d in cursor:
                docs.append({
                    "doc_id": d.get("doc_id"),
                    "content": d.get("content", ""),
                    "metadata": d.get("metadata", {}),
                    "score": d.get("score", 0),
                })
            return docs
        except Exception as e:
            raise Exception(f"Error searching documents: {str(e)}")

    def search_by_embedding(self, query_embedding: List[float], top_k: int = 5) -> List[Dict]:
        """
        Ưu tiên dùng $vectorSearch (Atlas Vector Index: 'vector_index', path: 'embedding').
        Fallback: cosine similarity trên dữ liệu có sẵn (embeddings_collection hoặc documents.embedding).
        """
        # 1) Thử vectorSearch trên `documents`
        try:
            pipeline = [{
                "$vectorSearch": {
                    "index": "vector_index",
                    "path": "embedding",
                    "queryVector": query_embedding,
                    "numCandidates": max(top_k * 10, 50),
                    "limit": top_k,
                }
            }]
            results = list(self.documents_collection.aggregate(pipeline))
            # Chuẩn hoá output (dùng key 'similarity' giống code cũ)
            out = []
            for r in results:
                out.append({
                    "doc_id": r.get("doc_id"),
                    "content": r.get("content", ""),
                    "metadata": r.get("metadata", {}),
                    # Vector Search trả về 'score' (tuỳ cấu hình), chuẩn hoá tên:
                    "similarity": r.get("score", r.get("similarity", 0)),
                })
            if out:
                return out
        except OperationFailure as ofe:
            # Atlas Search chưa enable/index chưa tồn tại
            logger.warning(f"$vectorSearch not available, fallback to cosine. Detail: {ofe.details if hasattr(ofe, 'details') else str(ofe)}")
        except Exception as e:
            logger.warning(f"$vectorSearch error, fallback to cosine: {e}")

        # 2) Fallback: cosine trên embeddings_collection (legacy) hoặc documents.embedding
        try:
            similarities = []

            # Ưu tiên documents.embedding (mới)
            cursor = self.documents_collection.find({"embedding": {"$exists": True}})
            docs = list(cursor)
            if not docs:
                # fallback cuối: legacy collection
                docs = list(self.embeddings_collection.find())
                use_legacy = True
            else:
                use_legacy = False

            for d in docs:
                if use_legacy:
                    doc_id = d["doc_id"]
                    vec = d.get("vector", [])
                    sim = self.cosine_similarity(query_embedding, vec)
                    # load document content/metadata
                    doc = self.documents_collection.find_one({"doc_id": doc_id}) or {}
                    content = doc.get("content", "")
                    metadata = doc.get("metadata", {})
                else:
                    doc_id = d.get("doc_id")
                    vec = d.get("embedding", [])
                    sim = self.cosine_similarity(query_embedding, vec)
                    content = d.get("content", "")
                    metadata = d.get("metadata", {})

                similarities.append((doc_id, sim, content, metadata))

            similarities.sort(key=lambda x: x[1], reverse=True)
            top = similarities[:top_k]
            return [{
                "doc_id": t[0],
                "content": t[2],
                "metadata": t[3],
                "similarity": t[1],
            } for t in top]

        except Exception as e:
            raise Exception(f"Error searching by embedding: {str(e)}")

    @staticmethod
    def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """Cosine similarity (fallback)."""
        try:
            dot = sum(a * b for a, b in zip(vec1, vec2))
            n1 = math.sqrt(sum(a * a for a in vec1)) or 0.0
            n2 = math.sqrt(sum(b * b for b in vec2)) or 0.0
            if n1 == 0 or n2 == 0:
                return 0.0
            return dot / (n1 * n2)
        except Exception:
            return 0.0

    # -------------- Utils --------------
    def close(self):
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")


# Global MongoDB manager instance (giữ API cũ)
mongo_manager: Optional[MongoDBManager] = None

def get_mongo_manager() -> MongoDBManager:
    global mongo_manager
    if mongo_manager is None:
        mongo_manager = MongoDBManager()
    return mongo_manager


# ---- Service wrappers giữ nguyên API cũ ----
class MongoDBService:
    """Service wrapper for MongoDB operations used by ExecutionService"""

    def __init__(self):
        self.manager = get_mongo_manager()

    def insert_execution_log(self, log_entry: Dict[str, Any]) -> str:
        try:
            col = self.manager.get_collection("execution_logs")
            if "timestamp" not in log_entry:
                log_entry["timestamp"] = now_utc().isoformat()
            log_entry["created_at"] = now_utc()
            res = col.insert_one(log_entry)
            return str(res.inserted_id)
        except Exception as e:
            raise Exception(f"Error inserting execution log: {str(e)}")

    def insert_rag_dataset(self, dataset_info: Dict[str, Any]) -> str:
        try:
            col = self.manager.get_collection("rag_datasets")
            if "inserted_at" not in dataset_info:
                dataset_info["inserted_at"] = now_utc().isoformat()
            dataset_info["created_at"] = now_utc()
            res = col.insert_one(dataset_info)
            return str(res.inserted_id)
        except Exception as e:
            raise Exception(f"Error inserting RAG dataset: {str(e)}")

    def get_execution_logs(self, project_key: str = None, limit: int = 100) -> List[Dict]:
        try:
            col = self.manager.get_collection("execution_logs")
            q = {}
            if project_key:
                q["project_key"] = project_key
            logs = list(col.find(q).sort("created_at", -1).limit(limit))
            for lg in logs:
                if "_id" in lg:
                    lg["_id"] = str(lg["_id"])
            return logs
        except Exception as e:
            raise Exception(f"Error getting execution logs: {str(e)}")

    def get_rag_datasets(self, project_key: str = None) -> List[Dict]:
        try:
            col = self.manager.get_collection("rag_datasets")
            q = {}
            if project_key:
                q["project_key"] = project_key
            datasets = list(col.find(q).sort("created_at", -1))
            for ds in datasets:
                if "_id" in ds:
                    ds["_id"] = str(ds["_id"])
            return datasets
        except Exception as e:
            raise Exception(f"Error getting RAG datasets: {str(e)}")

    def insert_bug_fix_result(self, fix_result: Dict[str, Any]) -> str:
        try:
            col = self.manager.get_collection("bug_fixes")
            fix_result["created_at"] = now_utc()
            fix_result["timestamp"] = now_utc().isoformat()
            res = col.insert_one(fix_result)
            return str(res.inserted_id)
        except Exception as e:
            raise Exception(f"Error inserting bug fix result: {str(e)}")
