from __future__ import annotations
from typing import Dict, List


class Scanner:
    """Base scanner interface"""

    def scan(self) -> List[Dict]:
        """Run scan and return list of bugs"""
        raise NotImplementedError
