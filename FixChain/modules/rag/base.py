from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, List


class RAG(ABC):
    """Base interface for RAG components."""

    @abstractmethod
    def add_document(self, content: str, metadata: Dict | None = None, embedding: List[float] | None = None) -> str:
        """Add a document to the knowledge base."""
        raise NotImplementedError

    @abstractmethod
    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """Search documents relevant to the query."""
        raise NotImplementedError
