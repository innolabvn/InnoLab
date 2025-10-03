# src/app/services/batch_fix/rag_integration.py
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
import uuid
from src.app.domains.fix.models import RealBug
from src.app.services.rag_service import RAGService
from src.app.services.batch_fix.models import FixResult
from src.app.services.log_service import logger

def build_query_and_filters_from_issues(issues_data: List[RealBug]) -> Tuple[str, Dict[str, str]]:
    """
    Build a concise query string and filters from a collection of issues for Fixer RAG search.
    Returns:
        query (str): deduplicated terms joined with " | ", truncated to 1000 chars
        filters (dict): includes at most {label, classification, file_name}
    """
    if not issues_data:
        return "", {}
    
    seen: set[str] = set()
    terms: List[str] = []
    filters: Dict[str, str] = {}
    
    for it in issues_data:
        key = it.key
        issue_id = it.id
        lang = it.lang
        title = it.title
        severity = it.severity
        code_snippet = it.code_snippet

        for val in (key, issue_id, lang, title, severity, code_snippet):
            if val and val not in seen:
                seen.add(val)
                terms.append(val)
        
        # filter
        if it.label.upper() == "BUG":
            filters.setdefault("label", "BUG")

        if it.file_name and "file_name" not in filters:
            filters["file_name"] = it.file_name

    query = " | ".join(terms)[:1000]
    return query, filters

def _build_bug_items_payload(
    fix_result: FixResult,
    issues_data: List[RealBug],
    fixed_code: str,
) -> List[Dict[str, Any]]:
    """
    Map FixResult + issues_data -> payload 'bugs' theo schema BugItem của Fixer router.
    """
    bug_items: List[Dict[str, Any]] = []
    file_path = fix_result.file_path or ""
    fixed_file = Path(file_path).name if file_path else ""

    for it in issues_data:
        key = it.key or str(uuid.uuid4())
        file_name = fixed_file or (it.file_name or "")
        description = f"Fix applied to {file_name}, {it.title}"

        bug_items.append({
            "doc_id": key,
            "id": it.id,
            "type": it.label,
            "lang": it.lang,
            "description": description,
            "file_path": file_path,
            "code_snippet": it.code_snippet,
            "fixed_code": fixed_code,
            "metadata": {
                "severity": it.severity,
                "line_number": it.line_number,
                "original_size": getattr(fix_result, "original_size", 0) or 0,
                "fixed_size": getattr(fix_result, "fixed_size", 0) or 0,
                "similarity_ratio": getattr(fix_result, "similarity_ratio", 0.0) or 0.0,
            },
        })

    return bug_items


class RAGAdapter:
    """
    Bridge Batch Fix <-> Fixer RAG
    - search_context(): search Fixer RAG để lấy top-k nguồn, ghép context string
    - add_fix(): import "Fix Case" vào Fixer RAG (/fixer-rag/import)
    """

    def __init__(self) -> None:
        self.svc = RAGService()

    def search_context(self, issues_data: List[RealBug]) -> Optional[str]:
        if not issues_data:
            return None
        query, filters = build_query_and_filters_from_issues(issues_data)
        logger.debug("RAG search query: %s with filters: %s", query[:100], filters)
        if not query:
            return None

        # Gọi đúng endpoint /fixer-rag/search
        res = self.svc.search_fixer(query=query, limit=8, filters=filters)
        if not (res.success and res.sources):
            logger.debug("Search fixer RAG failed, return: %s", {res.error_message or "No source found"})
            return None

        # Ghép thành đoạn context ngắn gọn cho prompt
        parts = ["\n=== RELEVANT CONTEXT FROM FIXER RAG ==="]
        for i, src in enumerate(res.sources[:3], 1):
            content = str(src.get("content", ""))[:400]
            sim = float(src.get("similarity_score", src.get("similarity", 0.0)) or 0.0)
            parts.append(f"\n{i}. Similar Item (Similarity: {sim:.2f}):")
            parts.append(f"{content}")
            md = src.get("metadata", {}) or {}
            if md.get("code_language"):
                parts.append(f"Language: {md['code_language']}")
        parts.append("\n=== END OF RAG CONTEXT ===\n")
        logger.debug(f"Retrieved context for prompt: {parts}")
        return "\n".join(parts)

    def add_fix(self, fix_result: FixResult, issues_data: List[RealBug], fixed_code: str) -> bool:
        """
        Import kết quả fix vào Fixer RAG qua hàm có sẵn: import_fix_cases(...).
        """
        bugs_payload = _build_bug_items_payload(fix_result, issues_data, fixed_code)
        res = self.svc.import_fix_cases(bugs_payload)
        return bool(getattr(res, "success", False))
