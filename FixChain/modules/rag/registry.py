from __future__ import annotations
from typing import Dict, Type

from .base import RAG

_registry: Dict[str, Type[RAG]] = {}


def register(name: str, cls: Type[RAG]) -> None:
    """Register a RAG implementation."""
    _registry[name] = cls


def create(name: str, *args, **kwargs) -> RAG:
    """Create a registered RAG component."""
    if name not in _registry:
        raise KeyError(f"RAG '{name}' is not registered")
    return _registry[name](*args, **kwargs)


# Register built-in implementation
from .mongodb import MongoDBRAG

register("mongodb", MongoDBRAG)
