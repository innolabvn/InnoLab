from __future__ import annotations
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from src.app.services.log_service import logger
from src.app.services.cli_service import CLIService
from .base import Scanner

def _find_repo_root(start: Path) -> Path:
    cur = start.resolve()
    for _ in range(6):
        if (cur / "projects").exists():
            return cur
        if (cur / ".git").exists():
            return cur
        cur = cur.parent
    return start.resolve()

class BearerScanner(Scanner):
    """Scanner for loading Bearer scan results from Dockerized bearer/bearer."""

    def __init__(self, scan_directory: str):
        self.scan_directory = scan_directory

    def scan(self) -> List[Dict]:
        """Scan directory using Bearer and return list of issues"""
        logger.info("[EXECUTION FLOW] 🚀 Starting Bearer Scanner")
        logger.info(f"[EXECUTION FLOW] 📁 Target directory: {self.scan_directory}")
        try:
            logger.info("[BEARER SCAN] Starting Bearer security scan for directory: %s", self.scan_directory)
            
            repo_root = _find_repo_root(Path(__file__).parent)
            projects_root = Path(os.getenv("PROJECTS_ROOT", repo_root / "projects")).resolve()
            logger.debug("[BEARER SCAN] Projects root: %s", projects_root)

            # Resolve project_dir
            sd = Path(self.scan_directory)
            project_dir = sd if sd.is_absolute() else (projects_root / self.scan_directory).resolve()
            logger.info("[BEARER SCAN] Target project directory: %s", project_dir)

            if not project_dir.exists():
                msg = f"Project directory not found: {project_dir}"
                logger.error("[BEARER SCAN] %s", msg)
                return []

            # Output file in <projects_root>/bearer_results/
            bearer_results_dir = (projects_root / "bearer_results").resolve()
            bearer_results_dir.mkdir(parents=True, exist_ok=True)
            output_file = bearer_results_dir / f"bearer_results_{self.scan_directory}.json"
            logger.info("[BEARER SCAN] Output file will be: %s", output_file)
            
            try:
                if output_file.exists():
                    output_file.unlink()
                    logger.info("[BEARER SCAN] Removed existing Bearer results file: %s", output_file)
            except Exception as e:
                logger.warning("[BEARER SCAN] Failed to remove existing results file: %s", e)

            # Run dockerized bearer scan
            scan_cmd = [
                "docker", "run", "--rm",
                "-v", f"{str(project_dir)}:/scan",
                "-v", f"{str(bearer_results_dir)}:/output",
                "bearer/bearer:latest",
                "scan", "/scan",
                "--format", "json",
                "--output", f"/output/{output_file.name}",
                "--hide-progress-bar",
                "--skip-path", "node_modules,*.git,__pycache__,.venv,venv,dist,build"
            ]
            logger.info("[BEARER SCAN] Running Bearer Docker scan with command: %s", ' '.join(scan_cmd))
            logger.info("[EXECUTION FLOW] ⚡ Executing Bearer security scan...")
            success, output_lines = CLIService.run_command_stream(scan_cmd)
            logger.info(f"[EXECUTION FLOW] ✅ Bearer scan completed - success: {success}")

            # Bearer đôi khi trả exit code != 0 nhưng vẫn có file output
            logger.info("[BEARER SCAN] Docker scan completed with success=%s", success)
            
            if not success and not output_file.exists():
                logger.error("[BEARER SCAN] Bearer Docker scan failed and no output file generated")
                bearer_output = ''.join(output_lines)
                try:
                    import re
                    clean = re.sub(r'\x1b\[[0-9;]*m', '', bearer_output)
                except Exception:
                    clean = bearer_output
                logger.error("[BEARER SCAN] Bearer scan output: %s", clean[:1000])
                return []

            if not output_file.exists():
                logger.error("[BEARER SCAN] Bearer scan did not produce an output file")
                return []

            logger.info("[BEARER SCAN] Reading Bearer results from: %s", output_file)
            with output_file.open("r", encoding="utf-8") as f:
                bearer_data = json.load(f)
                logger.info("[BEARER SCAN] Raw bearer response keys: %s", list(bearer_data.keys()))
                logger.debug("[BEARER SCAN] Full bearer response: %s", str(bearer_data)[:2000])

            bugs = self._convert_bearer_to_bugs_format(bearer_data)
            logger.info("[BEARER SCAN] ✅ Found %d Bearer security issues", len(bugs))
            if bugs:
                logger.info("[BEARER SCAN] Sample bug: %s", str(bugs[0])[:500])
                logger.info("[BEARER SCAN] Bug severities: %s", [bug.get('severity') for bug in bugs[:5]])
            return bugs

        except json.JSONDecodeError as e:
            logger.error("[BEARER SCAN] ❌ Failed to parse Bearer JSON file: %s", e)
            return []
        except Exception as e:
            logger.error("[BEARER SCAN] ❌ Error during Bearer scan: %s", e)
            return []

    # ---- converters ----
    def _convert_bearer_to_bugs_format(self, bearer_data: Dict) -> List[Dict]:
        logger.info("[BEARER CONVERT] Converting Bearer data to bugs format")
        bugs: List[Dict] = []
        findings = []
        severity_levels = ["critical", "high", "medium", "low", "info"]
        
        for severity in severity_levels:
            severity_findings = bearer_data.get(severity, [])
            if severity_findings:
                logger.info("[BEARER CONVERT] Found %d %s severity findings", len(severity_findings), severity.upper())
            for finding in severity_findings:
                finding["severity"] = severity
                findings.append(finding)
        
        logger.info("[BEARER CONVERT] Total findings collected: %d", len(findings))
        logger.debug("[BEARER CONVERT] Sample findings: %s", str(findings[:3])[:500])

        for finding in findings:
            try:
                filename = finding.get("filename", finding.get("full_filename", "unknown"))
                if filename.startswith("/scan/"):
                    filename = filename[6:]
                elif filename.startswith("/"):
                    filename = filename[1:] if len(filename) > 1 else "unknown"

                line_number = finding.get("line_number", 1)

                id = finding.get("id")
                fingerprint = finding.get("fingerprint")
                title = finding.get("title", "No title")
                desc = finding.get("description", "")
                severity = finding.get("severity").upper()
                cwe_ids = finding.get("cwe_ids", [])
                code_extract = finding.get("code_extract", "")

                bug = {
                    "key": fingerprint,
                    "id": id,
                    "severity": severity,
                    "title": title,
                    "description": desc,
                    "file_name": filename,
                    "line_number": line_number,
                    "tags": cwe_ids,
                    "code_snippet": code_extract,
                }
                bugs.append(bug)
            except Exception as e:
                logger.warning("[BEARER CONVERT] Error processing Bearer finding: %s", e)
                logger.debug("[BEARER CONVERT] Problematic finding: %s", finding)
                continue

        logger.info("[BEARER CONVERT] ✅ Successfully converted %d findings to bug format", len(bugs))
        if bugs:
            logger.info("[BEARER CONVERT] Bug files: %s", list(set([bug.get('file_name') for bug in bugs[:10]])))
        return bugs
