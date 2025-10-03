# src\app\services\analysis_service.py
from __future__ import annotations
from collections import Counter
from dataclasses import asdict, dataclass, field
import json
import os
from typing import Dict, List, Any, TypedDict, Optional, Union, cast

from src.app.domains.fix.models import RealBug
from src.app.services.log_service import logger
from src.app.adapters.dify_client import run_workflow_with_dify, DifyRunResponse
from src.app.services.rag_service import RAGService, ScannerRAGSignal

class AnalysisResult(TypedDict, total=False):
    success: bool
    message: str
    error: str
    list_bugs: List[RealBug]
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
                return {"success": False, "error": "Missing API key", "list_bugs": [], "bugs_to_fix": 0}
            
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
            logger.debug("Dify raw response: %s", response.raw)

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
                "list_bugs": [],
                "bugs_to_fix": 0,
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
        if "FIX" or "TRUE POSITIVE" or "Fix" in action:
            return "BUG"
        elif "IGNORE" or "FALSE POSITIVE" or "Ignore" in action:
            return "CODE SMELL"
        return "UNKNOWN"

    def _normalize_labeled_signals(self, list_bugs: Union[List[Any], Dict[str, Any], str]):
        """
        Convert Dify labeled result to a list of ScannerRAGSignal objects (preferred).
        Input: list_bugs is the direct output from Dify (list or {"bugs": [...]})
        This function DOES NOT expect bearer scan fields to be present.
        Returns: List[ScannerRAGSignal] when ScannerRAGSignal is available, otherwise a list of dicts (backwards compatible).
        Dify response sample:
        {
            "action": "Fix",
            "key": "65c9c2496677f21552e48b34c59791e4_0",
            "classification": "True Positive",
            "reason": "RAG: Usage of weak hashing library (MDx).  The code uses hashlib.md5, which is a weak hashing algorithm.",
            "id": "python_lang_weak_hash_md5",
            "title": "Usage of weak hashing library (MDx)",
            "file_name": "app.py",
            "lang": "python",
            "code_snippet": "    pwd_hash = hashlib.md5(password.encode()).hexdigest()",
            "line_number": "48",
            "severity": "MEDIUM"
          },
        """
        items: List[RealBug] = []

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

            logger.debug("Processing Dify bug item: %s", r.get("key", ""))
            try:
                action = r.get("action", "")
                key = r.get("key", "")
                classification = r.get("classification", "")
                reason = r.get("reason", "")
                id = r.get("id", "")
                title = r.get("title", "")
                file_name = r.get("file_name", "")
                lang = r.get("lang", "")
                code_snippet = r.get("code_snippet", "")
                line_number = r.get("line_number", "")
                severity = r.get("severity", "")
                label = self._get_label(str(action).upper())
                scan_res = RealBug(
                    key = key,
                    label = label,
                    id = id,
                    classification = classification,
                    reason = reason,
                    title = title,
                    lang = lang,
                    file_name = file_name,
                    code_snippet = code_snippet,
                    line_number = line_number,
                    severity = severity
                )
                items.append(scan_res)
            except Exception as e:
                logger.warning("Failed to normalize Dify item: %s ; item=%s", e, r)

        logger.debug("Normalized labeled signals from Dify: %s", items.pop)
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

    def _safe_int(self, v: Any) -> Optional[int]:
        try:
            return int(v)
        except Exception:
            return None

    def _norm_classification(self, s: Optional[str]) -> Optional[str]:
        if not s:
            return None
        sl = s.strip().lower()
        if sl in {"tp", "true positive"}:
            return "True Positive"
        if sl in {"fp", "false positive"}:
            return "False Positive"
        return s

    def _rb_to_scanner_signal(self, rb: "RealBug") -> "ScannerRAGSignal":
        # Build a minimal yet valid ScannerRAGSignal for upsert/insert
        return ScannerRAGSignal(
            key=rb.key or rb.id,  # ensure key is populated; prefer key
            id=rb.id,
            title=rb.title or (rb.id or rb.key),
            description=rb.reason or rb.title or "",
            code_snippet=rb.code_snippet or "",
            file_name=rb.file_name or None,
            line_number=self._safe_int(rb.line_number),
            severity=rb.severity or None,
            tags=[t for t in {rb.label, rb.severity} if t],  # store label/severity as tags
            # Dify metadata
            dify_bug_id=rb.id,
            dify_classification=self._norm_classification(rb.classification),
            dify_reason=rb.reason or None,
        )

    def _apply_dify_updates(self, labeled_signals: List["RealBug"], upsert_missing: bool = True) -> None:
        """
        Apply Dify-labeled results into Scanner RAG.
        Matching priority:
        1) key (preferred)
        2) id (fallback if your RAG supports it)
        If matching record is found -> update with dify_* fields (and optionally core fields).
        If not found and upsert_missing=True -> insert/upsert a new ScannerRAGSignal.
        """
        if not labeled_signals:
            return

        for rb in labeled_signals:
            try:
                key = getattr(rb, "key", None)
                bug_id = getattr(rb, "id", None)

                # Only Dify-* update fields here; don't invent unknown fields like "dify_label"
                update_fields: Dict[str, Any] = {
                    "dify_bug_id": bug_id,
                    "dify_classification": self._norm_classification(getattr(rb, "classification", None)),
                    "dify_reason": getattr(rb, "reason", None),
                }
                # prune Nones
                update_fields = {k: v for k, v in update_fields.items() if v is not None}

                updated = False

                # Prefer update by key
                if key and hasattr(self.rag, "update_scanner_signal"):
                    try:
                        updated = bool(self.rag.update_scanner_signal(key, update_fields))
                    except Exception as e:
                        logger.debug("Scanner RAG update by key failed (key=%s): %s", key, e)
                        updated = False

                # Upsert/Insert if still not updated
                if not updated and upsert_missing:
                    merged_sig = self._rb_to_scanner_signal(rb)

                    # Prefer typed upsert API
                    if hasattr(self.rag, "upsert_scanner_signals"):
                        try:
                            self.rag.upsert_scanner_signals([merged_sig])
                            updated = True
                        except Exception as e:
                            logger.debug("rag.upsert_scanner_signals failed: %s", e)
                            updated = False

                    # Fallback to add API (dict payload)
                    if not updated and hasattr(self.rag, "add_scanner_signals"):
                        try:
                            self.rag.add_scanner_signals([asdict(merged_sig)])
                            updated = True
                        except Exception as e:
                            logger.debug("rag.add_scanner_signals failed: %s", e)
                            updated = False

                    # Last resort: try an update method that can upsert if supported
                    if not updated and hasattr(self.rag, "update_scanner_signal"):
                        try:
                            # use the merged doc as update body
                            self.rag.update_scanner_signal(merged_sig.key, asdict(merged_sig))
                            updated = True
                        except Exception:
                            updated = False

                logger.debug("Dify update applied for key=%s, updated=%s", key, updated)

            except Exception as e:
                logger.warning("Exception while applying Dify update; bug=%s ; err=%s", rb, e)
