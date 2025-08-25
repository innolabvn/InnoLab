from __future__ import annotations
import json
import os
from datetime import datetime
from typing import Dict, List

from utils.logger import logger
from .base import Scanner


class BearerScanner(Scanner):
    """Scanner for loading Bearer scan results."""

    def __init__(self, project_key: str):
        self.project_key = project_key

    def scan(self) -> List[Dict]:
        try:
            logger.info(
                f"Loading Bearer scan results for project: {self.project_key}"
            )
            innolab_root = os.getenv("INNOLAB_ROOT_PATH", "d:\\InnoLab")
            sonar_dir = os.path.join(innolab_root, "SonarQ")
            bearer_results_path = os.path.join(
                sonar_dir,
                "bearer_results",
                f"bearer_results_{self.project_key}.json",
            )

            if not os.path.exists(bearer_results_path):
                logger.error(
                    f"Bearer results file not found: {bearer_results_path}"
                )
                logger.info(
                    "Please run Bearer scan first to generate results file"
                )
                logger.info(
                    "Example: docker run --rm -v /path/to/project:/scan -v /path/to/output:/output bearer/bearer:latest scan /scan --format json --output /output/bearer_results_my-service.json"
                )
                return []

            logger.info(
                f"Reading Bearer scan results from: {bearer_results_path}"
            )
            with open(bearer_results_path, "r", encoding="utf-8") as f:
                bearer_data = json.load(f)
            logger.info("Bearer scan results loaded successfully")
            bugs = self._convert_bearer_to_bugs_format(bearer_data)
            logger.info(f"Found {len(bugs)} Bearer security issues")
            return bugs
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Bearer JSON file: {e}")
            return []
        except Exception as e:
            logger.error(f"Error reading Bearer scan results: {e}")
            return []

    def _convert_bearer_to_bugs_format(self, bearer_data: Dict) -> List[Dict]:
        """Convert Bearer scan results to compatible bugs format."""
        bugs: List[Dict] = []
        severity_levels = ["critical", "high", "medium", "low", "info"]
        for severity in severity_levels:
            findings = bearer_data.get(severity, [])
            for finding in findings:
                filename = finding.get("filename", finding.get("full_filename", "unknown"))
                if filename.startswith("/scan/"):
                    filename = filename[6:]
                line_number = finding.get("line_number", 1)
                if "source" in finding and "start" in finding["source"]:
                    line_number = finding["source"]["start"]
                rule_id = finding.get("id", "bearer_security_issue")
                fingerprint = finding.get(
                    "fingerprint", hash(str(finding)) & 0x7FFFFFFF
                )
                unique_key = f"bearer_{rule_id}_{fingerprint}"
                title = finding.get("title", "Security vulnerability")
                description = finding.get("description", "")
                message = (
                    f"{title}. {description[:200]}..."
                    if len(description) > 200
                    else f"{title}. {description}"
                )
                cwe_ids = finding.get("cwe_ids", [])
                bug = {
                    "key": unique_key,
                    "rule": rule_id,
                    "severity": self._map_bearer_severity(severity),
                    "component": filename,
                    "line": line_number,
                    "message": message.strip(),
                    "status": "OPEN",
                    "type": "VULNERABILITY",
                    "effort": "15min" if severity in ["critical", "high"] else "10min",
                    "debt": "15min" if severity in ["critical", "high"] else "10min",
                    "tags": [
                        "security",
                        "bearer",
                        severity,
                        *[f"cwe-{cwe}" for cwe in cwe_ids],
                    ],
                    "creationDate": datetime.now().isoformat(),
                    "updateDate": datetime.now().isoformat(),
                    "textRange": {
                        "startLine": line_number,
                        "endLine": line_number,
                        "startOffset": finding.get("source", {})
                        .get("column", {})
                        .get("start", 0)
                        if "source" in finding
                        else 0,
                        "endOffset": finding.get("source", {})
                        .get("column", {})
                        .get("end", 0)
                        if "source" in finding
                        else 0,
                    },
                }
                bugs.append(bug)
        return bugs

    def _map_bearer_severity(self, bearer_severity: str) -> str:
        severity_map = {
            "CRITICAL": "BLOCKER",
            "HIGH": "CRITICAL",
            "MEDIUM": "MAJOR",
            "LOW": "MINOR",
            "INFO": "INFO",
        }
        return severity_map.get(bearer_severity.upper(), "MAJOR")
