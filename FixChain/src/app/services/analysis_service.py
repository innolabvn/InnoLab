# src\app\services\analysis_service.py
from __future__ import annotations
from collections import Counter
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
        self.dify_cloud_api_key: str = dify_cloud_api_key or os.getenv("DIFY_CLOUD_API_KEY", "").strip()
        self.rag = RAGService()

    def count_bug_types(self, bugs: List[Dict[str, Any]]) -> Dict[str, int]:
        counts = Counter(bug.get("severity", "") for bug in bugs)
        counts["TOTAL"] = len(bugs)
        return dict(counts)

    def analyze_bugs_with_dify(
        self,
        bearer_report: List[Dict[str, Any]],
        source_code: str = "",
    ) -> AnalysisResult:
        """
        Gửi kết quả scan từ Bearer sang Dify workflow.
        Đồng thời: ghi nhanh signals vào Scanner RAG và search lại để lấy retrieved_context.
        """
        list_bugs: Union[List[Dict[str, Any]], Dict[str, Any], str] = []
        bugs_to_fix: int = 0

        try:
            api_key = self.dify_cloud_api_key
            if not api_key:
                logger.error("Dify API key is missing.")
                return {"success": False, "error": "Missing API key", "list_bugs": list_bugs, "bugs_to_fix": bugs_to_fix}

            # ---------------------------------------------------------
            # (A) ONLY RETRIEVE from Scanner RAG for historical labels
            #     DO NOT WRITE ANYTHING before Dify labeling
            # ---------------------------------------------------------
            retrieved_context = "" # Không dùng context cũ
            try:
                q = self._build_scanner_query(bearer_report)  # compact query from rule/message/component
                res = self.rag.search_scanner(q, limit=8, filters={})
                if res.success and res.sources:
                    retrieved_context = "\n".join(
                        f"- {str(s.get('content',''))}" for s in res.sources
                    )[:8000]
                    logger.debug("Scanner RAG retrieved %d context docs for Dify.", len(res.sources))
            except Exception as e:
                logger.warning("Scanner RAG retrieval failed (non-fatal): %s", e)

            # ---------------------------------------------------------
            # (B) Call Dify with Bearer report + retrieved_context
            # ---------------------------------------------------------
            inputs = {
                "is_use_rag": "True",
                "src": source_code or "",
                "report": json.dumps(bearer_report, ensure_ascii=False),
                "retrieved_context": retrieved_context,
            }

            logger.info("Sending %d bug(s) to Dify workflow.", len(bearer_report))
            response: DifyRunResponse = run_workflow_with_dify(api_key=api_key, inputs=inputs)
            logger.debug("Dify raw response: %s", response.raw)

            # Defensive parsing trên cấu trúc Dify
            outputs = self._safe_get_outputs(response)
            list_bugs = outputs.get("list_bugs", [])

            # ---------------------------------------------------------
            # (C) Post-process: count bugs to FIX & persist labeled items to Scanner RAG
            # ---------------------------------------------------------

            bugs_to_fix = self._count_fix_bugs(list_bugs)

            try:
                labeled_signals = self._normalize_labeled_signals(list_bugs)
                if labeled_signals:
                    self.rag.add_scanner_signals(labeled_signals)
                    logger.info("Persisted %d labeled scanner signals to RAG.", len(labeled_signals))
            except Exception as e:
                logger.warning("Persist labeled signals failed (non-fatal): %s", e)

            msg = "No bugs to fix" if bugs_to_fix == 0 else f"Need to fix {bugs_to_fix} bugs"
            return {"success": True, "list_bugs": list_bugs, "bugs_to_fix": bugs_to_fix, "message": msg}

        except Exception as e:
            logger.error("Dify analysis error: %s", str(e))
            return {
                "success": False,
                "error": str(e),
                "list_bugs": list_bugs,
                "bugs_to_fix": bugs_to_fix,
            }

    # ---------------- Internal helpers ----------------
    def _build_scanner_query(self, report: List[Dict[str, Any]]) -> str:
        """
        Build concise OR-like query string from Bearer report.
        Prefer rule / description / message / component.
        """
        terms: List[str] = []
        for it in report or []:
            for k in ("rule", "description", "message", "component"):
                v = str(it.get(k, "")).strip()
                if v and v not in terms:
                    terms.append(v)
        # keep it short for embedding
        q = " | ".join(terms)[:1000]
        return q or "code quality issues"

    @staticmethod
    def _safe_get_outputs(response: DifyRunResponse) -> Dict[str, Any]:
        """
        Chuẩn hoá việc rút outputs từ response của Dify, tránh KeyError/None.
        Kỳ vọng các dạng:
        {"data": {"outputs": {...}}}
        hoặc {"outputs": {...}}
        """
        if not response:
            return {}

        data = response.raw.get("data")  # raw để chắc chắn lấy dict gốc
        if isinstance(data, dict):
            outputs = data.get("outputs")
            if isinstance(outputs, dict):
                return cast(Dict[str, Any], outputs)

        outputs = response.raw.get("outputs")
        if isinstance(outputs, dict):
            return cast(Dict[str, Any], outputs)

        return {}
    
    @staticmethod
    def _infer_label(item: Dict[str, Any]) -> str:
        """
        Infer BUG vs CODE_SMELL from Dify output fields.
        Accepts keys like: action ('FIX'/'IGNORE'), label ('BUG'/'CODE_SMELL'), or boolean flags.
        """
        # Highest priority: explicit label
        label = str(item.get("label", "")).upper()
        if label in ("BUG", "CODE_SMELL"):
            return label
        # Next: action implies bug-to-fix
        action = str(item.get("action", "")).upper()
        if "FIX" in action:
            return "BUG"
        if "IGNORE" in action or "SKIP" in action:
            return "CODE_SMELL"
        # Fallback: severity heuristic (MEDIUM+ => BUG)
        sev = str(item.get("severity", "")).upper()
        if sev in ("CRITICAL", "HIGH", "MEDIUM"):
            return "BUG"
        return "CODE_SMELL"

    def _normalize_labeled_signals(self, list_bugs: Union[List[Any], Dict[str, Any], str]) -> List[Dict[str, Any]]:
        """
        Convert Dify labeled result to ScannerRAG import items:
          { text, label: BUG|CODE_SMELL, id?, lang?, source='dify' }
        """
        items: List[Dict[str, Any]] = []

        # Dict variant: {"bugs": [...]}
        if isinstance(list_bugs, dict) and isinstance(list_bugs.get("bugs"), list):
            records = cast(List[Dict[str, Any]], list_bugs["bugs"])
        elif isinstance(list_bugs, list):
            records = cast(List[Dict[str, Any]], list_bugs)
        else:
            return items

        for r in records:
            if not isinstance(r, dict):
                continue
            description = str(r.get("description"))[:1000]
            if not description:
                continue
            items.append({
                "description": description,
                "label": self._infer_label(r),
                "id": str(r.get("bug_id") or ""),
                "source": "dify",
            })
        return items

    @staticmethod
    def _count_fix_bugs(list_bugs: Union[List[Any], Dict[str, Any], str]) -> int:
        # Support {"bugs_to_fix": N}
        if isinstance(list_bugs, dict):
            direct = list_bugs.get("bugs_to_fix")
            if isinstance(direct, (int, str)):
                try:
                    return int(direct)
                except (TypeError, ValueError):
                    pass
        # Support {"bugs": [...]}
        if isinstance(list_bugs, dict) and isinstance(list_bugs.get("bugs"), list):
            return sum(1 for bug in list_bugs["bugs"]
                       if isinstance(bug, dict) and "FIX" in str(bug.get("action", "")).upper())
        # Support simple list
        if isinstance(list_bugs, list):
            return sum(1 for bug in list_bugs
                       if isinstance(bug, dict) and "FIX" in str(bug.get("action", "")).upper())
        return 0
