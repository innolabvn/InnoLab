from __future__ import annotations
import json
import os
from datetime import datetime
from typing import Dict, List

from utils.logger import logger
from .base import Scanner


class BearerScanner(Scanner):
    """Scanner for loading Bearer scan results."""

    def __init__(self, project_key: str, scan_directory: str = None):
        self.project_key = project_key
        self.scan_directory = scan_directory

    def scan(self) -> List[Dict]:
        """Run Bearer scan and return list of security vulnerabilities."""
        try:
            logger.info(f"Starting Bearer scan for project: {self.project_key}")
            
            # Setup paths
            innolab_root = os.getenv("INNOLAB_ROOT_PATH", "d:\\InnoLab")
            sonar_dir = os.path.join(innolab_root, "SonarQ")
            
            # Ensure bearer_results directory exists
            bearer_results_dir = os.path.join(sonar_dir, "bearer_results")
            os.makedirs(bearer_results_dir, exist_ok=True)
            
            # Output file path
            output_file = os.path.join(bearer_results_dir, f"bearer_results_{self.project_key}.json")
            
            # Remove existing output file to ensure fresh results
            if os.path.exists(output_file):
                try:
                    os.remove(output_file)
                    logger.info(f"Removed existing Bearer results file: {output_file}")
                except Exception as e:
                    logger.warning(f"Failed to remove existing Bearer results file: {e}")
            
            # Determine project directory to scan
            if self.scan_directory:
                if os.path.isabs(self.scan_directory):
                    project_dir = self.scan_directory
                else:
                    # Try relative to innolab_root first
                    project_dir = os.path.abspath(os.path.join(innolab_root, self.scan_directory))
                    if not os.path.exists(project_dir):
                        # Then try relative to sonar_dir
                        project_dir = os.path.abspath(os.path.join(sonar_dir, self.scan_directory))
                        if not os.path.exists(project_dir):
                            # Finally try as direct path under innolab_root
                            project_dir = os.path.abspath(os.path.join(innolab_root, os.path.basename(self.scan_directory)))
            else:
                # Default to demo_project directory
                project_dir = os.path.join(innolab_root, "projects", "demo_project")
                if not os.path.exists(project_dir):
                    # Fallback to source_bug directory if demo_project doesn't exist
                    project_dir = os.path.join(sonar_dir, "source_bug")
            
            if not os.path.exists(project_dir):
                logger.error(f"Project directory not found: {project_dir}")
                return []
            
            logger.info(f"Scanning directory: {project_dir}")
            
            # Run Bearer scan with proper JSON output
            # Use bearer CLI directly if available, otherwise use docker
            scan_success = False
            
            # Try native bearer CLI first
            try:
                from modules.cli_service import CLIService
                
                # Check if bearer is installed natively
                check_cmd = ["bearer", "--version"]
                version_success, _ = CLIService.run_command_stream(check_cmd)
                
                if version_success:
                    logger.info("Using native Bearer CLI")
                    scan_cmd = [
                        "bearer", "scan", project_dir,
                        "--format", "json",
                        "--output", output_file,
                        "--quiet"
                    ]
                    
                    logger.info(f"Running Bearer scan: {' '.join(scan_cmd)}")
                    success, output_lines = CLIService.run_command_stream(scan_cmd)
                    
                    if success and os.path.exists(output_file):
                        scan_success = True
                        logger.info("Bearer scan completed successfully")
                    else:
                        logger.warning("Native Bearer scan failed, trying Docker...")
                        
            except Exception as e:
                logger.warning(f"Native Bearer CLI not available: {e}")
            
            # Fallback to Docker if native CLI failed
            if not scan_success:
                try:
                    logger.info("Using Bearer Docker image")
                    
                    # Convert Windows paths for Docker
                    if os.name == 'nt':  # Windows
                        docker_project_dir = project_dir.replace('\\', '/').replace('C:', '/c').replace('D:', '/d').replace('E:', '/e')
                        docker_output_dir = os.path.dirname(output_file).replace('\\', '/').replace('C:', '/c').replace('D:', '/d').replace('E:', '/e')
                        docker_output_file = f"{docker_output_dir}/{os.path.basename(output_file)}"
                    else:
                        docker_project_dir = project_dir
                        docker_output_file = output_file
                    
                    scan_cmd = [
                        "docker", "run", "--rm",
                        "-v", f"{project_dir}:/scan",
                        "-v", f"{os.path.dirname(output_file)}:/output",
                        "bearer/bearer:latest",
                        "scan", "/scan",
                        "--format", "json",
                        "--output", f"/output/{os.path.basename(output_file)}",
                        "--quiet"
                    ]
                    
                    logger.info(f"Running Bearer Docker scan: {' '.join(scan_cmd)}")
                    success, output_lines = CLIService.run_command_stream(scan_cmd)
                    
                    # Check if output file exists regardless of command exit code
                    # Bearer sometimes returns non-zero exit code but still produces valid output
                    if os.path.exists(output_file):
                        scan_success = True
                        logger.info("Bearer Docker scan completed successfully")
                    else:
                        logger.error("Bearer Docker scan failed")
                        # Log output for debugging
                        bearer_output = ''.join(output_lines)
                        import re
                        clean_output = re.sub(r'\x1b\[[0-9;]*m', '', bearer_output)
                        logger.error(f"Bearer scan output: {clean_output[:1000]}")
                        
                except Exception as docker_error:
                    logger.error(f"Error running Bearer Docker scan: {docker_error}")
            
            # If scan failed, return empty list
            if not scan_success or not os.path.exists(output_file):
                logger.error("Bearer scan failed to produce results file")
                logger.info("Please ensure Bearer CLI is installed or Docker is available")
                logger.info("Install Bearer: https://docs.bearer.com/guides/installation/")
                return []
            
            # Read and parse the results
            logger.info(f"Reading Bearer scan results from: {output_file}")
            with open(output_file, "r", encoding="utf-8") as f:
                bearer_data = json.load(f)
            
            logger.info("Bearer scan results loaded successfully")
            
            # Debug: Log raw Bearer data structure
            logger.debug(f"Bearer data keys: {list(bearer_data.keys())}")
            if "critical" in bearer_data:
                logger.debug(f"Critical issues: {len(bearer_data.get('critical', []))}")
            if "high" in bearer_data:
                logger.debug(f"High issues: {len(bearer_data.get('high', []))}")
            if "medium" in bearer_data:
                logger.debug(f"Medium issues: {len(bearer_data.get('medium', []))}")
            if "low" in bearer_data:
                logger.debug(f"Low issues: {len(bearer_data.get('low', []))}")
            if "findings" in bearer_data:
                logger.debug(f"Findings array: {len(bearer_data.get('findings', []))}")
            
            bugs = self._convert_bearer_to_bugs_format(bearer_data)
            logger.info(f"Found {len(bugs)} Bearer security issues")
            
            # Debug: Log first few bugs if any
            if bugs:
                logger.debug(f"Sample bug: {bugs[0]}")
            
            return bugs
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Bearer JSON file: {e}")
            return []
        except Exception as e:
            logger.error(f"Error during Bearer scan: {e}")
            return []

    def _convert_bearer_to_bugs_format(self, bearer_data: Dict) -> List[Dict]:
        """Convert Bearer scan results to compatible bugs format."""
        bugs: List[Dict] = []
        
        # Bearer JSON format can have different structures
        # Handle both old format (severity-based) and new format (findings array)
        findings = []
        
        if "findings" in bearer_data:
            # New Bearer format with findings array
            findings = bearer_data.get("findings", [])
        else:
            # Old Bearer format with severity levels
            severity_levels = ["critical", "high", "medium", "low", "info"]
            for severity in severity_levels:
                severity_findings = bearer_data.get(severity, [])
                for finding in severity_findings:
                    finding["severity"] = severity  # Add severity to finding
                    findings.append(finding)
        
        # Process each finding
        for finding in findings:
            try:
                # Extract filename
                filename = finding.get("filename", finding.get("full_filename", "unknown"))
                if filename.startswith("/scan/"):
                    filename = filename[6:]  # Remove /scan/ prefix from Docker mount
                elif filename.startswith("/"):
                    # Handle absolute paths
                    filename = filename[1:] if len(filename) > 1 else "unknown"
                
                # Extract line number
                line_number = finding.get("line_number", 1)
                if "source" in finding:
                    source = finding["source"]
                    if isinstance(source, dict):
                        line_number = source.get("start", source.get("line", line_number))
                    elif isinstance(source, int):
                        line_number = source
                
                # Extract rule information
                rule_id = finding.get("id", finding.get("rule_id", "bearer_security_issue"))
                
                # Generate unique key
                fingerprint = finding.get("fingerprint", hash(str(finding)) & 0x7FFFFFFF)
                unique_key = f"bearer_{rule_id}_{fingerprint}"
                
                # Extract title and description
                title = finding.get("title", finding.get("rule_title", "Security vulnerability"))
                description = finding.get("description", finding.get("rule_description", ""))
                
                # Create message
                if description:
                    message = f"{title}. {description[:200]}..." if len(description) > 200 else f"{title}. {description}"
                else:
                    message = title
                
                # Extract severity
                severity = finding.get("severity", "medium").lower()
                
                # Extract CWE IDs
                cwe_ids = finding.get("cwe_ids", finding.get("cwe", []))
                if isinstance(cwe_ids, str):
                    cwe_ids = [cwe_ids]
                
                # Extract additional metadata
                rule_type = finding.get("type", "security")
                confidence = finding.get("confidence", "medium")
                
                # Create bug entry
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
                logger.warning(f"Error processing Bearer finding: {e}")
                logger.debug(f"Problematic finding: {finding}")
                continue
        
        return bugs
    
    def _extract_column_start(self, finding: Dict) -> int:
        """Extract column start position from finding."""
        if "source" in finding:
            source = finding["source"]
            if isinstance(source, dict):
                if "column" in source:
                    column = source["column"]
                    if isinstance(column, dict):
                        return column.get("start", 0)
                    elif isinstance(column, int):
                        return column
                return source.get("start_column", source.get("column_start", 0))
        return 0
    
    def _extract_column_end(self, finding: Dict) -> int:
        """Extract column end position from finding."""
        if "source" in finding:
            source = finding["source"]
            if isinstance(source, dict):
                if "column" in source:
                    column = source["column"]
                    if isinstance(column, dict):
                        return column.get("end", 0)
                    elif isinstance(column, int):
                        return column + 1  # Assume single character
                return source.get("end_column", source.get("column_end", 0))
        return 0

    def _map_bearer_severity(self, bearer_severity: str) -> str:
        """Map Bearer severity levels to SonarQube-compatible severity levels."""
        severity_map = {
            "critical": "BLOCKER",
            "high": "CRITICAL", 
            "medium": "MAJOR",
            "low": "MINOR",
            "info": "INFO",
            "warning": "MINOR",
            "error": "CRITICAL",
            # Handle uppercase variants
            "CRITICAL": "BLOCKER",
            "HIGH": "CRITICAL",
            "MEDIUM": "MAJOR",
            "LOW": "MINOR",
            "INFO": "INFO",
            "WARNING": "MINOR",
            "ERROR": "CRITICAL",
        }
        return severity_map.get(bearer_severity, "MAJOR")
