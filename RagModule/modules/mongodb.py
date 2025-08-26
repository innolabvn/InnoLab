from __future__ import annotations
from typing import Dict, List, Optional

from .base import RAG
from ..mongodb_service import MongoDBManager


class MongoDBRAG(RAG):
    """RAG implementation backed by MongoDB."""

    def __init__(self, manager: Optional[MongoDBManager] = None):
        self.manager = manager or MongoDBManager()

    def add_document(
        self, content: str, metadata: Dict | None = None, embedding: List[float] | None = None
    ) -> str:
        return self.manager.add_document(content, metadata or {}, embedding)

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        return self.manager.search_documents(query, top_k)
