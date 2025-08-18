from __future__ import annotations
import subprocess
from typing import List, Optional, Sequence
from utils.logger import logger

class CLIService:
    """Helper service for running CLI commands with logging."""

    @staticmethod
    def run_command(
        command: Sequence[str] | str,
        cwd: Optional[str] = None,
        env: Optional[dict] = None,
        shell: bool = False,
    ) -> bool:
        """Run a command and log its output.

        Args:
            command: Command to execute. Can be a list of args or a string if ``shell`` is True.
            cwd: Working directory for the command.
            env: Optional environment variables.
            shell: Whether to execute through the shell.

        Returns:
            bool: True if command succeeded (return code 0), False otherwise.
        """
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                shell=shell,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            if result.stdout:
                logger.info(result.stdout.strip())
            if result.stderr:
                logger.warning(result.stderr.strip())
            if result.returncode != 0:
                logger.error(f"Command failed with return code {result.returncode}")
                return False
            return True
        except FileNotFoundError:
            cmd = command if isinstance(command, str) else command[0]
            logger.error(f"Command not found: {cmd}")
            return False
        except Exception as e:
            logger.error(f"Error running command {command}: {e}")
            return False

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
                env=env,
                shell=shell,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
            )
            assert process.stdout is not None
            for line in process.stdout:
                output_lines.append(line)
                logger.info(line.strip())
            return_code = process.wait()
            if return_code != 0:
                logger.error(f"Command failed with return code {return_code}")
                return False, output_lines
            return True, output_lines
        except FileNotFoundError:
            cmd = command if isinstance(command, str) else command[0]
            logger.error(f"Command not found: {cmd}")
            return False, output_lines
        except Exception as e:
            logger.error(f"Error running command {command}: {e}")
            return False, output_lines

    @staticmethod
    def run_cline_autofix(file_path: str) -> bool:
        """Run the cline CLI autofix for a given file."""
        logger.info(f"Running cline CLI autofix for {file_path}")
        return CLIService.run_command(["cline", "autofix", file_path])
