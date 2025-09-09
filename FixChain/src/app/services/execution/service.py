from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.app.services.log_service import logger
from src.app.services.analysis_service import AnalysisService
from src.app.domains.scan import BearerScanner
from src.app.domains.fix import LLMFixer



@dataclass
class ExecutionConfig:
    max_iterations: int
    project_key: str
    scan_directory: str
    scan_modes: List[str]
    fix_modes: List[str]
    dify_cloud_api_key: Optional[str] = None


class ExecutionServiceNoMongo:
    """Execution Service không phụ thuộc MongoDB (dùng cho demo/CLI)."""

    def __init__(
        self,
        config: ExecutionConfig,
    ) -> None:
        self.cfg = config

        logger.info("Max iterations: %s", self.cfg.max_iterations)
        logger.info("Project key: %s", self.cfg.project_key)
        logger.info("Scan directory: %s", self.cfg.scan_directory)
        logger.info("Scan modes: %s", self.cfg.scan_modes)
        logger.info("Fix modes: %s", self.cfg.fix_modes)

        # Services
        self.analysis_service = AnalysisService(dify_cloud_api_key=self.cfg.dify_cloud_api_key)

        # Scanners
        self.scanners: List[Any] = []
        scanner_args: Dict[str, Dict[str, Any]] = {
            "bearer": {
                "project_key": self.cfg.project_key,
                "scan_directory": self.cfg.scan_directory,
            }
        }
        for mode in self.cfg.scan_modes:
            args = scanner_args.get(mode, {})
            self.scanners.append(BearerScanner(**args))

        # Fixers
        self.fixers: List[Any] = [LLMFixer(self.cfg.scan_directory)]

    # ---- Optional: mock-insert RAG dataset (no DB), giữ nguyên hành vi cũ
    def insert_rag_default(self) -> bool:
        logger.info("Validating default RAG dataset file...")
        dataset_path = os.getenv("RAG_DATASET_PATH")
        if not dataset_path:
            logger.error("RAG_DATASET_PATH must be set in environment")
            return False
        if not os.path.exists(dataset_path):
            logger.error("Dataset file not found: %s", dataset_path)
            return False
        logger.info("Dataset file validated: %s", dataset_path)
        return True

    def _resolve_scan_root(self) -> str:
        """Chuẩn hoá đường dẫn scan, không phụ thuộc sys.path hack."""
        scan_dir = self.cfg.scan_directory
        if os.path.isabs(scan_dir):
            return scan_dir
        # Nếu bạn muốn anchor vào repo root, có thể thay bằng logic khác:
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../.."))
        project_root = os.getenv("PROJECT_ROOT") or os.path.abspath(os.path.join(repo_root, "projects"))
        return os.path.abspath(os.path.join(project_root, scan_dir))

    def read_source_code(self, file_path: Optional[str] = None) -> str:
        """Đọc source code (gộp) để gửi kèm cho Dify (nếu cần)."""
        try:
            base = self._resolve_scan_root()
            if file_path:
                full_path = os.path.join(base, file_path)
                return open(full_path, "r", encoding="utf-8").read()

            if not os.path.isdir(base):
                logger.error("Scan directory not found: %s", base)
                return ""

            collected: List[str] = []
            logger.info("Reading source code from directory: %s", base)
            for root, _dirs, files in os.walk(base):
                for name in files:
                    if name.endswith((".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".cpp", ".c", ".h")):
                        fp = os.path.join(root, name)
                        try:
                            rel = os.path.relpath(fp, base).replace("\\", "/")
                            content = open(fp, "r", encoding="utf-8").read()
                            collected.append(f"// File: {rel}\n{content}\n\n")
                        except Exception as e:
                            logger.warning("Could not read %s: %s", fp, e)
            return "".join(collected)
        except Exception as e:
            logger.error("Error reading source code: %s", e)
            return ""

    @staticmethod
    def _count_bug_types(bugs: List[Dict[str, Any]]) -> Dict[str, int]:
        counts: Dict[str, int] = {"BUG": 0, "CODE_SMELL": 0, "VULNERABILITY": 0}
        for b in bugs:
            t = str(b.get("type", "UNKNOWN")).upper()
            counts[t] = counts.get(t, 0) + 1
        counts["TOTAL"] = sum(counts.get(k, 0) for k in counts if k != "TOTAL")
        return counts

    def _log_execution_result(self, result: Dict[str, Any]) -> None:
        logger.info("=== EXECUTION RESULT ===")
        logger.info("Project: %s", result.get("project_key"))
        logger.info("Total bugs fixed: %s", result.get("total_bugs_fixed"))
        logger.info("Total iterations: %s", len(result.get("iterations", [])))
        logger.info("Start time: %s", result.get("start_time"))
        logger.info("End time: %s", result.get("end_time"))

        for i, it in enumerate(result.get("iterations", []), 1):
            logger.info(
                "Iteration %s: %s bugs found, %s fixed",
                i, it.get("bugs_found"), it.get("fix_result", {}).get("fixed_count", 0)
            )

    def run(self, use_rag: bool = False) -> Dict[str, Any]:
        start = datetime.now()
        iterations: List[Dict[str, Any]] = []
        total_fixed = 0

        for it in range(1, self.cfg.max_iterations + 1):
            logger.info("===== ITERATION %s/%s =====", it, self.cfg.max_iterations)

            # Scan
            all_bugs: List[Dict[str, Any]] = []
            for mode, scanner in zip(self.cfg.scan_modes, self.scanners):
                sb = scanner.scan()
                logger.info("%s scanner found %s bugs", mode.upper(), len(sb))
                all_bugs.extend(sb)

            counts = self._count_bug_types(all_bugs)
            bugs_total = counts.get("TOTAL", 0)
            n_bug = counts.get("BUG", 0)
            n_smell = counts.get("CODE_SMELL", 0)

            logger.info(
                "Iteration %s: %s bugs total (%s BUG, %s CODE_SMELL)",
                it, bugs_total, n_bug, n_smell
            )

            it_result: Dict[str, Any] = {
                "iteration": it,
                "bugs_found": bugs_total,
                "bugs_type_bug": n_bug,
                "bugs_type_code_smell": n_smell,
                "timestamp": datetime.now().isoformat(),
            }

            # Early exits
            if bugs_total == 0:
                it_result["fix_result"] = {
                    "success": True,
                    "fixed_count": 0,
                    "failed_count": 0,
                    "bugs_remain": 0,
                    "bugs_type_bug": 0,
                    "bugs_type_code_smell": 0,
                    "message": "No bugs found",
                }
                iterations.append(it_result)
                break

            if n_bug == 0 and n_smell > 0:
                it_result["fix_result"] = {
                    "success": True,
                    "fixed_count": 0,
                    "failed_count": 0,
                    "bugs_remain": n_smell,
                    "bugs_type_bug": 0,
                    "bugs_type_code_smell": n_smell,
                    "message": f"Only code smell issues remain ({n_smell}), no bugs to fix",
                }
                iterations.append(it_result)
                break

            # Gather source for Dify (nếu cần)
            source_code = self.read_source_code()

            # Phân tích với Dify
            analysis = self.analysis_service.analyze_bugs_with_dify(
                all_bugs, use_rag=use_rag, source_code=source_code
            )
            it_result["analysis_result"] = analysis

            list_real_bugs = analysis.get("list_bugs")
            if isinstance(list_real_bugs, str):
                try:
                    list_real_bugs = json.loads(list_real_bugs)
                except Exception as e:
                    logger.error("Failed to parse list_bugs JSON: %s", e)
                    list_real_bugs = []
            if list_real_bugs is None:
                list_real_bugs = []

            # Không có bug thực sự để fix
            if not list_real_bugs or analysis.get("bugs_to_fix", 0) == 0:
                msg = "No real bugs identified for fixing after analysis" if not list_real_bugs else "Dify analysis reports no bugs to fix"
                it_result["fix_result"] = {
                    "success": True,
                    "fixed_count": 0,
                    "failed_count": 0,
                    "bugs_remain": bugs_total,
                    "bugs_type_bug": n_bug,
                    "bugs_type_code_smell": n_smell,
                    "message": msg,
                }
                iterations.append(it_result)
                break

            # Fix
            fix_results: List[Dict[str, Any]] = []
            for fixer in self.fixers:
                raw = fixer.fix_bugs(list_real_bugs, use_rag=use_rag)
                if isinstance(raw, str):
                    try:
                        fix_result = json.loads(raw.splitlines()[-1])
                    except json.JSONDecodeError:
                        logger.error("Failed to parse fix result JSON")
                        fix_result = {"success": False, "fixed_count": 0, "error": "Invalid JSON output"}
                else:
                    fix_result = raw

                fix_results.append(fix_result)
                if fix_result.get("success"):
                    total_fixed += fix_result.get("fixed_count", 0)
                else:
                    logger.error("Fix failed: %s", fix_result.get("error", "Unknown error"))

            it_result["fix_results"] = fix_results
            if fix_results:
                it_result["fix_result"] = fix_results[-1]

            # Re-scan xác thực
            rescan: List[Dict[str, Any]] = []
            for scanner in self.scanners:
                rescan.extend(scanner.scan())
            r_counts = self._count_bug_types(rescan)
            it_result["rescan_bugs_found"] = r_counts.get("TOTAL", 0)
            it_result["rescan_bugs_type_bug"] = r_counts.get("BUG", 0)
            it_result["rescan_bugs_type_code_smell"] = r_counts.get("CODE_SMELL", 0)

            logger.info(
                "Rescan found %s open bugs (%s BUG, %s CODE_SMELL)",
                it_result["rescan_bugs_found"],
                it_result["rescan_bugs_type_bug"],
                it_result["rescan_bugs_type_code_smell"],
            )

            iterations.append(it_result)

            if it_result["rescan_bugs_found"] == 0:
                logger.info("All bugs resolved after rescan")
                break

        end = datetime.now()
        result: Dict[str, Any] = {
            "project_key": self.cfg.project_key,
            "total_bugs_fixed": total_fixed,
            "iterations": iterations,
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "duration_seconds": (end - start).total_seconds(),
            "rag_enabled": bool(use_rag),
        }
        self._log_execution_result(result)
        return result
