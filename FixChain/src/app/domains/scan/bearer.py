from __future__ import annotations
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from FixChain.src.app.services.log_service import logger
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

    def __init__(self, project_key: str, scan_directory: str):
        self.project_key = project_key
        self.scan_directory = scan_directory

    def scan(self) -> List[Dict]:
        try:
            logger.info("Starting Bearer scan for project_key=%s", self.project_key)

            repo_root = _find_repo_root(Path(__file__).parent)
            projects_root = Path(os.getenv("PROJECTS_ROOT", repo_root / "projects")).resolve()

            # Resolve project_dir
            sd = Path(self.scan_directory)
            if sd.is_absolute():
                project_dir = sd
            else:
                # ưu tiên dưới projects_root
                project_dir = (projects_root / self.scan_directory).resolve()

            if not project_dir.exists():
                msg = f"Project directory not found: {project_dir}"
                logger.error(msg)
                return []

            # Output file in <projects_root>/bearer_results/
            bearer_results_dir = (projects_root / "bearer_results").resolve()
            bearer_results_dir.mkdir(parents=True, exist_ok=True)
            output_file = bearer_results_dir / f"bearer_results_{self.project_key}.json"
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
                logger.error("Bearer scan output: %s", clean[:1000])
                return []

            if not output_file.exists():
                logger.error("Bearer scan did not produce an output file")
                return []

            logger.info("Reading Bearer results from: %s", output_file)
            with output_file.open("r", encoding="utf-8") as f:
                bearer_data = json.load(f)

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

        if "findings" in bearer_data:
            findings = bearer_data.get("findings", [])
        else:
            severity_levels = ["critical", "high", "medium", "low", "info"]
            for severity in severity_levels:
                for finding in bearer_data.get(severity, []):
                    finding["severity"] = severity
                    findings.append(finding)

        for finding in findings:
            try:
                filename = finding.get("filename", finding.get("full_filename", "unknown"))
                if filename.startswith("/scan/"):
                    filename = filename[6:]
                elif filename.startswith("/"):
                    filename = filename[1:] if len(filename) > 1 else "unknown"

                line_number = finding.get("line_number", 1)
                src = finding.get("source")
                if isinstance(src, dict):
                    line_number = src.get("start", src.get("line", line_number))
                elif isinstance(src, int):
                    line_number = src

                rule_id = finding.get("id", finding.get("rule_id", "bearer_security_issue"))
                fingerprint = finding.get("fingerprint", hash(str(finding)) & 0x7FFFFFFF)
                unique_key = f"bearer_{rule_id}_{fingerprint}"

                title = finding.get("title", finding.get("rule_title", "Security vulnerability"))
                desc = finding.get("description", finding.get("rule_description", ""))

                if desc:
                    msg = f"{title}. {desc[:200]}..." if len(desc) > 200 else f"{title}. {desc}"
                else:
                    msg = title

                severity = (finding.get("severity", "medium") or "medium").lower()
                cwe_ids = finding.get("cwe_ids", finding.get("cwe", []))
                if isinstance(cwe_ids, str):
                    cwe_ids = [cwe_ids]

                rule_type = finding.get("type", "security")
                confidence = finding.get("confidence", "medium")

                bug = {
                    "key": unique_key,
                    "rule": rule_id,
                    "severity": self._map_bearer_severity(severity),
                    "component": filename,
                    "line": line_number,
                    "message": msg.strip(),
                    "status": "OPEN",
                    "type": "VULNERABILITY",
                    "effort": "15min" if severity in ["critical", "high"] else "10min",
                    "debt": "15min" if severity in ["critical", "high"] else "10min",
                    "tags": [
                        "security",
                        "bearer",
                        severity,
                        rule_type,
                        confidence,
                        *[f"cwe-{cwe}" for cwe in cwe_ids],
                    ],
                    "creationDate": datetime.now().isoformat(),
                    "updateDate": datetime.now().isoformat(),
                    "textRange": {
                        "startLine": line_number,
                        "endLine": line_number,
                        "startOffset": self._extract_column_start(finding),
                        "endOffset": self._extract_column_end(finding),
                    },
                }
                bugs.append(bug)
            except Exception as e:
                logger.warning("Error processing Bearer finding: %s", e)
                logger.debug("Problematic finding: %s", finding)
                continue

        return bugs

    def _extract_column_start(self, finding: Dict) -> int:
        src = finding.get("source")
        if isinstance(src, dict):
            col = src.get("column")
            if isinstance(col, dict):
                return int(col.get("start", 0))
            if isinstance(col, int):
                return col
            return int(src.get("start_column", src.get("column_start", 0)))
        return 0

    def _extract_column_end(self, finding: Dict) -> int:
        src = finding.get("source")
        if isinstance(src, dict):
            col = src.get("column")
            if isinstance(col, dict):
                return int(col.get("end", 0))
            if isinstance(col, int):
                return col + 1
            return int(src.get("end_column", src.get("column_end", 0)))
        return 0

    def _map_bearer_severity(self, s: str) -> str:
        m = {
            "critical": "BLOCKER",
            "high": "CRITICAL",
            "medium": "MAJOR",
            "low": "MINOR",
            "info": "INFO",
            "warning": "MINOR",
            "error": "CRITICAL",
            "CRITICAL": "BLOCKER",
            "HIGH": "CRITICAL",
            "MEDIUM": "MAJOR",
            "LOW": "MINOR",
            "INFO": "INFO",
            "WARNING": "MINOR",
            "ERROR": "CRITICAL",
        }
        return m.get(s, "MAJOR")
