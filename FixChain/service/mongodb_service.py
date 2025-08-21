import os
import json
import math
from datetime import datetime
from typing import List, Dict, Optional, Any
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from dotenv import load_dotenv
from utils.logger import logger

# Load environment variables from root directory
root_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.env')
load_dotenv(root_env_path)

class MongoDBManager:
    def __init__(self):
        self.client = None
        self.db = None
        self.documents_collection = None
        self.embeddings_collection = None
        self.connect()
    
    def connect(self):
        """Connect to MongoDB"""
        try:
            # MongoDB connection string
            # Use localhost for local development, mongodb for docker
            default_url = "mongodb://localhost:27017/"
            if os.getenv("DOCKER_ENV") == "true":
                default_url = "mongodb://admin:password123@mongodb:27017/"
            
            mongo_url = os.getenv("MONGODB_URI", default_url)
            db_name = os.getenv("MONGODB_DATABASE", "rag_db")
            
            self.client = MongoClient(mongo_url)
            self.db = self.client[db_name]
            
            # Get collections
            self.documents_collection = self.db.documents
            self.embeddings_collection = self.db.embeddings
            
            # Test connection
            self.client.admin.command('ping')
            logger.info("✅ Connected to MongoDB successfully")
            
        except Exception as e:
            logger.error(f"❌ Error connecting to MongoDB: {e}")
            raise e
    
    def add_document(self, content: str, metadata: Dict = None, embedding: List[float] = None) -> str:
        """Add document to MongoDB"""
        try:
            if metadata is None:
                metadata = {}
            
            # Generate document ID
            doc_id = f"doc_{datetime.now().timestamp()}"
            
            # Prepare document
            document = {
                "doc_id": doc_id,
                "content": content,
                "metadata": {
                    **metadata,
                    "timestamp": datetime.now().isoformat(),
                    "created_at": datetime.now()
                },
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            }
            
            # Insert document
            result = self.documents_collection.insert_one(document)
            
            # Insert embedding if provided
            if embedding:
                embedding_doc = {
                    "doc_id": doc_id,
                    "vector": embedding,
                    "dimension": len(embedding),
                    "created_at": datetime.now()
                }
                self.embeddings_collection.insert_one(embedding_doc)
            
            return doc_id
            
        except Exception as e:
            raise Exception(f"Error adding document to MongoDB: {str(e)}")
    
    def search_documents(self, query: str, top_k: int = 5) -> List[Dict]:
        """Search documents using text search"""
        try:
            # Use MongoDB text search
            search_results = self.documents_collection.find(
                {"$text": {"$search": query}},
                {"score": {"$meta": "textScore"}}
            ).sort([("score", {"$meta": "textScore"})]).limit(top_k)
            
            documents = []
            for doc in search_results:
                documents.append({
                    "doc_id": doc["doc_id"],
                    "content": doc["content"],
                    "metadata": doc["metadata"],
                    "score": doc.get("score", 0)
                })
            
            return documents

        except Exception as e:
            raise Exception(f"Error searching documents: {str(e)}")
    
    def search_by_embedding(self, query_embedding: List[float], top_k: int = 5) -> List[Dict]:
        """Search documents by embedding similarity (simplified cosine similarity)"""
        try:
            # Get all embeddings
            all_embeddings = list(self.embeddings_collection.find())
            
            # Calculate similarities
            similarities = []
            for emb_doc in all_embeddings:
                similarity = self.cosine_similarity(query_embedding, emb_doc["vector"])
                similarities.append({
                    "doc_id": emb_doc["doc_id"],
                    "similarity": similarity
                })
            
            # Sort by similarity
            similarities.sort(key=lambda x: x["similarity"], reverse=True)
            
            # Get top documents
            top_doc_ids = [item["doc_id"] for item in similarities[:top_k]]
            
            # Fetch documents
            documents = []
            for doc_id in top_doc_ids:
                doc = self.documents_collection.find_one({"doc_id": doc_id})
                if doc:
                    similarity_score = next(item["similarity"] for item in similarities if item["doc_id"] == doc_id)
                    documents.append({
                        "doc_id": doc["doc_id"],
                        "content": doc["content"],
                        "metadata": doc["metadata"],
                        "similarity": similarity_score
                    })
            
            return documents

        except Exception as e:
            raise Exception(f"Error searching by embedding: {str(e)}")
    
    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        try:
            # Calculate dot product
            dot_product = sum(a * b for a, b in zip(vec1, vec2))
            
            # Calculate norms
            norm1 = math.sqrt(sum(a * a for a in vec1))
            norm2 = math.sqrt(sum(b * b for b in vec2))
            
            if norm1 == 0 or norm2 == 0:
                return 0
            
            return dot_product / (norm1 * norm2)
            
        except Exception as e:
            return 0
    
    def get_document_count(self) -> int:
        """Get total number of documents"""
        try:
            return self.documents_collection.count_documents({})
        except Exception as e:
            return 0
    
    def delete_document(self, doc_id: str) -> bool:
        """Delete document and its embedding"""
        try:
            # Delete document
            doc_result = self.documents_collection.delete_one({"doc_id": doc_id})
            
            # Delete embedding
            emb_result = self.embeddings_collection.delete_one({"doc_id": doc_id})
            
            return doc_result.deleted_count > 0

        except Exception as e:
            logger.error(f"Error deleting document: {e}")
            return False
    
    def get_collection(self, collection_name: str) -> Collection:
        """Get a specific collection from the database"""
        try:
            if self.db is None:
                raise Exception("Database not connected")
            return self.db[collection_name]
        except Exception as e:
            raise Exception(f"Error getting collection {collection_name}: {str(e)}")
    
    def insert_rag_document(self, content: str, metadata: Dict[str, Any] = None, embedding: List[float] = None, collection_name: str = "rag_documents") -> str:
        """Insert RAG document into specified collection"""
        try:
            if metadata is None:
                metadata = {}
            
            # Generate document ID
            doc_id = f"doc_{datetime.now().timestamp()}"
            
            # Get the specified collection
            collection = self.get_collection(collection_name)
            
            # Prepare document
            document = {
                "doc_id": doc_id,
                "content": content,
                "metadata": {
                    **metadata,
                    "timestamp": datetime.now().isoformat(),
                    "created_at": datetime.now()
                },
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            }
            
            # Add embedding to document if provided
            if embedding:
                document["embedding"] = embedding
                document["embedding_dimension"] = len(embedding)
            
            # Insert document
            result = collection.insert_one(document)
            
            return doc_id

        except Exception as e:
            raise Exception(f"Error adding RAG document to {collection_name}: {str(e)}")
    
    def close(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            logger.info("✅ MongoDB connection closed")

# Global MongoDB manager instance
mongo_manager = None

def get_mongo_manager() -> MongoDBManager:
    """Get or create MongoDB manager instance"""
    global mongo_manager
    if mongo_manager is None:
        mongo_manager = MongoDBManager()
    return mongo_manager


class MongoDBService:
    """Service wrapper for MongoDB operations used by ExecutionService"""
    
    def __init__(self):
        self.manager = get_mongo_manager()
    
    def insert_execution_log(self, log_entry: Dict[str, Any]) -> str:
        """Insert execution log into MongoDB"""
        try:
            collection = self.manager.get_collection("execution_logs")
            
            # Add timestamp if not present
            if "timestamp" not in log_entry:
                log_entry["timestamp"] = datetime.now().isoformat()
            
            log_entry["created_at"] = datetime.now()
            
            result = collection.insert_one(log_entry)
            return str(result.inserted_id)
            
        except Exception as e:
            raise Exception(f"Error inserting execution log: {str(e)}")
    
    def insert_rag_dataset(self, dataset_info: Dict[str, Any]) -> str:
        """Insert RAG dataset information into MongoDB"""
        try:
            collection = self.manager.get_collection("rag_datasets")
            
            # Add timestamp if not present
            if "inserted_at" not in dataset_info:
                dataset_info["inserted_at"] = datetime.now().isoformat()
            
            dataset_info["created_at"] = datetime.now()
            
            result = collection.insert_one(dataset_info)
            return str(result.inserted_id)
            
        except Exception as e:
            raise Exception(f"Error inserting RAG dataset: {str(e)}")
    
    def get_execution_logs(self, project_key: str = None, limit: int = 100) -> List[Dict]:
        """Get execution logs from MongoDB"""
        try:
            collection = self.manager.get_collection("execution_logs")
            
            query = {}
            if project_key:
                query["project_key"] = project_key
            
            logs = list(collection.find(query).sort("created_at", -1).limit(limit))
            
            # Convert ObjectId to string
            for log in logs:
                if "_id" in log:
                    log["_id"] = str(log["_id"])
            
            return logs
            
        except Exception as e:
            raise Exception(f"Error getting execution logs: {str(e)}")
    
    def get_rag_datasets(self, project_key: str = None) -> List[Dict]:
        """Get RAG datasets from MongoDB"""
        try:
            collection = self.manager.get_collection("rag_datasets")
            
            query = {}
            if project_key:
                query["project_key"] = project_key
            
            datasets = list(collection.find(query).sort("created_at", -1))
            
            # Convert ObjectId to string
            for dataset in datasets:
                if "_id" in dataset:
                    dataset["_id"] = str(dataset["_id"])
            
            return datasets
            
        except Exception as e:
            raise Exception(f"Error getting RAG datasets: {str(e)}")
    
    def insert_bug_fix_result(self, fix_result: Dict[str, Any]) -> str:
        """Insert bug fix result into MongoDB"""
        try:
            collection = self.manager.get_collection("bug_fixes")
            
            fix_result["created_at"] = datetime.now()
            fix_result["timestamp"] = datetime.now().isoformat()
            
            result = collection.insert_one(fix_result)
            return str(result.inserted_id)
            
        except Exception as e:
            raise Exception(f"Error inserting bug fix result: {str(e)}")
