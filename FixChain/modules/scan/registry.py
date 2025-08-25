from __future__ import annotations
from typing import Type, Dict

from .base import Scanner

_registry: Dict[str, Type[Scanner]] = {}


def register(name: str, cls: Type[Scanner]) -> None:
    """Register a scanner implementation."""
    _registry[name] = cls


def create(name: str, *args, **kwargs) -> Scanner:
    """Create a registered scanner."""
    if name not in _registry:
        raise KeyError(f"Scanner '{name}' is not registered")
    return _registry[name](*args, **kwargs)


# Register built-in scanners
from .bearer import BearerScanner
from .sonar import SonarQScanner

register("bearer", BearerScanner)
register("sonarq", SonarQScanner)
