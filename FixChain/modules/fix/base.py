from __future__ import annotations
from typing import Dict, List


class Fixer:
    """Base fixer interface"""

    def fix_bugs(self, list_real_bugs: List[Dict], use_rag: bool = False) -> Dict:
        """Apply fixes to provided bugs"""
        raise NotImplementedError
