# src\app\repositories\mongo.py
import os
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from pymongo import MongoClient, ASCENDING, TEXT
from pymongo.collection import Collection
from dotenv import load_dotenv
from src.app.services.log_service import logger

# Load environment variables from root directory
root_env_path = Path(__file__).resolve().parents[4] / '.env'
load_dotenv(root_env_path)

def now_utc():
    return datetime.now(timezone.utc)

def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return v.strip() if v and v.strip() else default

class MongoDBManager:
    """
    Chuẩn hoá:
    - Document chính lưu luôn field `embedding` (float[]), `embedding_dimension`.
    - search_by_embedding: ưu tiên $vectorSearch (index: vector_index, path: embedding), fallback cosine.
    - Giữ tương thích ngược: vẫn có `embeddings_collection` nếu dữ liệu cũ còn đó.
    """
    def __init__(self):
        uri = _env("MONGODB_URI", "mongodb://mongodb:27017")
        dbname = _env("MONGODB_DATABASE", "fixchain")

        self.client = MongoClient(uri)
        self.db = self.client[dbname]

        # Tên collection có thể cấu hình
        self.scanner_col_name = _env("SCANNER_RAG_COLLECTION", "scanner_rag_collection")
        self.fixer_col_name = _env("FIXER_RAG_COLLECTION", "fixer_rag_collection")

        self.scanner_col = self.db[self.scanner_col_name]
        self.fixer_col = self.db[self.fixer_col_name]

        try:
            # Ping
            ping = self.client.admin.command("ping")
            if ping.get("ok") == 1.0:
                logger.info("Connected to MongoDB successfully")
        
        except Exception as e:
            logger.error(f"Error connecting to MongoDB: {e}")
            raise

        # Tạo index cơ bản (idempotent)
        self._ensure_indexes(self.scanner_col)
        self._ensure_indexes(self.fixer_col)

    def _ensure_indexes(self, col: Collection):
        """Tạo các index an toàn nhiều lần."""
        try:
            # full-text fallback cho content
            col.create_index([("content", TEXT)])
        except Exception as e:
            logger.warning(f"[{col.name}] Create TEXT index failed (content): {e}")

        # lọc nhanh theo các trường phổ biến
        try:
            col.create_index([("doc_id", ASCENDING)], unique=True)
            col.create_index([("created_at", ASCENDING)])
            col.create_index([("metadata.project_key", ASCENDING)])
            col.create_index([("metadata.repo", ASCENDING)])
            col.create_index([("metadata.language", ASCENDING)])
            col.create_index([("metadata.tag", ASCENDING)])
        except Exception as e:
            logger.warning(f"[{col.name}] Create B-tree indexes failed: {e}")

    # -------------- Helpers --------------
    def collection(self, collection_name: str) -> Collection:
        """Trả về collection chuẩn theo tên truyền vào (scanner/fixer)."""
        if collection_name == self.scanner_col_name:
            return self.scanner_col
        if collection_name == self.fixer_col_name:
            return self.fixer_col
        # Cho phép mở rộng thêm nếu cần, nhưng tránh dùng tên cũ
        return self.db[collection_name]

    # -------------- CRUD --------------
    def add_document(
        self,
        *,
        content: str,
        metadata: Optional[Dict[str, Any]],
        embedding: Optional[List[float]],
        collection_name: str,
    ) -> str:
        """
        Thêm document vào 1 trong 2 collection RAG. Không ghi legacy, không dùng collections cũ.
        """
        try:
            col = self.collection(collection_name)
            metadata = metadata or {}
            doc_id = f"doc_{datetime.now().timestamp()}"

            document: Dict[str, Any] = {
                "doc_id": doc_id,
                "content": content,
                "metadata": {**metadata},
                "created_at": now_utc(),
            }

            if embedding:
                document["embedding"] = embedding
                document["embedding_dimension"] = len(embedding)

            col.insert_one(document)
            return doc_id

        except Exception as e:
            raise Exception(f"Error adding document to {collection_name}: {str(e)}")

    def insert_rag_document(
        self,
        *,
        content: str,
        metadata: Dict[str, Any],
        embedding: Optional[List[float]],
        collection_name: str,
    ) -> str:
        """
        Giữ API tương thích: alias của add_document (tham số bắt buộc giống nhau).
        """
        return self.add_document(
            content=content,
            metadata=metadata,
            embedding=embedding,
            collection_name=collection_name,
        )
    
    def get_document_count(self, collection_name: str) -> int:
        try:
            return self.collection(collection_name).count_documents({})
        except Exception:
            return 0

    # -------------- Search --------------
    def search_by_embedding(
        self,
        *,
        query_embedding: List[float],
        collection_name: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Cosine similarity trên embedding lưu trong document (fallback cho MongoDB CE/7.0).
        """
        col = self.collection(collection_name)
        try:
            cursor = col.find({"embedding": {"$exists": True}}, {
                "doc_id": 1, "embedding": 1, "content": 1, "metadata": 1
            })

            sims: List[Dict[str, Any]] = []
            for d in cursor:
                vec = d.get("embedding") or []
                score = self.cosine_similarity(query_embedding, vec)

                md = d.get("metadata") or {}
                if filters:
                    # Áp dụng filter chính xác theo metadata
                    for fk, fv in filters.items():
                        if md.get(fk) != fv:
                            break
                    else:
                        sims.append({
                            "doc_id": d.get("doc_id"),
                            "content": d.get("content", ""),
                            "metadata": md,
                            "similarity_score": score,
                        })
                    continue

                sims.append({
                    "doc_id": d.get("doc_id"),
                    "content": d.get("content", ""),
                    "metadata": md,
                    "similarity_score": score,
                })

            sims.sort(key=lambda x: x["similarity_score"], reverse=True)
            return sims[:top_k]

        except Exception as e:
            raise Exception(f"Error searching by embedding in {collection_name}: {str(e)}")
        
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


# Singleton
_mongo_manager: Optional[MongoDBManager] = None


def get_mongo_manager() -> MongoDBManager:
    global _mongo_manager
    if _mongo_manager is None:
        _mongo_manager = MongoDBManager()
    return _mongo_manager


# ---- Service wrappers giữ nguyên API cũ ----
class MongoDBService:
    """Service wrapper for MongoDB operations used by ExecutionService"""

    def __init__(self):
        self.manager = get_mongo_manager()

    # Logging chung (không thuộc RAG)
    def insert_execution_log(self, log_entry: Dict[str, Any]) -> str:
        col = self.manager.db["execution_logs"]
        if "timestamp" not in log_entry:
            log_entry["timestamp"] = now_utc().isoformat()
        log_entry["created_at"] = now_utc()
        res = col.insert_one(log_entry)
        return str(res.inserted_id)

    def get_execution_logs(self, project_key: str = "", limit: int = 100) -> List[Dict]:
        col = self.manager.db["execution_logs"]
        q: Dict[str, Any] = {}
        if project_key:
            q["project_key"] = project_key
        logs = list(col.find(q).sort("created_at", -1).limit(limit))
        for lg in logs:
            if "_id" in lg:
                lg["_id"] = str(lg["_id"])
        return logs

    # Dataset registry (không phải RAG store)
    def insert_rag_dataset(self, dataset_info: Dict[str, Any]) -> str:
        col = self.manager.db["rag_datasets"]
        if "inserted_at" not in dataset_info:
            dataset_info["inserted_at"] = now_utc().isoformat()
        dataset_info["created_at"] = now_utc()
        res = col.insert_one(dataset_info)
        return str(res.inserted_id)

    def get_rag_datasets(self, project_key: str = "") -> List[Dict]:
        col = self.manager.db["rag_datasets"]
        q: Dict[str, Any] = {}
        if project_key:
            q["project_key"] = project_key
        datasets = list(col.find(q).sort("created_at", -1))
        for ds in datasets:
            if "_id" in ds:
                ds["_id"] = str(ds["_id"])
        return datasets

    # Kết quả fix (tuỳ ứng dụng, có thể giữ nguyên)
    def insert_bug_fix_result(self, fix_result: Dict[str, Any]) -> str:
        col = self.manager.db["bug_fixes"]
        fix_result["created_at"] = now_utc()
        fix_result["timestamp"] = now_utc().isoformat()
        res = col.insert_one(fix_result)
        return str(res.inserted_id)