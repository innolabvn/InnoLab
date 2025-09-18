# src/app/services/batch_fix/rag_integration.py
from __future__ import annotations
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from src.app.services.rag_service import RAGService
from src.app.services.batch_fix.models import FixResult
from src.app.services.log_service import logger

def build_query_and_filters_from_issues(issues_data: Optional[List[Dict]]) -> Tuple[str, Dict[str, str]]:
    """
    Tạo query và filters từ issues để search Fixer RAG.
    Issue format:
    {
        "key": str,
        "label": "BUG" | "CODE_SMELL",
        "id": str,
        "classification": str,
        "reason": str,
        "rule_description": str,
        "title": str,
        "file_name": str
    }
    Returns:
        query (str): chuỗi query ngắn gọn
        filters (dict): bộ lọc phù hợp (label, classification, file_name)
    """
    if not issues_data:
        return "", {}
    seen, terms = set(), []
    filters: Dict[str, str] = {}
    
    for it in issues_data:
        for k in ("title", "rule_description", "reason"):
            v = str(it.get(k, "")).strip()
            if v and v not in seen:
                seen.add(v)
                terms.append(v)
        
        if it.get("label") == "BUG":
            filters["label"] = "BUG"
        if str(it.get("classification", "")).lower() in ("true positive", "tp"):
            filters["classification"] = "True Positive"
        if it.get("file_name"):
            filters["file_name"] = str(it["file_name"]).strip()

    query = " | ".join(terms)[:1000]
    return query, filters

def _build_bug_items_payload(
    fix_result: FixResult,
    issues_data: Optional[List[Dict]],
    fixed_code: str,
) -> List[Dict]:
    """
    Map FixResult + issues_data -> payload 'bugs' theo schema BugItem của Fixer router.
    """
    file_path = fix_result.file_path or ""
    file_name = Path(file_path).name if file_path else "unknown file"

    # Mặc định
    severity = "MEDIUM"
    bug_type = "BUG"
    line_number = None
    labels: List[str] = []

    # Lấy thêm metadata từ issues_data cho khớp schema
    if issues_data:
        logger.debug("Building bug item payload from issues data: %s", issues_data)
        for it in issues_data:
            if str(it.get("component", "")).endswith(file_name):
                severity = str(it.get("severity", severity)).upper() or "MEDIUM"
                bug_type = str(it.get("type", bug_type)).upper() or "BUG"
                try:
                    if it.get("line") is not None:
                        line = it.get("line")
                        if line:
                            line_number = int(line)
                except Exception:
                    pass
                rule = str(it.get("rule") or "").strip()
                if rule and rule not in labels:
                    labels.append(rule)

    description = f"Fix applied to {file_name}. See metadata.fix_context and code_snippet."
    bug_item = {
        "name": f"Fix: {file_name}",
        "description": description,
        "type": bug_type,                 # "BUG" hoặc "CODE_SMELL"
        "severity": severity,             # INFO|LOW|MEDIUM|HIGH|CRITICAL (router yêu cầu)
        "file_path": file_path or None,
        "line_number": line_number,
        "code_snippet": fixed_code or None,
        "labels": labels,
        "project": None,
        "metadata": {
            "source": "FixChain",
            "agent": "fixer",
            "fix_context": {
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
            },
        },
    }
    return [bug_item]


class RAGAdapter:
    """
    Bridge Batch Fix <-> Fixer RAG
    - search_context(): search Fixer RAG để lấy top-k nguồn, ghép context string
    - add_fix(): import "Fix Case" vào Fixer RAG (/fixer-rag/import)
    """

    def __init__(self) -> None:
        self.svc = RAGService()

    def search_context(self, issues_data: Optional[List[Dict]]) -> Optional[str]:
        if not issues_data:
            return None
        query, filters = build_query_and_filters_from_issues(issues_data)
        logger.debug("RAG search query: %s with filters: %s", query[:100], filters)
        if not query:
            return None

        # Gọi đúng endpoint /fixer-rag/search
        res = self.svc.search_fixer(query=query, limit=8, filters=filters)
        if not (res.success and res.sources):
            logger.debug(f"Search fixer RAG failed, return: {res}")
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

    def add_fix(
        self,
        fix_result: FixResult,
        issues_data: Optional[List[Dict]],
        raw_response: str,   # giữ nguyên chữ ký hàm (không dùng ở đây)
        fixed_code: str,
    ) -> bool:
        """
        Import kết quả fix vào Fixer RAG qua hàm có sẵn: import_fix_cases(...).
        (Không thêm hàm mới ở RAGService.)
        """
        bugs_payload = _build_bug_items_payload(fix_result, issues_data, fixed_code)
        logger.debug("Importing fix case to RAG with payload: %s", bugs_payload)
        res = self.svc.import_fix_cases(bugs_payload=bugs_payload, generate_embeddings=True)
        return bool(res.success)
