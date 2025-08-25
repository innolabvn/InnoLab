from __future__ import annotations
import json
import os
from typing import Dict, List

from utils.logger import logger
from .cli_service import CLIService


class Fixer:
    """Service that applies fixes using batch_fix.py"""

    def __init__(self, scan_directory: str):
        self.scan_directory = scan_directory

    def fix_bugs(self, list_real_bugs: List[Dict], use_rag: bool = False) -> Dict:
        try:
            logger.info(
                f"Starting fix_bugs for {len(list_real_bugs)} bugs"
            )
            if os.path.isabs(self.scan_directory):
                source_dir = self.scan_directory
            else:
                innolab_root = os.getenv("INNOLAB_ROOT_PATH", "d:\\InnoLab")
                sonar_dir = os.path.join(innolab_root, "SonarQ")
                source_dir = os.path.abspath(
                    os.path.join(sonar_dir, self.scan_directory)
                )
            logger.info(f"Fixing bugs in directory: {source_dir}")
            if not os.path.exists(source_dir):
                logger.error(f"Source directory does not exist: {source_dir}")
                return {
                    "success": False,
                    "fixed_count": 0,
                    "error": f"Source directory does not exist: {source_dir}",
                }
            original_dir = os.getcwd()
            innolab_root = os.getenv("INNOLAB_ROOT_PATH", "d:\\InnoLab")
            sonar_dir = os.path.join(innolab_root, "SonarQ")
            try:
                os.chdir(sonar_dir)
                issues_file_path = os.path.join(sonar_dir, "list_real_bugs.json")
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
                if os.path.isabs(self.scan_directory):
                    scan_dir_path = self.scan_directory
                else:
                    scan_dir_path = self.scan_directory
                fix_cmd = [
                    "python",
                    "batch_fix.py",
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
                        summary_line = next((ln.strip() for ln in reversed(output_lines) if ln.strip()), "{}")
                        summary = json.loads(summary_line)
                    except json.JSONDecodeError:
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
