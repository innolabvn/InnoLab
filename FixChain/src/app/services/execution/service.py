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
    scan_directory: str
    scan_modes: List[str]
    dify_cloud_api_key: Optional[str] = None


class ExecutionServiceNoMongo:
    """Execution Service không phụ thuộc MongoDB (dùng cho demo/CLI)."""

    def __init__(
        self,
        config: ExecutionConfig,
    ) -> None:
        self.cfg = config

        logger.info("Max iterations: %s", self.cfg.max_iterations)
        logger.info("Scan directory: %s", self.cfg.scan_directory)

        # Analyzer
        self.analysis_service = AnalysisService(dify_cloud_api_key=self.cfg.dify_cloud_api_key)
        # Scanner: Bearer
        self.scanner = BearerScanner(scan_directory=self.cfg.scan_directory)
        # Fixer: Gemini/LLM
        self.fixer = LLMFixer(self.cfg.scan_directory)

    def _resolve_scan_root(self) -> str:
        """Chuẩn hoá đường dẫn scan, không phụ thuộc sys.path hack."""
        scan_dir = self.cfg.scan_directory
        if os.path.isabs(scan_dir):
            return scan_dir
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../.."))
        project_root = os.getenv("PROJECT_ROOT") or os.path.abspath(os.path.join(repo_root, "projects"))
        return os.path.abspath(os.path.join(project_root, scan_dir))

    def read_source_code(self) -> str:
        """Đọc source code (gộp) để gửi kèm cho Dify (nếu cần)."""
        try:
            base = self._resolve_scan_root()
            if not os.path.isdir(base):
                logger.error("Scan directory not found: %s", base)
                return ""

            collected: List[str] = []
            logger.debug("Reading source code from directory: %s", base)
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
            full_code = "".join(collected)
            logger.debug(full_code[:50])
            return full_code
        except Exception as e:
            logger.error("Error reading source code: %s", e)
            return ""

    @staticmethod
    def _count_bug_types(bugs: List[Dict[str, str]]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for b in bugs:
            bug_type = str(b.get("severity", "")).upper()
            counts[bug_type] = counts.get(bug_type, 0) + 1
        counts["TOTAL"] = sum(v for k, v in counts.items() if k != "TOTAL")
        return counts

    def _log_execution_result(self, result: Dict[str, Any]) -> None:
        logger.info("===== EXECUTION RESULT =====")
        logger.info("Total bugs fixed: %s", result.get("total_bugs_fixed"))
        logger.info("Total iterations: %s", len(result.get("iterations", [])))
        logger.info("Start time: %s", result.get("start_time"))
        logger.info("End time: %s", result.get("end_time"))

        for i, it in enumerate(result.get("iterations", []), 1):
            logger.info(
                "Iteration %s: %s bugs found, %s file fixed",
                i, it.get("bugs_found"), it.get("fix_result", {}).get("fixed_count", 0)
            )

    def run(self) -> Dict[str, Any]:
        start = datetime.now()
        iterations: List[Dict[str, Any]] = []
        total_fixed = 0

        for it in range(1, self.cfg.max_iterations + 1):
            logger.info("===== ITERATION %s/%s =====", it, self.cfg.max_iterations)

            # Scan
            all_bugs: List[Dict[str, Any]] = []
            sb = self.scanner.scan()
            all_bugs.extend(sb)

            counts = self._count_bug_types(all_bugs)
            logger.debug("Bearer found: %s", counts)
            bugs_total = counts.get("TOTAL", 0)

            it_result: Dict[str, Any] = {
                "iteration": it,
                "bugs_found": bugs_total,
                "timestamp": datetime.now().isoformat(),
            }

            # Early exits
            if bugs_total == 0:
                it_result["fix_result"] = {
                    "success": True,
                    "fixed_count": 0,
                    "failed_count": 0,
                    "message": "No bugs found",
                }
                iterations.append(it_result)
                break

            # Gather source for Dify (nếu cần)
            source_code = self.read_source_code()

            # Phân tích với Dify
            analysis = self.analysis_service.analyze_bugs_with_dify(all_bugs, source_code=source_code)
            logger.debug("Dify analysis result: %s", str(analysis)[:100])
            it_result["analysis_result"] = analysis

            list_real_bugs = analysis.get("list_bugs")
            bugs_count = analysis.get("bugs_to_fix", 0)
            logger.info("Dify identified %s real bugs to fix", bugs_count)

            if isinstance(list_real_bugs, dict):
                list_real_bugs = [list_real_bugs]
            elif not isinstance(list_real_bugs, list):
                list_real_bugs = []

            # Không có bug thực sự để fix
            if not list_real_bugs or bugs_count == 0:
                it_result["fix_result"] = {
                    "success": True,
                    "fixed_count": 0,
                    "failed_count": 0,
                    "bug": 0,
                    "code_smell": bugs_total,
                    "message": "No real bugs identified for fixing after analysis",
                }
                iterations.append(it_result)
                break

            # Fix
            fix_results: List[Dict[str, Any]] = []
            raw = self.fixer.fix_bugs(list_real_bugs, bugs_count=bugs_count)
            if isinstance(raw, str):
                try:
                    fix_result = json.loads(raw.splitlines()[-1])
                    logger.debug(f"Fix result: {fix_result}")
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
            rescan.extend(self.scanner.scan())
            r_counts = self._count_bug_types(rescan)
            it_result["rescan_bugs_found"] = r_counts.get("CRITICAL", 0) + r_counts.get("HIGH", 0) + r_counts.get("MEDIUM", 0) + r_counts.get("LOW", 0)
            iterations.append(it_result)

            if it_result["rescan_bugs_found"] == 0:
                logger.info("All bugs resolved after rescan")
                break
            else:
                logger.info("Rescan found %s open bugs", it_result["rescan_bugs_found"])

        end = datetime.now()
        result: Dict[str, Any] = {
            "iterations": iterations,
            "total_bugs_fixed": total_fixed,
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "duration_seconds": (end - start).total_seconds(),
        }
        self._log_execution_result(result)
        return result
