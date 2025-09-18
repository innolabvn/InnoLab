# src\app\services\analysis_service.py
from __future__ import annotations
from collections import Counter
from dataclasses import asdict, dataclass, field
import json
import os
from typing import Dict, List, Any, TypedDict, Optional, Union, cast

from src.app.services.log_service import logger
from src.app.adapters.dify_client import run_workflow_with_dify, DifyRunResponse
from src.app.services.rag_service import RAGService, ScannerRAGSignal


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
        Flow:
         1) Upsert initial scanner signals from Bearer into scanner_rag.
         2) Retrieve context from scanner_rag (optional) and call Dify.
         3) Normalize Dify results, then update existing scanner_rag records with Dify analysis (label, dify_* fields).
            If a Dify item cannot be matched to an existing record and upsert_missing_on_dify=True, create it.
        """
        list_bugs: Union[List[Dict[str, Any]], Dict[str, Any], str] = []
        bugs_to_fix: int = 0

        try:
            api_key = self.dify_cloud_api_key
            if not api_key:
                logger.error("Dify API key is missing.")
                return {"success": False, "error": "Missing API key", "list_bugs": list_bugs, "bugs_to_fix": bugs_to_fix}
            
            # ---------------------------------------------------------
            # (0) Upsert raw scanner signals into Scanner RAG immediately
            # ---------------------------------------------------------
            try:
                self._upsert_initial_signals(bearer_report)
            except Exception as e:
                logger.warning("Initial upsert to Scanner RAG failed: %s", e)

            # ---------------------------------------------------------
            # (A) ONLY RETRIEVE from Scanner RAG for historical labels
            #     DO NOT WRITE ANYTHING before Dify labeling
            # ---------------------------------------------------------
            retrieved_context = ""
            try:
                q = self._build_scanner_query(bearer_report)
                res = self.rag.search_scanner(q, limit=8, filters={})
                if res and getattr(res, "success", True) and getattr(res, "sources", None):
                    retrieved_context = "\n".join(
                        f"- {str(s.get('description') or s.get('reason') or s.get('content',''))}" for s in res.sources
                    )[:8000]
                    logger.debug("Scanner RAG retrieved %s context docs for Dify.", str(res.sources)[:100])
            except Exception as e:
                logger.warning("Scanner RAG retrieval failed (non-fatal): %s", e)

            # ---------------------------------------------------------
            # (B) Call Dify with Bearer report + retrieved_context
            # ---------------------------------------------------------
            inputs = {
                "src": source_code or "",
                "report": json.dumps(bearer_report, ensure_ascii=False),
                "retrieved_context": retrieved_context,
            }

            logger.info("Sending %d bug(s) to Dify workflow.", len(bearer_report))
            response: DifyRunResponse = run_workflow_with_dify(api_key=api_key, inputs=inputs)
            logger.debug("Dify raw response: %s", str(response.raw)[:100])

            # Defensive parsing trên cấu trúc Dify
            outputs = self._safe_get_outputs(response)
            list_bugs = outputs.get("list_bugs", []) or []

            # ---------------------------------------------------------
            # (C) Post-process: count bugs to FIX & persist labeled items to Scanner RAG
            # ---------------------------------------------------------

            bugs_to_fix = self._count_fix_bugs(list_bugs)

            labeled_signals = self._normalize_labeled_signals(list_bugs)
            if labeled_signals:
                try:
                    self._apply_dify_updates(labeled_signals)
                    logger.info("Applied Dify updates to scanner RAG for %d items.", len(labeled_signals))
                except Exception as e:
                    logger.warning("Applying Dify updates failed (non-fatal): %s", e)

            msg = "No bugs to fix" if bugs_to_fix == 0 else f"Need to fix {bugs_to_fix} bugs"
            return {"success": True, "list_bugs": labeled_signals, "bugs_to_fix": bugs_to_fix, "message": msg}

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
        Build query string from Bearer report.
        """
        terms: List[str] = []
        for it in report or []:
            logger.debug("Processing Bearer report item for query: %s...", str(it)[:100])
            for k in ("key", "file_name", "tags", "code_snippet"):
                v = str(it.get(k, "")).strip()
                if v and v not in terms:
                    terms.append(v)
        # keep it short for embedding
        q = " | ".join(terms)[:1000]
        logger.debug("Built scanner query: %s...", q[:100])
        return q or "code quality issues"

    @staticmethod
    def _safe_get_outputs(response: DifyRunResponse) -> Dict[str, Any]:
        """
        Standardize extraction of outputs from Dify response.
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
    def _get_label(action: str) -> str:
        if "FIX" in action:
            return "BUG"
        elif "IGNORE" in action:
            return "CODE_SMELL"
        return "UNKNOWN"

    def _normalize_labeled_signals(self, list_bugs: Union[List[Any], Dict[str, Any], str]):
        """
        Convert Dify labeled result to a list of ScannerRAGSignal objects (preferred).
        Input: list_bugs is the direct output from Dify (list or {"bugs": [...]})
        This function DOES NOT expect bearer scan fields to be present.
        Returns: List[ScannerRAGSignal] when ScannerRAGSignal is available, otherwise a list of dicts (backwards compatible).
        """
        # items: List[ScannerRAGSignal] = []
        items: List[Dict[str, Any]] = []

        # Normalize records list shape
        if isinstance(list_bugs, dict) and isinstance(list_bugs.get("bugs"), list):
            records = cast(List[Dict[str, Any]], list_bugs["bugs"])
        elif isinstance(list_bugs, list):
            records = cast(List[Dict[str, Any]], list_bugs)
        else:
            return items

        for r in records:
            if not isinstance(r, dict):
                continue

            logger.debug("Processing Dify bug item: %s", r.get("bug_id", ""))
            try:
                action = r.get("action", "")
                bug_id = r.get("bug_id", "")
                classification = r.get("classification", "")
                reason = r.get("reason", "")
                rule_description = r.get("rule_description", "")
                rule_key = r.get("rule_key", "")
                label = self._get_label(action.upper())
                key = bug_id or rule_key or ""
                file_name = r.get("file_name", "")
                scan_res = {
                    "key": key,
                    "label": label,
                    "id": bug_id,
                    "classification": classification,
                    "reason": reason,
                    "rule_description": rule_description,
                    "title": rule_key if rule_key else rule_description[:120],
                    "file_name": file_name
                }
                items.append(scan_res)
            except Exception as e:
                logger.warning("Failed to normalize Dify item: %s ; item=%s", e, r)
                
        logger.debug("Normalized labeled signals from Dify: %s...", str(items)[:100])
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

    def _upsert_initial_signals(self, bearer_report: List[Dict[str, Any]]) -> None:
        """
        Upsert initial scanner signals from Bearer report into Scanner RAG.
        This is done before Dify analysis to ensure all signals are present.
        """
        if not bearer_report:
            return

        signals = []
        for it in bearer_report:
            try:
                signal = ScannerRAGSignal(
                    key=str(it.get("key") or ""),
                    id=str(it.get("id") or ""),
                    title=str(it.get("title") or "")[:120],
                    description=str(it.get("description") or "")[:1000],
                    code_snippet=str(it.get("code_snippet") or "")[:2000],
                    file_name=str(it.get("file_name") or "unknown"),
                    line_number= it.get("line_number" or ""),
                    severity=str(it.get("severity") or "").upper(),
                    tags=it.get("tags") or [],
                )
                if signal.key:
                    signals.append(signal)
            except Exception as e:
                logger.warning("Error processing Bearer report item for upsert: %s", e)
                continue

        if signals:
            docs = [asdict(s) for s in signals]
            res = self.rag.add_scanner_signals(docs)
            if not res.success:
                raise Exception(f"Failed to import scanner signals: {res.error_message}")
            logger.info("Upserted %d initial scanner signals to RAG.", len(docs))

    def _apply_dify_updates(self, labeled_signals: List[Dict], upsert_missing: bool = True) -> None:
        """
        Map each labeled_signal (ScannerRAGSignal or dict) to update operations on scanner_rag collection.
        Matching priority:
          1) key (preferred)
          2) id (bug_id)
        If matching record found -> update -> add dify_* fields + label
        If not found and upsert_missing True -> insert/upsert new record
        """
        # Convert any ScannerRAGSignal objects to dict documents
        docs: List[Dict[str, Any]] = []
        for s in labeled_signals:
            try:
                if isinstance(s, ScannerRAGSignal):
                    docs.append(s.to_document())
                elif isinstance(s, dict):
                    docs.append(s)
                else:
                    # best-effort cast
                    docs.append(cast(Dict[str, Any], s))
            except Exception as e:
                logger.warning("Failed to convert labeled signal to doc: %s ; sig=%s", e, s)

        # For each doc, try update via RAGService methods
        for doc in docs:
            try:
                key = doc.get("key", "")
                update_fields = {
                    "dify_bug_id": doc.get("id", ""),
                    "dify_label": doc.get("label"),
                    "dify_classification": doc.get("classification"),
                    "dify_reason": doc.get("reason"),
                }
                # remove None values
                update_fields = {k: v for k, v in update_fields.items() if v is not None}

                updated = False

                # Prefer update by key
                if key and hasattr(self.rag, "update_scanner_signal"):
                    try:
                        updated = self.rag.update_scanner_signal(key, update_fields)
                    except Exception as e:
                        logger.debug("Scanner RAG update failed for key=%s: %s", key, e)
                        updated = False

                # If no update method or update did not apply, try higher-level APIs
                if not updated:
                    if hasattr(self.rag, "upsert_scanner_signals"):
                        # create merged doc for upsert
                        merged = ScannerRAGSignal(**{**doc, **update_fields})
                        try:
                            self.rag.upsert_scanner_signals([merged])
                            updated = True
                        except Exception as e:
                            logger.debug("rag.upsert_scanner_signals failed for merged doc: %s", e)
                            updated = False
                    elif hasattr(self.rag, "add_scanner_signals"):
                        # try a best-effort update: add_scanner_signals may upsert
                        try:
                            self.rag.add_scanner_signals([ {**doc, **update_fields} ])
                            updated = True
                        except Exception as e:
                            logger.debug("rag.add_scanner_signals failed: %s", e)
                            updated = False

                # If still not updated and allowed, insert as new
                if not updated and upsert_missing:
                    try:
                        # build insert doc
                        if hasattr(self.rag, "add_scanner_signals"):
                            self.rag.add_scanner_signals([{**doc, **update_fields}])
                            updated = True
                        elif hasattr(self.rag, "upsert_scanner_signals"):
                            self.rag.upsert_scanner_signals([ScannerRAGSignal(**{**doc, **update_fields})])
                            updated = True
                        else:
                            # last resort: try update_scanner_signal with upsert param if supported
                            if hasattr(self.rag, "update_scanner_signal"):
                                try:
                                    self.rag.update_scanner_signal(key, {**doc, **update_fields})
                                    updated = True
                                except Exception:
                                    updated = False
                    except Exception as e:
                        logger.warning("Failed to insert missing Dify-updated doc into RAG: %s", e)

                logger.debug("Dify update applied for key=%s, updated=%s", key, updated)
            except Exception as e:
                logger.warning("Exception while applying Dify update to doc: %s ; doc=%s", e, doc)