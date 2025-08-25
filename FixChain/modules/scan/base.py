from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, List


class Scanner(ABC):
    """Base scanner interface."""

    @abstractmethod
    def scan(self) -> List[Dict]:
        """Run scan and return list of bugs."""
        raise NotImplementedError
