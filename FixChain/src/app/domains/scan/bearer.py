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
        try:
            logger.debug("Scan directory: %s", self.scan_directory)

            repo_root = _find_repo_root(Path(__file__).parent)
            projects_root = Path(os.getenv("PROJECTS_ROOT", repo_root / "projects")).resolve()

            # Resolve project_dir
            sd = Path(self.scan_directory)
            project_dir = sd if sd.is_absolute() else (projects_root / self.scan_directory).resolve()

            if not project_dir.exists():
                msg = f"Project directory not found: {project_dir}"
                logger.error(msg)
                return []

            # Output file in <projects_root>/bearer_results/
            bearer_results_dir = (projects_root / "bearer_results").resolve()
            bearer_results_dir.mkdir(parents=True, exist_ok=True)
            output_file = bearer_results_dir / f"bearer_results_{self.scan_directory}.json"
            try:
                if output_file.exists():
                    output_file.unlink()
                    logger.info("Removed existing Bearer results file: %s", output_file)
            except Exception as e:
                logger.warning("Failed to remove existing results file: %s", e)

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
            logger.info("Running Bearer Docker scan")
            success, output_lines = CLIService.run_command_stream(scan_cmd)

            # Bearer đôi khi trả exit code != 0 nhưng vẫn có file output
            if not success and not output_file.exists():
                logger.error("Bearer Docker scan failed")
                bearer_output = ''.join(output_lines)
                try:
                    import re
                    clean = re.sub(r'\x1b\[[0-9;]*m', '', bearer_output)
                except Exception:
                    clean = bearer_output
                logger.debug("Bearer scan output: %s", clean[:100])
                return []

            if not output_file.exists():
                logger.error("Bearer scan did not produce an output file")
                return []

            logger.debug("Reading Bearer results from: %s", output_file)
            with output_file.open("r", encoding="utf-8") as f:
                bearer_data = json.load(f)
                logger.debug(f"Raw bearer response: {bearer_data}")

            bugs = self._convert_bearer_to_bugs_format(bearer_data)
            logger.info("Found %d Bearer security issues", len(bugs))
            if bugs:
                logger.debug("Sample bug: %s", bugs[0])
            return bugs

        except json.JSONDecodeError as e:
            logger.error("Failed to parse Bearer JSON file: %s", e)
            return []
        except Exception as e:
            logger.error("Error during Bearer scan: %s", e)
            return []

    # ---- converters ----
    def _convert_bearer_to_bugs_format(self, bearer_data: Dict) -> List[Dict]:
        bugs: List[Dict] = []
        findings = []
        severity_levels = ["critical", "high", "medium", "low", "info"]
        
        for severity in severity_levels:
            for finding in bearer_data.get(severity, []):
                finding["severity"] = severity
                findings.append(finding)
        logger.debug(f"Total findings collected: {str(findings)[:100]}")

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
                logger.warning("Error processing Bearer finding: %s", e)
                logger.debug("Problematic finding: %s", finding)
                continue

        return bugs
