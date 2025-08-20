#!/usr/bin/env python3
"""
Demo script to run ExecutionService with or without RAG
This bypasses MongoDB dependency for testing
"""

import os
import sys
import json
import time
from datetime import datetime
from typing import List, Dict, Optional
from dotenv import load_dotenv

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service.cli_service import CLIService
from lib.dify_lib import DifyMode, run_workflow_with_dify
from utils.logger import logger

RAG_AVAILABLE = True

# Load environment variables
load_dotenv()

class ExecutionServiceNoMongo:
    """ExecutionService without MongoDB dependency"""
    
    def __init__(self, scan_directory=None):
        # Load environment variables
        self.dify_cloud_api_key = os.getenv('DIFY_CLOUD_API_KEY')
        self.dify_local_api_key = os.getenv('DIFY_LOCAL_API_KEY')
        self.sonar_host = os.getenv('SONAR_HOST', 'http://localhost:9000')
        self.sonar_token = os.getenv('SONAR_TOKEN')
        
        # Configuration from environment variables
        self.max_iterations = int(os.getenv('MAX_ITERATIONS', '5'))
        self.project_key = os.getenv('PROJECT_KEY')
        self.source_code_path = os.getenv('SOURCE_CODE_PATH')
        # Priority: parameter > environment variable > default
        self.scan_directory = scan_directory or os.getenv('SCAN_DIRECTORY', 'source_bug')
        
        # Execution tracking
        self.execution_count = 0
        self.current_source_file = 'code.py'  # Track current source file to scan
        
        # Log configuration
        logger.info(f"ExecutionServiceNoMongo initialized with:")
        logger.info(f"  Max iterations: {self.max_iterations}")
        logger.info(f"  Project key: {self.project_key}")
        logger.info(f"  Source code path: {self.source_code_path}")
        logger.info(f"  Scan directory: {self.scan_directory}")
        logger.info(f"  RAG available: {RAG_AVAILABLE}")
    
    def insert_rag_default(self) -> bool:
        """Insert default RAG data for bug fixing"""
        logger.info("Inserting default RAG data...")
        try:
            # Get dataset path from environment
            dataset_path = os.getenv('RAG_DATASET_PATH')
            if not dataset_path:
                logger.error("RAG_DATASET_PATH must be set in environment")
                return False
            
            # Check if dataset file exists
            if not os.path.exists(dataset_path):
                logger.error(f"Dataset file not found: {dataset_path}")
                return False
            
            # For demo without MongoDB, we'll just validate the dataset file
            # In full implementation with MongoDB, use this approach:
            from service.execution import ExecutionService
            execution_service = ExecutionService()
            return execution_service.insert_dataset_to_rag(dataset_path)
            
            
        except Exception as e:
            logger.error(f"Error inserting RAG data: {str(e)}")
            return False
    
    def scan_sonarq_bugs(self) -> List[Dict]:
        """Scan SonarQube to get list of bugs"""
        try:
            logger.info(f"Starting SonarQube scan for project: {self.project_key}")
            
            # Step 1: Run SonarQube scan using containerized scanner
            logger.info("Step 1: Running SonarQube scan...")
            
            # Change to SonarQ directory
            original_dir = os.getcwd()
            sonar_dir = "d:\\InnoLab\\SonarQ"
            os.chdir(sonar_dir)
            
            try:
                # Start sonar-scanner container if not running
                logger.info("Ensuring sonar-scanner container is running...")
                start_cmd = "docker start sonar_scanner 2>nul || docker-compose --profile tools up -d sonar-scanner"
                CLIService.run_command(start_cmd, shell=True)
                time.sleep(2)  # Wait for container to be ready
                
                # Create sonar-project.properties
                # Handle both relative and absolute paths for scan_directory
                if os.path.isabs(self.scan_directory):
                    project_dir = self.scan_directory
                else:
                    # For relative paths, resolve from sonar_dir
                    project_dir = os.path.abspath(os.path.join(sonar_dir, self.scan_directory))
                
                logger.info(f"Project directory: {project_dir}")
                
                # Ensure the directory exists
                os.makedirs(project_dir, exist_ok=True)
                props_file = os.path.join(project_dir, "sonar-project.properties")
                
                with open(props_file, 'w', encoding='utf-8') as f:
                    f.write(f"sonar.projectKey={self.project_key}\n")
                    f.write(f"sonar.projectName={self.project_key}\n")
                    f.write("sonar.sources=.\n")
                    f.write("sonar.exclusions=**/node_modules/**,**/dist/**,**/build/**,**/.git/**\n")
                
                logger.info(f"Created sonar-project.properties for project: {self.project_key}")
                
                # Copy project files to sonar scanner container
                # First, copy the project directory to the container
                copy_cmd = f"docker cp \"{project_dir}\" sonar_scanner:/usr/src/"
                logger.info(f"Copying project files: {copy_cmd}")
                CLIService.run_command(copy_cmd, shell=True)
                
                # Get the directory name for the working directory in container
                project_name = os.path.basename(project_dir)
                container_work_dir = f"/usr/src/{project_name}"
                
                # Run scan using docker exec
                scan_cmd = [
                    "docker", "exec", "-w", container_work_dir,
                    "-e", f"SONAR_HOST_URL=http://sonarqube:9000",
                    "-e", f"SONAR_TOKEN={self.sonar_token}",
                    "sonar_scanner", "sonar-scanner"
                ]
                
                logger.info(f"Running containerized scan: {' '.join(scan_cmd)}")
                
                # Start the process
                success, output_lines = CLIService.run_command_stream(scan_cmd)
                if not success:
                    logger.error(f"SonarQube scan failed. Output: {''.join(output_lines)}")
                    return []
                logger.info("SonarQube scan completed successfully")
                
                # Step 2: Wait a bit for SonarQube to process results
                logger.info("Waiting for SonarQube to process results...")
                time.sleep(3)  # Wait 3 seconds for background processing
                
                # Step 3: Export issues using export_to_file
                logger.info("Step 2: Exporting issues...")
                output_file = os.path.join(sonar_dir, f"issues_{self.project_key}.json")
                export_cmd = [
                    'python', 
                    'd:\\InnoLab\\SonarQ\\export_to_file.py', 
                    self.project_key,
                    output_file
                ]
                
                if not CLIService.run_command(export_cmd, cwd=sonar_dir):
                    logger.error("Issues export failed")
                    return []
                
                # Read JSON output from file
                if os.path.exists(output_file):
                    with open(output_file, 'r', encoding='utf-8') as f:
                        bugs_data = json.load(f)
                    all_bugs = bugs_data.get('issues', [])
                    
                    logger.info(f"Found {len(all_bugs)} total bugs, {len(all_bugs)} bugs")
                    return all_bugs
                else:
                    logger.error(f"Output file not found: {output_file}")
                    return []
                    
            finally:
                # Restore original directory
                os.chdir(original_dir)
            
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
            
            # Clean content by removing ```python ``` markers
            cleaned_content = self.clean_code_content(content)
            
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
                f.write(cleaned_content)
            
            logger.info(f"Updated source code: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error writing source code to {file_path}: {str(e)}")
            return False
    
    def clean_code_content(self, content: str) -> str:
        """Remove ```python ``` markers from beginning and end of content"""
        lines = content.split('\n')
        
        # Remove first line if it contains ```python
        if lines and lines[0].strip().startswith('```python'):
            lines = lines[1:]
        
        # Remove last line if it contains ```
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        
        # Also check second to last line in case there's an empty line before ```
        if len(lines) >= 2 and lines[-1].strip() == '' and lines[-2].strip() == '```':
            lines = lines[:-2]

        return '\n'.join(lines)

    def analysis_bugs_with_dify(self, bugs: List[Dict], use_rag: bool = False, mode: DifyMode = DifyMode.CLOUD) -> Dict:
        """Analysis bugs using Dify API"""
        try:
            # Choose API key based on mode
            api_key = self.dify_cloud_api_key if mode == DifyMode.CLOUD else self.dify_local_api_key
            
            if not api_key:
                logger.error(f"No API key found for mode: {mode}")
                return {"success": False, "error": "Missing API key"}
            
            # Prepare input for Dify
            inputs = {
                # use string to avoid json format error
                "is_use_rag": str(use_rag),
                "report": json.dumps(bugs, ensure_ascii=False),
            }
            
            logger.info(f"Fixing {len(bugs)} bugs using Dify")
            
            # Call Dify workflow once with all bugs
            response = run_workflow_with_dify(
                api_key=api_key,
                inputs=inputs,
                user="hieult",
                response_mode="blocking",
                mode=mode
            )
            
            # Log Dify outputs for analysis
            analysis_bug = response.get('data', {}).get('outputs', {}).get('analysis_bug', '')
            usage = response.get('data', {}).get('outputs', {}).get('usage', '')
            
            logger.info(f"Dify analysis_bug: {analysis_bug}")
            logger.info(f"Dify usage: {usage}")
            
            # Extract fixed code from response
            outputs = response.get('data', {}).get('outputs', {})
            list_bugs = outputs.get('list_bugs', '')
            bugs_to_fix = outputs.get('bugs_to_fix', '')

            
            # if bugs_to_fix  = 0 then return success
            if bugs_to_fix == 0:
                return {
                    "success": True,
                    "bugs_to_fix": bugs_to_fix,
                    "list_bugs": list_bugs,
                    "message": "No bugs to fix"
                }
            
            
            # Increment execution count and save to new file
            self.execution_count += 1
            return {
                "success": True,
                "list_bugs": list_bugs,
                "bugs_to_fix": bugs_to_fix,
                "message": "No bugs to fix"
            }

                
        except Exception as e:
            logger.error(f"DIFY:Error in fix_bugs_with_dify: {str(e)}")
            return {
                "list_bugs": list_bugs,
                "success": False,
                "bugs_to_fix": bugs_to_fix,
                "error": str(e)
            }
    
    def fix_bugs_llm(self, list_real_bugs: List[Dict], use_rag: bool = False) -> Dict:
        """
        Fix bugs using LLM by calling batch_fix.py script from SonarQ folder
        This method integrates with the existing batch_fix.py to fix code issues
        
        Phương thức này sử dụng script batch_fix.py từ thư mục SonarQ để fix bugs:
        1. Xác định thư mục source code cần fix (từ self.scan_directory)
        2. Tạo file list_real_bugs.json từ dữ liệu list_real_bugs
        3. Chuyển đến thư mục SonarQ 
        4. Chạy command: python batch_fix.py --fix source_bug --auto --issues-file list_real_bugs.json
        5. batch_fix.py sẽ:
           - Quét tất cả file code trong thư mục (.py, .js, .ts, .jsx, .tsx, .java, .cpp, .c)
           - Sử dụng Google Gemini AI để phân tích và fix từng file
           - Sử dụng dữ liệu từ list_real_bugs.json để fix các lỗi cụ thể
           - Tạo backup cho mỗi file trước khi fix
           - Validate syntax và safety của code sau khi fix
           - Ghi đè file gốc với code đã được fix
        6. Đếm số file đã fix thành công từ output
        7. Trả về kết quả với số lượng file đã fix
        """
        try:
            logger.info(f"Starting fix_bugs_llm for {len(list_real_bugs)} bugs")
            
            # Bước 1: Xác định thư mục source code cần fix
            # Ưu tiên: parameter > environment variable > default
            if os.path.isabs(self.scan_directory):
                source_dir = self.scan_directory
            else:
                # Đối với đường dẫn tương đối, resolve từ thư mục SonarQ
                sonar_dir = "d:\\InnoLab\\SonarQ"
                source_dir = os.path.abspath(os.path.join(sonar_dir, self.scan_directory))
            
            logger.info(f"Fixing bugs in directory: {source_dir}")
            
            # Bước 2: Kiểm tra thư mục có tồn tại không
            if not os.path.exists(source_dir):
                logger.error(f"Source directory does not exist: {source_dir}")
                return {
                    "success": False,
                    "fixed_count": 0,
                    "error": f"Source directory does not exist: {source_dir}"
                }
            
            # Bước 3: Chuyển đến thư mục SonarQ để chạy batch_fix.py
            original_dir = os.getcwd()
            sonar_dir = "d:\\InnoLab\\SonarQ"
            
            try:
                os.chdir(sonar_dir)
                
                # Bước 4: Tạo file list_real_bugs.json từ dữ liệu list_real_bugs
                issues_file_path = os.path.join(sonar_dir, "list_real_bugs.json")
                try:
                    with open(issues_file_path, 'w', encoding='utf-8') as f:
                        json.dump(list_real_bugs, f, indent=2, ensure_ascii=False)
                    logger.info(f"Created issues file: {issues_file_path} with {len(list_real_bugs)} bugs")
                except Exception as e:
                    logger.error(f"Failed to create issues file: {str(e)}")
                    return {
                        "success": False,
                        "fixed_count": 0,
                        "error": f"Failed to create issues file: {str(e)}"
                    }
                
                # Bước 5: Chuẩn bị và chạy command batch_fix.py với các tham số mới
                # Sử dụng --fix để enable fixing mode
                # Sử dụng --auto để skip confirmation prompts
                # Sử dụng --issues-file để load specific issues từ JSON file
                # Không sử dụng --output để ghi đè trực tiếp vào file gốc thay vì tạo thư mục duplicate
                fix_cmd = [
                    'python', 
                    'batch_fix.py',
                    'source_bug',
                    '--fix',
                    '--auto',
                    '--issues-file',
                    'list_real_bugs.json'
                ]
                
                logger.info(f"Running command: {' '.join(fix_cmd)}")
                
                # Bước 6: Thực thi command batch fix
                success, output_lines = CLIService.run_command_stream(fix_cmd)
                
                if success:
                    # Bước 7: Parse output để đếm số file đã fix thành công
                    output_text = ''.join(output_lines)
                    fixed_count = 0
                    
                    # Đếm số lần fix thành công từ output
                    # Tìm pattern "✅ Success" trong output
                    for line in output_lines:
                        if "✅ Success" in line:
                            fixed_count += 1
                    
                    logger.info(f"Batch fix completed successfully. Fixed {fixed_count} files")
                    
                    # Bước 8: Trả về kết quả thành công
                    return {
                        "success": True,
                        "fixed_count": fixed_count,
                        "output": output_text,
                        "message": f"Successfully fixed {fixed_count} files using LLM with {len(list_real_bugs)} specific issues"
                    }
                else:
                    # Xử lý trường hợp command thất bại
                    error_output = ''.join(output_lines)
                    logger.error(f"Batch fix failed: {error_output}")
                    
                    return {
                        "success": False,
                        "fixed_count": 0,
                        "error": f"Batch fix failed: {error_output}"
                    }
                    
            finally:
                # Bước 9: Khôi phục thư mục gốc
                os.chdir(original_dir)
                
                # Bước 10: Cleanup - xóa file issues tạm thời (optional)
                try:
                    if os.path.exists(issues_file_path):
                        os.remove(issues_file_path)
                        logger.info(f"Cleaned up temporary issues file: {issues_file_path}")
                except Exception as e:
                    logger.warning(f"Could not cleanup issues file: {str(e)}")
                
        except Exception as e:
            # Bước 11: Xử lý exception và trả về lỗi
            logger.error(f"Error in fix_bugs_llm: {str(e)}")
            return {
                "success": False,
                "fixed_count": 0,
                "error": str(e)
            }
    
    def log_execution_result(self, result: Dict):
        """Log execution result (simplified version without MongoDB)"""
        logger.info("=== EXECUTION RESULT ===")
        logger.info(f"Mode: {result.get('mode')}")
        logger.info(f"Project: {result.get('project_key')}")
        logger.info(f"Total bugs fixed: {result.get('total_bugs_fixed')}")
        logger.info(f"Total iterations: {len(result.get('iterations', []))}")
        logger.info(f"Start time: {result.get('start_time')}")
        logger.info(f"End time: {result.get('end_time')}")
        
        for i, iteration in enumerate(result.get('iterations', []), 1):
            logger.info(f"Iteration {i}: {iteration.get('bugs_found')} bugs found, {iteration.get('fix_result', {}).get('fixed_count', 0)} fixed")
    
    def run_execution(self, use_rag: bool = False, mode: DifyMode = DifyMode.CLOUD) -> Dict:
        """Run execution with or without RAG support"""
        start_time = datetime.now()
        logger.info(f"Starting execution {'with' if use_rag else 'without'} RAG (mode: {mode})")
        
        iterations = []
        total_bugs_fixed = 0
        for iteration in range(1, self.max_iterations + 1):
            logger.info(f"\n=== ITERATION {iteration}/{self.max_iterations} ===")
            
            # Scan for bugs
            bugs = self.scan_sonarq_bugs()
            # Count bugs by type using dictionary comprehension
            bug_counts = {
                'BUG': len([bug for bug in bugs if bug.get('type') == 'BUG']),
                'CODE_SMELL': len([bug for bug in bugs if bug.get('type') == 'CODE_SMELL'])
            }
            bugs_type_bug = bug_counts['BUG']
            bugs_type_code_smell = bug_counts['CODE_SMELL']
            bugs_found = len(bugs)
            
            # Create iteration result
            iteration_result = {
                "iteration": iteration,
                "bugs_found": bugs_found,
                "bugs_type_bug": bugs_type_bug,
                "bugs_type_code_smell": bugs_type_code_smell,
                "timestamp": datetime.now().isoformat()
            }
            
            # Check if no bugs found - early exit
            if bugs_found == 0:
                logger.info("No bugs found - execution completed successfully")
                iteration_result["fix_result"] = {
                    "success": True,
                    "fixed_count": 0,
                    "failed_count": 0,
                    "bugs_remain": 0,
                    "bugs_type_bug": 0,
                    "bugs_type_code_smell": 0,
                    "message": "No bugs found"
                }
                iterations.append(iteration_result)
                break
            
            # Analysis bugs with Dify
            analysis_result = self.analysis_bugs_with_dify(bugs, use_rag=use_rag, mode=mode)
            bugs_to_fix = analysis_result.get("bugs_to_fix")
            list_bugs = analysis_result.get("list_bugs")
            list_real_bugs = analysis_result.get("list_real_bugs")


            if(bugs_to_fix == 0):
                iteration_result["analysis_result"] = analysis_result
                break

            # Fix bugs with LLM using batch_fix.py
            fix_result = self.fix_bugs_llm(list_real_bugs, use_rag=use_rag)
            
            # Store fix result in iteration
            iteration_result["fix_result"] = fix_result
            
            # Update counters based on fix result
            if fix_result.get("success", False):
                fixed_count = fix_result.get("fixed_count", 0)
                total_bugs_fixed += fixed_count
                
                # If we fixed some bugs, reduce bugs_to_fix
                if fixed_count > 0:
                    bugs_to_fix = max(0, bugs_to_fix - fixed_count)
                    logger.info(f"Fixed {fixed_count} bugs, remaining bugs to fix: {bugs_to_fix}")
                else:
                    logger.info("No bugs were fixed in this iteration")
            else:
                logger.error(f"Fix failed: {fix_result.get('error', 'Unknown error')}")
                # Continue to next iteration even if fix failed


            
            iterations.append(iteration_result)

            if bugs_to_fix == 0:
                logger.info(f"Iteration {iteration} completed: {bugs_to_fix} bugs to fix")
                break
            
            # Log iteration result
            logger.info(f"Iteration {iteration} completed: {fix_result.get('bugs_to_fix', 0)} bugs to fix")
        
        end_time = datetime.now()
        
        # Prepare final result
        mode_str = mode.value if hasattr(mode, 'value') else str(mode)
        if use_rag:
            mode_str = f"{mode_str}_with_rag"
        
        result = {
            "mode": mode_str,
            "project_key": self.project_key,
            "total_bugs_fixed": total_bugs_fixed,
            "iterations": iterations,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": (end_time - start_time).total_seconds()
        }
        
        if use_rag:
            result["rag_enabled"] = True
        
        # Log final result
        self.log_execution_result(result)
        
        return result

def main():
    """Main function to run the demo"""
    import argparse
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='ExecutionService Demo - Bug fixing with Dify AI')
    parser.add_argument('--insert_rag', action='store_true', 
                       help='Run with RAG support (insert default RAG data and use RAG for bug fixing)')
    parser.add_argument('--mode', choices=['cloud', 'local'], default='cloud',
                       help='Dify mode to use (default: cloud)')
    parser.add_argument('--destination', type=str, 
                       help='Destination directory to scan (overrides SCAN_DIRECTORY env var)')
    
    args = parser.parse_args()
    
    print("🚀 Running ExecutionService Demo")
    print("This demo runs the bug fixing process without MongoDB dependency")
    print(f"RAG functionality: {'Available' if RAG_AVAILABLE else 'Not Available'}")
    
    # Determine execution mode based on command line arguments
    if args.insert_rag:
        if not RAG_AVAILABLE:
            print("\n⚠️  Warning: --insert_rag specified but RAG functionality is not available")
            print("Falling back to execution without RAG")
            use_rag = False
        else:
            print("\n🔍 Running with RAG support (--insert_rag specified)")
            use_rag = True
    else:
        # Default to running without RAG (no interactive mode)
        print("\nRunning with default mode: without RAG")
        use_rag = False
    
    try:
        # Initialize service with destination if provided
        service = ExecutionServiceNoMongo(scan_directory=args.destination)
        
        # Determine Dify mode
        dify_mode = DifyMode.CLOUD if args.mode == 'cloud' else DifyMode.LOCAL
        
        # Run execution based on user choice
        if use_rag:
            print(f"\n🔍 Running with RAG support (mode: {args.mode})...")
        else:
            print(f"\n⚡ Running without RAG (mode: {args.mode})...")
        
        result = service.run_execution(use_rag=use_rag, mode=dify_mode)
        
        # Display results
        print("\n" + "="*50)
        print("📊 EXECUTION RESULTS")
        print("="*50)
        print(f"Mode: {result.get('mode')}")
        print(f"Project: {result.get('project_key')}")
        print(f"Total bugs fixed: {result.get('total_bugs_fixed')}")
        print(f"Total iterations: {len(result.get('iterations', []))}")
        print(f"Duration: {result.get('duration_seconds'):.2f} seconds")
        
        for i, iteration in enumerate(result.get('iterations', []), 1):
            
            print(f"\n  Iteration {i}:")
            print(f"    🐞 Bugs found: {iteration.get('bugs_found')}")
            print(f"        + Type Bug: {iteration.get('bugs_type_bug')}")
            bugs_ignored = iteration.get('bugs_type_code_smell', 0)
            print(f"        + Type Code-smell: {bugs_ignored}")
   
            bugs_to_fix = iteration.get('fix_result', {}).get('bugs_to_fix', 0)
            print(f"    🔧 Bugs to fix: {bugs_to_fix}")
            print(f"    🚫 Bugs Ignored: {bugs_ignored}")
       

            # print(f"    Bugs remain: {iteration.get('fix_result', {}).get('bugs_remain', 0)}")
            fix_result = iteration.get('fix_result', {})
            
            # print(f"    Bugs fixed: {fix_result.get('fixed_count', 0)}")
            # print(f"    Bugs failed: {fix_result.get('failed_count', 0)}")
            if fix_result.get('message'):
                print(f"    Message: {fix_result.get('message')}")
        
        print(f"\n⏰ Start time: {result.get('start_time')}")
        print(f"⏰ End time: {result.get('end_time')}")
        print("\n✅ Demo completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error during execution: {str(e)}")
        logger.error(f"Demo failed: {str(e)}")

if __name__ == "__main__":
    main()