from __future__ import annotations
import json
import os
import time
from datetime import datetime
from typing import Dict, List

from utils.logger import logger
from .cli_service import CLIService


class Scanner:
    """Base scanner interface"""

    def scan(self) -> List[Dict]:
        """Run scan and return list of bugs"""
        raise NotImplementedError


class BearerScanner(Scanner):
    """Scanner for loading Bearer scan results"""

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
        """Convert Bearer scan results to compatible bugs format"""
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
                    "scanner": "bearer",
                    "bearer_severity": severity,
                    "cwe_ids": cwe_ids,
                    "documentation_url": finding.get("documentation_url", ""),
                    "code_extract": finding.get("code_extract", ""),
                }
                bugs.append(bug)
        logger.info(
            f"Converted {len(bugs)} Bearer findings to compatible format"
        )
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


class SonarQScanner(Scanner):
    """Scanner for SonarQube projects"""

    def __init__(self, project_key: str, scan_directory: str, sonar_token: str):
        self.project_key = project_key
        self.scan_directory = scan_directory
        self.sonar_token = sonar_token

    def scan(self) -> List[Dict]:
        try:
            logger.info(
                f"Starting SonarQube scan for project: {self.project_key}"
            )
            logger.info("Step 1: Running SonarQube scan...")
            original_dir = os.getcwd()
            innolab_root = os.getenv("INNOLAB_ROOT_PATH", "d:\\InnoLab")
            sonar_dir = os.path.join(innolab_root, "SonarQ")
            os.chdir(sonar_dir)
            try:
                logger.info(
                    "Ensuring sonar-scanner container is running..."
                )
                start_cmd = (
                    "docker start sonar_scanner 2>nul || docker-compose --profile tools up -d sonar-scanner"
                )
                CLIService.run_command(start_cmd, shell=True)
                time.sleep(2)
                if os.path.isabs(self.scan_directory):
                    project_dir = self.scan_directory
                else:
                    project_dir = os.path.abspath(
                        os.path.join(sonar_dir, self.scan_directory)
                    )
                logger.info(f"Project directory: {project_dir}")
                props_file = os.path.join(project_dir, "sonar-project.properties")
                with open(props_file, "w", encoding="utf-8") as f:
                    f.write(f"sonar.projectKey={self.project_key}\n")
                    f.write(f"sonar.projectName={self.project_key}\n")
                    f.write("sonar.sources=.\n")
                    f.write(
                        "sonar.exclusions=**/node_modules/**,**/dist/**,**/build/**,**/.git/**\n"
                    )
                logger.info(
                    f"Created sonar-project.properties for project: {self.project_key}"
                )
                container_work_dir = "/usr/src"
                scan_cmd = [
                    "docker",
                    "exec",
                    "-w",
                    container_work_dir,
                    "-e",
                    "SONAR_HOST_URL=http://sonarqube:9000",
                    "-e",
                    f"SONAR_TOKEN={self.sonar_token}",
                    "sonar_scanner",
                    "sonar-scanner",
                ]
                logger.info(
                    f"Running containerized scan: {' '.join(scan_cmd)}"
                )
                success, output_lines = CLIService.run_command_stream(scan_cmd)
                if not success:
                    logger.error(
                        f"SonarQube scan failed. Output: {''.join(output_lines)}"
                    )
                    return []
                logger.info("SonarQube scan completed successfully")
                logger.info("Waiting for SonarQube to process results...")
                time.sleep(3)
                logger.info("Step 2: Exporting issues...")
                output_file = os.path.join(sonar_dir, f"issues_{self.project_key}.json")
                export_cmd = [
                    "python",
                    os.path.join(sonar_dir, "export_to_file.py"),
                    self.project_key,
                    output_file,
                ]
                if not CLIService.run_command(export_cmd, cwd=sonar_dir):
                    logger.error("Issues export failed")
                    return []
                if os.path.exists(output_file):
                    with open(output_file, "r", encoding="utf-8") as f:
                        bugs_data = json.load(f)
                    all_bugs = bugs_data.get("issues", [])
                    open_bugs = [
                        bug
                        for bug in all_bugs
                        if bug.get("status", "").upper() == "OPEN"
                    ]
                    closed_bugs = [
                        bug
                        for bug in all_bugs
                        if bug.get("status", "").upper() != "OPEN"
                    ]
                    logger.info(
                        f"Found {len(all_bugs)} total bugs: {len(open_bugs)} open, {len(closed_bugs)} closed/resolved"
                    )
                    logger.info(
                        f"Returning {len(open_bugs)} open bugs for processing"
                    )
                    return open_bugs
                else:
                    logger.error(f"Output file not found: {output_file}")
                    return []
            finally:
                os.chdir(original_dir)
        except Exception as e:
            logger.error(f"Error in SonarQube scan process: {str(e)}")
            return []
