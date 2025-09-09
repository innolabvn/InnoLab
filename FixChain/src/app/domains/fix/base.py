# src/app/domains/fixer/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, List


class Fixer(ABC):
    """Base fixer interface for FixChain Fixer domain."""

    def __init__(self, scan_directory: str):
        # Accept either absolute path or a relative project name (e.g., "demo-python")
        self.scan_directory = scan_directory

    @abstractmethod
    def fix_bugs(self, list_real_bugs: List[Dict], use_rag: bool = False) -> Dict:
        """
        Apply fixes to bugs and return result summary.

        Params
        -------
        list_real_bugs: List[Dict]
            A list of issue dicts produced by Scanner (or curated).
        use_rag: bool
            If True, enable RAG enrichment inside batch fix script (if supported).

        Returns
        -------
        Dict: {
          "success": bool,
          "fixed_count": int,
          "total_input_tokens": int,
          "total_output_tokens": int,
          "total_tokens": int,
          "average_similarity": float,
          "threshold_met_count": int,
          "output": str,     # raw combined stdout
          "message": str,    # human-readable summary
          "error": str,      # present only when success=False
        }
        """
        raise NotImplementedError
