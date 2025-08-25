from __future__ import annotations
from typing import Dict, Type

from .base import Scanner

_registry: Dict[str, Type[Scanner]] = {}


def register(name: str, cls: Type[Scanner]) -> None:
    """Register a scanner class"""
    _registry[name] = cls


def create(name: str, *args, **kwargs) -> Scanner:
    """Create a scanner instance by name"""
    if name not in _registry:
        raise ValueError(f"Scanner '{name}' is not registered")
    return _registry[name](*args, **kwargs)
