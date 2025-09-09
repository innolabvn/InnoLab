from __future__ import annotations
from typing import List, Optional, Sequence
import subprocess
import re
from src.app.services.log_service import logger

class CLIService:
    """Helper service for running CLI commands with logging."""

    @staticmethod
    def run_command_stream(
        command: Sequence[str] | str,
        cwd: Optional[str] = None,
        env: Optional[dict] = None,
        shell: bool = False,
    ) -> tuple[bool, list[str]]:
        """Run a command and stream its output line by line.

        Returns:
            tuple[bool, list[str]]: Success flag and list of captured output lines.
        """
        output_lines: list[str] = []
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                shell=shell,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
            )
            assert process.stdout is not None
            for line in process.stdout:
                output_lines.append(line)
                try:
                    # Clean ANSI escape sequences and handle Unicode characters
                    clean_line = line.strip()
                    # Remove ANSI escape sequences
                    clean_line = re.sub(r'\x1b\[[0-9;]*m', '', clean_line)
                    # Ensure safe logging by encoding to ASCII with error handling
                    safe_line = clean_line.encode('ascii', errors='ignore').decode('ascii')
                    if safe_line.strip():  # Only log non-empty lines
                        logger.info(f"stdout: {safe_line}")
                except Exception as e:
                    # Fallback for any encoding issues
                    logger.warning("stdout decode error: %s", e)
            process.wait()
            return True, output_lines
        except FileNotFoundError:
            cmd = command if isinstance(command, str) else command[0]
            logger.error(f"Command not found: {cmd}")
            return False, output_lines
        except Exception as e:
            logger.error(f"Error running command {command}: {e}")
            return False, output_lines
