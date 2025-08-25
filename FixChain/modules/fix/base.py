from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, List


class Fixer(ABC):
    """Base fixer interface."""

    def __init__(self, scan_directory: str):
        self.scan_directory = scan_directory

    @abstractmethod
    def fix_bugs(self, list_real_bugs: List[Dict], use_rag: bool = False) -> Dict:
        """Apply fixes to bugs and return result summary."""
        raise NotImplementedError
