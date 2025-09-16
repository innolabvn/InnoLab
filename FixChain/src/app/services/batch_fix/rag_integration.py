# src/app/services/batch_fix/rag_integration.py
from __future__ import annotations
from typing import Dict, List, Optional
from pathlib import Path
from src.app.services.rag_service import RAGService
from src.app.services.batch_fix.models import FixResult

def _build_query_from_issues(issues_data: Optional[List[Dict]]) -> str:
    """
    Tạo query ngắn gọn từ issues để search Fixer RAG.
    Ưu tiên: description, message, title, component.
    """
    if not issues_data:
        return ""
    seen, terms = set(), []
    for it in issues_data:
        for k in ("description", "message", "title"):
            v = str(it.get(k, "")).strip()
            if v and v not in seen:
                seen.add(v)
                terms.append(v)
    return " | ".join(terms)[:1000]

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
        query = _build_query_from_issues(issues_data)
        if not query:
            return None

        # Gọi đúng endpoint /fixer-rag/search
        res = self.svc.search_fixer(query=query, limit=3, filters=None)
        if not (res.success and res.sources):
            return None

        # Ghép thành đoạn context ngắn gọn cho prompt
        parts = ["\n=== RELEVANT CONTEXT FROM FIXER RAG ==="]
        for i, src in enumerate(res.sources[:3], 1):
            content = str(src.get("content", ""))[:400]
            sim = float(src.get("similarity_score", src.get("similarity", 0.0)) or 0.0)
            parts.append(f"\n{i}. Similar Item (Similarity: {sim:.2f}):")
            parts.append(f"   {content}...")
            md = src.get("metadata", {}) or {}
            if md.get("code_language"):
                parts.append(f"   Language: {md['code_language']}")
        parts.append("\n=== END OF RAG CONTEXT ===\n")
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
        res = self.svc.import_fix_cases(bugs_payload=bugs_payload, collection_name=None, generate_embeddings=True)
        return bool(res.success)
