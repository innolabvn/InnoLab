# src\app\services\analysis_service.py
from __future__ import annotations
import json
import os
from typing import Dict, List, Any, TypedDict, Optional, Union, cast

from src.app.services.log_service import logger
from src.app.adapters.dify_client import run_workflow_with_dify, DifyRunResponse
from src.app.services.rag_service import RAGService


class AnalysisResult(TypedDict, total=False):
    success: bool
    message: str
    error: str
    list_bugs: Union[List[Dict[str, Any]], Dict[str, Any], str]
    bugs_to_fix: int


class AnalysisService:
    """Service for analyzing bugs and interacting with Dify."""

    def __init__(self, dify_cloud_api_key: Optional[str] = None) -> None:
        # Fallback to env if not provided explicitly
        self.dify_cloud_api_key: str = (
            dify_cloud_api_key
            or os.getenv("DIFY_CLOUD_API_KEY", "").strip()
        )
        self.rag = RAGService()

    def count_bug_types(self, bugs: List[Dict[str, Any]]) -> Dict[str, int]:
        counts: Dict[str, int] = {"VULNERABILITY": 0}
        for bug in bugs:
            bug_type = str(bug.get("type", "UNKNOWN"))
            counts[bug_type] = counts.get(bug_type, 0) + 1
        counts["TOTAL"] = len(bugs)
        return counts

    def analyze_bugs_with_dify(
        self,
        bugs: List[Dict[str, Any]],
        use_rag: bool = False,
        source_code: str = "",
    ) -> AnalysisResult:
        """
        Gửi báo cáo bugs sang Dify workflow và rút ra số lượng bugs cần FIX.
        Optionally:
           - Lưu context phân tích vào RAG (agent=analysis)
           - Truy vấn RAG để lấy retrieved_context truyền cho workflow khi use_rag=True
        Returns:
            {
              "success": bool,
              "message": str,
              "list_bugs": list|dict|str,   # tuỳ Dify trả
              "bugs_to_fix": int,
              "error": str                   # khi thất bại
            }
        """
        list_bugs: Union[List[Dict[str, Any]], Dict[str, Any], str] = []
        bugs_to_fix: int = 0

        try:
            api_key = self.dify_cloud_api_key
            if not api_key:
                logger.error("Dify API key is missing. Set DIFY_CLOUD_API_KEY.")
                return {"success": False, "error": "Missing API key", "list_bugs": list_bugs, "bugs_to_fix": bugs_to_fix}

            # ---- (A) Lưu context vào RAG ----
            # 1) Tóm tắt ngắn report + snapshot source (tránh quá dài)
            try:
                collection = (os.getenv("SCANNER_RAG_COLLECTION", "kb_scanner_signals").strip() or None)
                self.rag.add_analysis_context(
                    report=bugs or [],
                    source_snippet=source_code[:4000],
                    project=os.getenv("PROJECT_NAME", None),
                    collection_name=collection,
                )
            except Exception as e:
                logger.warning("RAG (analysis) insert failed: %s", e)

            # ---- (B) Truy vấn RAG để lấy retrieved_context ----
            retrieved_context = ""
            if use_rag:
                try:
                    # Tạo query gọn gàng từ report
                    rule_descriptions = {str(b.get("rule_description", "")).strip() for b in (bugs or []) if b.get("rule_description")}
                    q = " ".join(list(rule_descriptions))[:1000] or json.dumps(bugs, ensure_ascii=False)[:1000]
                    collection = (os.getenv("SCANNER_RAG_COLLECTION", "").strip() or None)
                    result = self.rag.search_text(
                        text=q,
                        limit=5,
                        collection_name=collection,
                        filters={"metadata.agent": "analysis"},
                    )
                    if result.success and result.sources:
                        retrieved_context = "\n\n---\n".join([str(s.get("content", "")) for s in result.sources])
                except Exception as e:
                    logger.warning("RAG (analysis) search failed: %s", e)

            # ---- (C) Gọi Dify ----
            inputs = {
                "is_use_rag": "True" if use_rag else "False",
                "src": source_code,
                "report": json.dumps(bugs, ensure_ascii=False),
                "retrieved_context": retrieved_context,
            }
            logger.info("Sending %d bug(s) to Dify workflow (use_rag=%s).", len(bugs), use_rag)

            response: DifyRunResponse = run_workflow_with_dify(
                api_key=api_key,
                inputs=inputs,
                response_mode="blocking",
            )

            # Defensive parsing trên cấu trúc Dify
            outputs = self._safe_get_outputs(response)
            list_bugs = outputs.get("list_bugs", [])

            logger.debug("Dify outputs keys: %s", list(outputs.keys()))
            logger.debug("list_bugs type: %s", type(list_bugs).__name__)

            bugs_to_fix = self._count_fix_bugs(list_bugs)

            if bugs_to_fix == 0:
                return {
                    "success": True,
                    "bugs_to_fix": 0,
                    "list_bugs": list_bugs,
                    "message": "No bugs to fix",
                }

            return {
                "success": True,
                "list_bugs": list_bugs,
                "bugs_to_fix": bugs_to_fix,
                "message": f"Need to fix {bugs_to_fix} bugs",
            }

        except Exception as e:
            logger.error("Dify analysis error: %s", str(e))
            return {
                "success": False,
                "error": str(e),
                "list_bugs": list_bugs,
                "bugs_to_fix": bugs_to_fix,
            }

    # ---------------- Internal helpers ----------------

    @staticmethod
    def _safe_get_outputs(response: DifyRunResponse) -> Dict[str, Any]:
        """
        Chuẩn hoá việc rút outputs từ response của Dify, tránh KeyError/None.
        Kỳ vọng các dạng:
        {"data": {"outputs": {...}}}
        hoặc {"outputs": {...}}
        """
        if not isinstance(response, dict):
            return {}

        data = response.get("data")
        if isinstance(data, dict):
            outputs = data.get("outputs")
            if isinstance(outputs, dict):
                return cast(Dict[str, Any], outputs)

        outputs = response.get("outputs")
        if isinstance(outputs, dict):
            return cast(Dict[str, Any], outputs)

        return {}


    @staticmethod
    def _count_fix_bugs(list_bugs: Union[List[Any], Dict[str, Any], str]) -> int:
        """
        Đếm số bug có action chứa 'FIX' (không phân biệt hoa thường).
        Chấp nhận ba biến thể:
          - dict có key 'bugs_to_fix' → dùng trực tiếp
          - dict có key 'bugs' → duyệt list
          - list các bug → duyệt list
        """
        # 1) Nếu Dify đã trả thẳng "bugs_to_fix"
        if isinstance(list_bugs, dict):
            direct = list_bugs.get("bugs_to_fix")
            if isinstance(direct, (int, str)):
                try:
                    return int(direct)
                except (TypeError, ValueError):
                    pass  # fallback bên dưới

        # 2) Nếu là dict và có mảng "bugs"
        if isinstance(list_bugs, dict) and isinstance(list_bugs.get("bugs"), list):
            bugs_arr = list_bugs["bugs"]
            return sum(
                1
                for bug in bugs_arr
                if isinstance(bug, dict)
                and "action" in bug
                and "FIX" in str(bug.get("action", "")).upper()
            )

        # 3) Nếu là mảng các bug
        if isinstance(list_bugs, list):
            return sum(
                1
                for bug in list_bugs
                if isinstance(bug, dict)
                and "action" in bug
                and "FIX" in str(bug.get("action", "")).upper()
            )

        # 4) Không match định dạng nào
        return 0
