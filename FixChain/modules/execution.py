import os
import json
import subprocess
import time
from datetime import datetime
from typing import List, Dict, Optional

import requests
from utils.logger import logger
from lib.dify_lib import DifyMode, run_workflow_with_dify
from .mongodb_service import MongoDBService


class ExecutionService:
    def __init__(self):
        # Load environment variables
        self.dify_cloud_api_key = os.getenv('DIFY_CLOUD_API_KEY')
        self.dify_local_api_key = os.getenv('DIFY_LOCAL_API_KEY')
        self.sonar_host = os.getenv('SONAR_HOST', 'http://localhost:9000')
        self.sonar_token = os.getenv('SONAR_TOKEN')
        self.sonarq_path = os.getenv('SONARQ_PATH', os.path.join(os.getcwd(), 'SonarQ'))
        
        # Initialize services
        self.mongodb_service = MongoDBService()
        
        # Configuration from environment variables
        self.max_iterations = int(os.getenv('MAX_ITERATIONS', '5'))
        self.project_key = os.getenv('PROJECT_KEY')
        self.source_code_path = os.getenv('SOURCE_CODE_PATH')
        
        # Execution tracking
        self.execution_count = 0
        self.current_source_file = 'code.py'  # Track current source file to scan
        
        # Log configuration
        logger.info(f"ExecutionService initialized with:")
        logger.info(f"  Max iterations: {self.max_iterations}")
        logger.info(f"  Project key: {self.project_key}")
        logger.info(f"  Source code path: {self.source_code_path}")
        
    def set_project_config(self, project_key: str = None, source_code_path: str = None):
        """Set project configuration for execution
        
        Args:
            project_key: SonarQube project key (optional, uses env var if not provided)
            source_code_path: Path to source code (optional, uses env var if not provided)
        """
        # Use provided values or fall back to environment variables
        if project_key:
            self.project_key = project_key
        elif not self.project_key:
            raise ValueError("PROJECT_KEY must be set in environment or provided as parameter")
            
        if source_code_path:
            self.source_code_path = source_code_path
        elif not self.source_code_path:
            raise ValueError("SOURCE_CODE_PATH must be set in environment or provided as parameter")
            
        logger.info(f"Project configured: {self.project_key} at {self.source_code_path}")
    
    def scan_sonarq_bugs(self) -> List[Dict]:
        """Scan SonarQube to get list of bugs
        
        This method performs a complete SonarQube scan:
        1. Run SonarQube scan using run_scan.bat
        2. Export issues using export_issues.py
        """
        try:
            logger.info(f"Starting SonarQube scan for project: {self.project_key}")
            
            # Step 1: Run SonarQube scan
            logger.info("Step 1: Running SonarQube scan...")
            scan_cmd = [
                os.path.join(self.sonarq_path, 'run_scan.bat'),
                self.source_code_path
            ]
            
            env = os.environ.copy()
            env['SONAR_TOKEN'] = self.sonar_token
            env['SONAR_HOST'] = self.sonar_host
            
            # Run scan (this may take a while)
            scan_result = subprocess.run(
                scan_cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                env=env,
                cwd=self.sonarq_path,
                shell=True
            )
            
            if scan_result.returncode != 0:
                logger.error(f"SonarQube scan failed: {scan_result.stderr}")
                logger.error(f"Scan output: {scan_result.stdout}")
                return []
            
            logger.info("SonarQube scan completed successfully")
            
            # Step 2: Wait a bit for SonarQube to process results
            logger.info("Waiting for SonarQube to process results...")
            time.sleep(10)  # Wait 10 seconds for background processing
            
            # Step 3: Export issues
            logger.info("Step 2: Exporting issues...")
            export_cmd = [
                'python',
                os.path.join(self.sonarq_path, 'export_issues.py'),
                self.project_key,
                self.sonar_host
            ]
            
            export_result = subprocess.run(
                export_cmd, 
                capture_output=True, 
                text=True, 
                encoding='utf-8',
                env=env
            )
            
            if export_result.returncode != 0:
                logger.error(f"Issues export failed: {export_result.stderr}")
                return []
            
            # Parse JSON output
            bugs_data = json.loads(export_result.stdout)
            bugs = bugs_data.get('issues', [])
            
            logger.info(f"Found {len(bugs)} bugs in SonarQube scan")
            return bugs
            
        except Exception as e:
            logger.error(f"Error in SonarQube scan process: {str(e)}")
            return []
    
    def read_source_code(self, file_path: str = None) -> str:
        """Read source code from file"""
        try:
            # Use current source file if no specific file provided
            if file_path is None:
                file_path = self.current_source_file
                
            full_path = os.path.join(self.source_code_path, file_path)
            with open(full_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading source code from {file_path}: {str(e)}")
            return ""
    
    def write_source_code(self, file_path: str, content: str) -> bool:
        """Write fixed code back to file"""
        try:
            full_path = os.path.join(self.source_code_path, file_path)
            
            # Create backup
            backup_path = f"{full_path}.backup.{int(time.time())}"
            if os.path.exists(full_path):
                with open(full_path, 'r', encoding='utf-8') as f:
                    backup_content = f.read()
                with open(backup_path, 'w', encoding='utf-8') as f:
                    f.write(backup_content)
                logger.info(f"Created backup: {backup_path}")
            
            # Write new content
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"Updated source code: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error writing source code to {file_path}: {str(e)}")
            return False
    
    def fix_bugs_with_dify(self, bugs: List[Dict], use_rag: bool = False, mode: DifyMode = DifyMode.CLOUD) -> Dict:
        """Fix bugs using Dify API"""
        try:
            # Choose API key based on mode
            api_key = self.dify_cloud_api_key if mode == DifyMode.CLOUD else self.dify_local_api_key
            
            if not api_key:
                logger.error(f"No API key found for mode: {mode}")
                return {"success": False, "error": "Missing API key"}
            
            # Read source code from current source file
            source_code = self.read_source_code()
            if not source_code:
                logger.error("Failed to read source code from code.py")
                return {"success": False, "error": "Failed to read source code"}
            
            # Prepare input for Dify
            inputs = {
                "is_use_rag": use_rag,
                "src": source_code,
                "report": json.dumps(bugs, ensure_ascii=False),
            }
            
            logger.info(f"Fixing {len(bugs)} bugs using Dify")
            
            # Call Dify workflow once with all bugs
            response = run_workflow_with_dify(
                api_key=api_key,
                inputs=inputs,
                user="execution_service",
                response_mode="blocking",
                mode=mode
            )
            
            fixed_files = []
            failed_fixes = []
            
            # Process response
            if response and 'data' in response:
                outputs = response['data'].get('outputs', {})
                fixed_code = outputs.get('fixed_code') or outputs.get('result')
                analysis_bug = outputs.get('analysis_bug')
                usage = outputs.get('usage')
                
                # Log analysis_bug and usage for further analysis
                if analysis_bug:
                    logger.info(f"Bug Analysis: {analysis_bug}")
                if usage:
                    logger.info(f"Usage Statistics: {usage}")

                if fixed_code:
                    # Check if the fixed code is different from original
                    if fixed_code.strip() != source_code.strip():
                        # Increment execution count for file naming
                        self.execution_count += 1
                        
                        # Create file with execution count: code_1.py, code_2.py, etc.
                        output_filename = f'code_{self.execution_count}.py'
                        
                        if self.write_source_code(output_filename, fixed_code):
                            # Update current source file to the newly created file
                            self.current_source_file = output_filename
                            logger.info(f"Updated current source file to {output_filename} for next iteration")
                            
                            fixed_files.append({
                                "file_path": output_filename,
                                "status": "fixed",
                                "execution_count": self.execution_count
                            })
                            logger.info(f"Successfully fixed bugs in {output_filename}")
                        else:
                            failed_fixes.append({
                                "file_path": output_filename,
                                "error": "Failed to write fixed code"
                            })
                    else:
                        logger.warning("No changes generated for code.py")
                        failed_fixes.append({
                            "file_path": "code.py",
                            "error": "No changes generated"
                        })
                else:
                    logger.error("No result in Dify response")
                    failed_fixes.append({
                        "error": "No result in Dify response"
                    })
            else:
                logger.error("Invalid response from Dify")
                failed_fixes.append({
                    "error": "Invalid Dify response"
                })
            
            return {
                "success": True,
                "fixed_files": fixed_files,
                "failed_fixes": failed_fixes,
                "total_bugs": len(bugs),
                "fixed_count": len(fixed_files),
                "failed_count": len(failed_fixes)
            }
            
        except Exception as e:
            logger.error(f"Error in fix_bugs_with_dify: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def log_execution_result(self, iteration: int, result: Dict, use_rag: bool):
        """Log execution result to file and database"""
        try:
            timestamp = datetime.now().isoformat()
            log_entry = {
                "timestamp": timestamp,
                "iteration": iteration,
                "project_key": self.project_key,
                "use_rag": use_rag,
                "result": result
            }
            
            # Log to file
            log_dir = "d:\\ILA\\FixChain\\logs"
            os.makedirs(log_dir, exist_ok=True)
            
            log_filename = f"execution_{self.project_key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            log_path = os.path.join(log_dir, log_filename)
            
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False, indent=2) + "\n")
            
            # Log to database
            self.mongodb_service.insert_execution_log(log_entry)
            
            logger.info(f"Logged execution result for iteration {iteration}")
            
        except Exception as e:
            logger.error(f"Error logging execution result: {str(e)}")
    
    def run_without_rag(self, mode: DifyMode = DifyMode.CLOUD) -> Dict:
        """Run execution without RAG
        
        Steps:
        1. Scan SonarQ -> List Bug
        2. Source + List Bug -> Dify -> Code Fixed
        3. Run step 2
        4. Chạy 5 max lần (tới khi nào fix hết bug) -> file log theo lần chạy
        """
        logger.info("Starting execution WITHOUT RAG")
        
        if not self.project_key or not self.source_code_path:
            return {"success": False, "error": "Project not configured"}
        
        execution_summary = {
            "mode": "without_rag",
            "project_key": self.project_key,
            "iterations": [],
            "total_bugs_fixed": 0,
            "start_time": datetime.now().isoformat()
        }
        
        for iteration in range(1, self.max_iterations + 1):
            logger.info(f"=== Iteration {iteration}/{self.max_iterations} ===")
            
            # Step 1: Scan SonarQ -> List Bug
            bugs = self.scan_sonarq_bugs()
            
            # Log iteration result with bugs found
            iteration_result = {
                "iteration": iteration,
                "bugs_found": len(bugs),
                "fix_result": None
            }
            
            if not bugs:
                logger.info("No bugs found. Execution completed.")
                iteration_result["fix_result"] = {"success": True, "message": "No bugs found"}
                execution_summary["iterations"].append(iteration_result)
                break
            
            # Step 2: Source + List Bug -> Dify -> Code Fixed
            fix_result = self.fix_bugs_with_dify(bugs, use_rag=False, mode=mode)
            
            # Update iteration result with fix result
            iteration_result["fix_result"] = fix_result
            
            execution_summary["iterations"].append(iteration_result)
            execution_summary["total_bugs_fixed"] += fix_result.get("fixed_count", 0)
            
            self.log_execution_result(iteration, iteration_result, use_rag=False)
            
            # Check if all bugs are fixed
            if fix_result.get("fixed_count", 0) == 0:
                logger.info("No bugs were fixed in this iteration. Stopping.")
                break
            
            logger.info(f"Iteration {iteration} completed. Fixed {fix_result.get('fixed_count', 0)} bugs.")
        
        execution_summary["end_time"] = datetime.now().isoformat()
        logger.info(f"Execution WITHOUT RAG completed. Total bugs fixed: {execution_summary['total_bugs_fixed']}")
        
        return execution_summary
    
    def insert_dataset_to_rag(self, dataset_path: str) -> bool:
        """Insert dataset to RAG system"""
        try:
            with open(dataset_path, 'r', encoding='utf-8') as f:
                bugs_data = json.load(f)
            
            response = requests.post(f"http://localhost:8000/api/v1/bugs/bugs/import", json=bugs_data)
            logger.info(f"Status Code: {response.status_code}")
            
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ Import thành công!")
                logger.info(f"   - Imported: {result['imported_count']} bugs")
                logger.info(f"   - Failed: {result['failed_count']} bugs")
            logger.info(f"   - Batch: {result['batch_name']}")
            logger.info(f"   - Project: {result['project']}")
            
            if result['imported_bugs']:
                logger.info("\n📋 Danh sách bugs đã import:")
                for bug in result['imported_bugs'][:3]:  # Show first 3
                    logger.info(f"   - {bug['bug_name']} ({bug['type']}, {bug['severity']})")
                return True
            if result['failed_bugs']:
                logger.warning("\n❌ Bugs import thất bại:")
                for bug in result['failed_bugs']:
                    logger.warning(f"   - {bug['bug_name']}: {bug['error']}")
                return True
            
            else:
                logger.warning(f"❌ Import thất bại: {response.text}")
                return False

        except Exception as e:
            logger.error(f"❌ Lỗi kết nối: {e}")
            return False

            
    def run_with_rag(self, dataset_path: str = None, mode: DifyMode = DifyMode.CLOUD) -> Dict:
        """Run execution with RAG
        
        Args:
            dataset_path: Path to RAG dataset file (optional, uses env var if not provided)
            mode: Dify mode (cloud or local)
            
        Steps:
        1. Insert Dataset -> RAG
        2. Scan SonarQ -> List Bug
        3. Source + List Bug -> Dify -> Code Fixed -> RAG
        4. Run step 2
        5. Chạy 5 max lần (tới khi nào fix hết bug) -> file log theo lần chạy
        """
        logger.info("Starting execution WITH RAG")
        
        if not self.project_key or not self.source_code_path:
            return {"success": False, "error": "Project not configured"}
        
        # Get dataset path from environment if not provided
        if not dataset_path:
            dataset_path = os.getenv('RAG_DATASET_PATH')
            if not dataset_path:
                return {"success": False, "error": "RAG_DATASET_PATH must be set in environment or provided as parameter"}
        
        # Step 1: Insert Dataset -> RAG
        if not self.insert_dataset_to_rag(dataset_path):
            return {"success": False, "error": "Failed to insert dataset to RAG"}
        
        execution_summary = {
            "mode": "with_rag",
            "project_key": self.project_key,
            "dataset_path": dataset_path,
            "iterations": [],
            "total_bugs_fixed": 0,
            "start_time": datetime.now().isoformat()
        }
        
        for iteration in range(1, self.max_iterations + 1):
            logger.info(f"=== Iteration {iteration}/{self.max_iterations} (WITH RAG) ===")
            
            # Step 2: Scan SonarQ -> List Bug
            bugs = self.scan_sonarq_bugs()
            
            if not bugs:
                logger.info("No bugs found. Execution completed.")
                break
            
            # Step 3: Source + List Bug -> Dify -> Code Fixed -> RAG
            fix_result = self.fix_bugs_with_dify(bugs, use_rag=True, mode=mode)
            
            # Log iteration result
            iteration_result = {
                "iteration": iteration,
                "bugs_found": len(bugs),
                "fix_result": fix_result
            }
            
            execution_summary["iterations"].append(iteration_result)
            execution_summary["total_bugs_fixed"] += fix_result.get("fixed_count", 0)
            
            self.log_execution_result(iteration, iteration_result, use_rag=True)
            
            # Check if all bugs are fixed
            if fix_result.get("fixed_count", 0) == 0:
                logger.info("No bugs were fixed in this iteration. Stopping.")
                break
            
            logger.info(f"Iteration {iteration} completed. Fixed {fix_result.get('fixed_count', 0)} bugs.")
        
        execution_summary["end_time"] = datetime.now().isoformat()
        logger.info(f"Execution WITH RAG completed. Total bugs fixed: {execution_summary['total_bugs_fixed']}")
        
        return execution_summary