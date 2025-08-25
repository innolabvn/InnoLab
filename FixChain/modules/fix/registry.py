from __future__ import annotations
from typing import Dict, Type

from .base import Fixer

_registry: Dict[str, Type[Fixer]] = {}


def register(name: str, cls: Type[Fixer]) -> None:
    """Register a fixer implementation."""
    _registry[name] = cls


def create(name: str, *args, **kwargs) -> Fixer:
    """Create a registered fixer."""
    if name not in _registry:
        raise KeyError(f"Fixer '{name}' is not registered")
    return _registry[name](*args, **kwargs)


# Register built-in fixers
from .llm import LLMFixer

register("llm", LLMFixer)
