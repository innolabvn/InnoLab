from __future__ import annotations
from typing import Type, Dict, List

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


class ScannerRegistry:
    """Registry for managing scanner instances and configurations."""
    
    def __init__(self):
        self._scanners: Dict[str, Scanner] = {}
        self._configs: Dict[str, Dict] = {}
    
    def register(self, name: str, scanner_class: Type[Scanner], config: Dict) -> None:
        """Register a scanner with its configuration."""
        self._configs[name] = config
        # Create scanner instance with config
        scanner = scanner_class(config)
        self._scanners[name] = scanner
    
    def get_scanner(self, name: str) -> Scanner:
        """Get a registered scanner."""
        if name not in self._scanners:
            raise KeyError(f"Scanner '{name}' is not registered")
        return self._scanners[name]
    
    def list_scanners(self) -> List[str]:
        """List all registered scanner names."""
        return list(self._scanners.keys())
    
    def get_config(self, name: str) -> Dict:
        """Get configuration for a scanner."""
        if name not in self._configs:
            raise KeyError(f"Scanner '{name}' is not registered")
        return self._configs[name]


# Register built-in scanners
from .bearer import BearerScanner
from .sonar import SonarQScanner

register("bearer", BearerScanner)
register("sonarq", SonarQScanner)
