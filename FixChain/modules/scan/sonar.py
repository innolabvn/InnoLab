from __future__ import annotations
import json
import os
import time
from typing import Dict, List

from utils.logger import logger
from ..cli_service import CLIService
from .base import Scanner


class SonarQScanner(Scanner):
    """Scanner for SonarQube projects."""

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
            # Hardcode sonar_dir to correct path
            sonar_dir = "d:\\InnoLab\\SonarQ"
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
                    # Try to find project directory relative to innolab_root first
                    project_dir = os.path.abspath(
                        os.path.join(innolab_root, self.scan_directory)
                    )
                    if not os.path.exists(project_dir):
                        # Fallback to relative to sonar_dir
                        project_dir = os.path.abspath(
                            os.path.join(sonar_dir, self.scan_directory)
                        )
                logger.info(f"Project directory: {project_dir}")
                
                # Copy project to source_bug directory for Docker container access
                import shutil
                source_bug_dir = os.path.join(sonar_dir, "source_bug")
                if os.path.exists(source_bug_dir):
                    shutil.rmtree(source_bug_dir)
                shutil.copytree(project_dir, source_bug_dir)
                logger.info(f"Copied project to source_bug directory: {source_bug_dir}")
                
                # Create sonar-project.properties in source_bug directory
                props_file = os.path.join(source_bug_dir, "sonar-project.properties")
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
