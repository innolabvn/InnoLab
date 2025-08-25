from __future__ import annotations
from typing import Dict, Type

from .base import Fixer

_registry: Dict[str, Type[Fixer]] = {}


def register(name: str, cls: Type[Fixer]) -> None:
    """Register a fixer class"""
    _registry[name] = cls


def create(name: str, *args, **kwargs) -> Fixer:
    """Create a fixer instance by name"""
    if name not in _registry:
        raise ValueError(f"Fixer '{name}' is not registered")
    return _registry[name](*args, **kwargs)
