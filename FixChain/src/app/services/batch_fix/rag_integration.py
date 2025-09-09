# src/app/services/batch_fix/rag_integration.py
from __future__ import annotations
from typing import Dict, List, Optional
from pathlib import Path
from src.app.services.rag_service import RAGService
from src.app.services.batch_fix.models import FixResult

class RAGAdapter:
    def __init__(self) -> None:
        self.svc = RAGService()

    def search_context(self, issues_data: Optional[List[Dict]]) -> Optional[str]:
        if not issues_data: return None
        res = self.svc.search_rag_knowledge(issues_data, limit=3)
        if res.success and res.sources:
            return self.svc.get_rag_context_for_prompt(issues_data)
        return None

    def add_fix(self, fix_result: FixResult, issues_data: Optional[List[Dict]], raw_response: str, fixed_code: str) -> bool:
        fix_context = {
            "file_path": fix_result.file_path,
            "original_size": fix_result.original_size,
            "fixed_size": fix_result.fixed_size,
            "similarity_ratio": fix_result.similarity_ratio,
            "input_tokens": fix_result.input_tokens,
            "output_tokens": fix_result.output_tokens,
            "total_tokens": fix_result.total_tokens,
            "processing_time": fix_result.processing_time,
            "meets_threshold": fix_result.meets_threshold,
            "validation_errors": fix_result.validation_errors,
            "issues_found": fix_result.issues_found,
        }
        result = self.svc.add_fix_to_rag(fix_context, issues_data, raw_response, fixed_code)
        return result.success
