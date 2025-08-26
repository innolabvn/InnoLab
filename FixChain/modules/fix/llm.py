from __future__ import annotations
import json
import os
from typing import Dict, List

from utils.logger import logger
from ..cli_service import CLIService
from .base import Fixer


class LLMFixer(Fixer):
    """Service that applies fixes using batch_fix.py"""

    def __init__(self, scan_directory: str):
        self.scan_directory = scan_directory

    def fix_bugs(self, list_real_bugs: List[Dict], use_rag: bool = False) -> Dict:
        try:
            logger.info(
                f"Starting fix_bugs for {len(list_real_bugs)} bugs"
            )
            logger.info(f"DEBUG: scan_directory = {self.scan_directory}")
            if os.path.isabs(self.scan_directory):
                source_dir = self.scan_directory
            else:
                innolab_root = os.getenv("INNOLAB_ROOT_PATH", "d:\\InnoLab")
                logger.info(f"DEBUG: innolab_root = {innolab_root}")
                # Use scan_directory directly with innolab_root
                source_dir = os.path.join(innolab_root, self.scan_directory)
            logger.info(f"DEBUG: source_dir = {source_dir}")
            logger.info(f"Fixing bugs in directory: {source_dir}")
            if not os.path.exists(source_dir):
                logger.error(f"Source directory does not exist: {source_dir}")
                return {
                    "success": False,
                    "fixed_count": 0,
                    "error": f"Source directory does not exist: {source_dir}",
                }
            original_dir = os.getcwd()
            # SonarQ is always at d:\InnoLab\SonarQ regardless of INNOLAB_ROOT_PATH
            sonar_dir = "d:\\InnoLab\\SonarQ"
            try:
                os.chdir(sonar_dir)
                # Create issues file in the project directory instead of SonarQ directory
                issues_file_path = os.path.join(source_dir, "list_real_bugs.json")
                try:
                    if os.path.exists(issues_file_path):
                        os.remove(issues_file_path)
                        logger.info(
                            f"Removed existing issues file: {issues_file_path}"
                        )
                    with open(issues_file_path, "w", encoding="utf-8") as f:
                        json.dump(list_real_bugs, f, indent=2, ensure_ascii=False)
                    logger.info(
                        f"Created issues file: {issues_file_path} with {len(list_real_bugs)} bugs"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to create issues file: {str(e)}"
                    )
                    return {
                        "success": False,
                        "fixed_count": 0,
                        "error": f"Failed to create issues file: {str(e)}",
                    }
                # Use the original source_dir to fix files in the correct location
                scan_dir_path = source_dir
                batch_fix_path = os.path.join(sonar_dir, "batch_fix.py")
                fix_cmd = [
                    "python",
                    batch_fix_path,
                    scan_dir_path,
                    "--fix",
                    "--auto",
                    "--issues-file",
                    "list_real_bugs.json",
                ]
                if use_rag:
                    fix_cmd.append("--enable-rag")
                    logger.info("RAG integration enabled for bug fixing")
                logger.info(f"Running command: {' '.join(fix_cmd)}")
                success, output_lines = CLIService.run_command_stream(fix_cmd)
                if success:
                    output_text = "".join(output_lines)
                    try:
                        # Look for the JSON result line that starts with {"success"
                        summary_line = None
                        for line in reversed(output_lines):
                            line = line.strip()
                            if line.startswith('{"success"'):
                                summary_line = line
                                break
                        
                        if summary_line:
                            # Try to find complete JSON by looking for the closing brace
                            if not summary_line.endswith('}'):
                                # JSON might be incomplete, try to reconstruct
                                for i, line in enumerate(reversed(output_lines)):
                                    if line.strip().startswith('{"success"'):
                                        # Collect all lines from this point to find complete JSON
                                        remaining_lines = list(reversed(output_lines))[len(output_lines)-i-1:]
                                        full_json = ''.join(remaining_lines).strip()
                                        # Find the first complete JSON object
                                        brace_count = 0
                                        json_end = -1
                                        for j, char in enumerate(full_json):
                                            if char == '{':
                                                brace_count += 1
                                            elif char == '}':
                                                brace_count -= 1
                                                if brace_count == 0:
                                                    json_end = j + 1
                                                    break
                                        if json_end > 0:
                                            summary_line = full_json[:json_end]
                                        break
                            
                            summary = json.loads(summary_line)
                        else:
                            summary = {}
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse JSON result: {e}")
                        logger.warning(f"Attempted to parse: {summary_line}")
                        summary = {}

                    fixed_count = summary.get("fixed_count", 0)
                    total_input_tokens = summary.get("total_input_tokens", 0)
                    total_output_tokens = summary.get("total_output_tokens", 0)
                    total_tokens = summary.get("total_tokens", 0)
                    average_similarity = summary.get("average_similarity", 0.0)
                    threshold_met_count = summary.get("threshold_met_count", 0)

                    logger.info(
                        f"Batch fix completed successfully. Fixed {fixed_count} files"
                    )
                    logger.info(
                        f"Token usage - Input: {total_input_tokens}, Output: {total_output_tokens}, Total: {total_tokens}"
                    )
                    logger.info(
                        f"Average similarity: {average_similarity:.3f}, Threshold met: {threshold_met_count}"
                    )
                    return {
                        "success": summary.get("success", True),
                        "fixed_count": fixed_count,
                        "total_input_tokens": total_input_tokens,
                        "total_output_tokens": total_output_tokens,
                        "total_tokens": total_tokens,
                        "average_similarity": average_similarity,
                        "threshold_met_count": threshold_met_count,
                        "output": output_text,
                        "message": f"Successfully fixed {fixed_count} files using LLM with {len(list_real_bugs)} specific issues. Used {total_tokens} tokens total.",
                    }
                else:
                    error_output = "".join(output_lines)
                    logger.error(f"Batch fix failed: {error_output}")
                    return {
                        "success": False,
                        "fixed_count": 0,
                        "error": f"Batch fix failed: {error_output}",
                    }
            finally:
                os.chdir(original_dir)
                try:
                    if os.path.exists(issues_file_path):
                        os.remove(issues_file_path)
                        logger.info(
                            f"Cleaned up temporary issues file: {issues_file_path}"
                        )
                except Exception as e:
                    logger.warning(
                        f"Could not cleanup issues file: {str(e)}"
                    )
        except Exception as e:
            logger.error(f"Error in fix_bugs: {str(e)}")
            return {
                "success": False,
                "fixed_count": 0,
                "error": str(e),
            }
