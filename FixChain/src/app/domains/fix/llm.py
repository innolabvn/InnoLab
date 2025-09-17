# src/app/domains/fixer/llm.py
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple
from src.app.services.log_service import logger
from src.app.services.cli_service import CLIService
from src.app.adapters.serena_client import SerenaMCPClient
from .base import Fixer

def _extract_json_objects(blob: str):
    objs, stack, start = [], [], None
    for i, ch in enumerate(blob):
        if ch == "{":
            if not stack:
                start = i
            stack.append("{")
        elif ch == "}":
            stack.pop()
            if not stack and start is not None:
                objs.append(blob[start:i+1])
                start = None
    return objs


def _find_repo_root(start: Path) -> Path:
    """
    Tìm repo root theo heuristic:
    - Ưu tiên thư mục chứa 'FixChain' (mono root)
    - Nếu không có, dùng git top-level (nếu có .git)
    - Fallback: parent của `src/`
    """
    cur = start.resolve()
    for _ in range(7):
        # Heuristic 1: có thư mục FixChain, utils, projects
        if (cur / "FixChain").exists() and (cur / "projects").exists():
            return cur
        if (cur / ".git").exists():
            return cur
        cur = cur.parent
    return start.resolve()


class LLMFixer(Fixer):
    """Fixer triển khai bằng cách gọi batch_fix.py qua CLIService."""

    def __init__(self, scan_directory: str):
        super().__init__(scan_directory)
        self.serena_client = SerenaMCPClient()
        self.serena_available = self.serena_client.check_availability()

    def _resolve_source_dir(self) -> Tuple[bool, Path, str]:
        """
        Trả về (ok, source_dir, err_msg)
        - Nếu scan_directory là absolute path -> dùng trực tiếp.
        - Nếu relative -> ghép vào <repo_root>/projects/<scan_directory>.
        - Cho phép override bằng env PROJECTS_ROOT.
        """
        # Absolute path
        sd = Path(self.scan_directory)
        if sd.is_absolute():
            return (sd.exists(), sd, f"Source directory does not exist: {sd}")

        # Relative -> inside projects/
        repo_root = _find_repo_root(Path(__file__).parent)
        projects_root = Path(os.getenv("PROJECTS_ROOT", repo_root / "projects")).resolve()
        source_dir = (projects_root / self.scan_directory).resolve()
        return (source_dir.exists(), source_dir, f"Source directory does not exist: {source_dir}")

    def _locate_batch_fix_dir(self) -> Tuple[bool, Path, str]:
        """
        Tìm thư mục chứa batch_fix. Heuristic:
        - <repo_root>/FixChain/src/app/services/batch_fix
        """
        repo_root = _find_repo_root(Path(__file__).parent)
        candidates = [
            repo_root / "FixChain" / "src" / "app" / "services" / "batch_fix",
            repo_root / "services" / "batch_fix",
        ]
        for c in candidates:
            if (c / "cli.py").exists():
                return True, c, ""
        return False, repo_root, "Cannot locate batch_fix under FixChain/src/app/services or services"

    def _parse_summary_from_stdout(self, output_lines: List[str]) -> Dict:
        """
        Tìm object JSON đầu tiên trong stdout có key 'success'.
        """
        blob = "\n".join(output_lines)
        for candidate in _extract_json_objects(blob):
            if '"success"' in candidate:
                try:
                    return json.loads(candidate)
                except Exception:
                    pass
        # Fallback: quét từng dòng từ dưới lên (tương thích code cũ)
        for line in reversed(output_lines):
            s = line.strip()
            if s.startswith('{"success"'):
                try:
                    return json.loads(s)
                except Exception:
                    continue
        return {}

    def fix_bugs(self, list_real_bugs: List[Dict], bugs_count: int = 0) -> Dict:
        try:
            logger.info("Starting fix_bugs for %d bugs", bugs_count)
            ok_src, source_dir, err_src = self._resolve_source_dir()
            logger.debug("Source_dir = %s", source_dir)

            if not ok_src:
                logger.error(err_src)
                return {"success": False, "fixed_count": 0, "error": err_src}

            ok_batch_fix, batch_fix_dir, err_batch_fix = self._locate_batch_fix_dir()
            if not ok_batch_fix:
                logger.error(err_batch_fix)
                return {"success": False, "fixed_count": 0, "error": err_batch_fix}

            batch_fix_path = (batch_fix_dir / "cli.py").resolve()
            if not batch_fix_path.exists():
                msg = f"cli.py not found at {batch_fix_path}"
                logger.error(msg)
                return {"success": False, "fixed_count": 0, "error": msg}

            # Tạo file issues tạm thời ngay trong source_dir để batch_fix dễ access
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", prefix="list_real_bugs_", dir=source_dir, delete=False, encoding="utf-8"
            ) as tf:
                json.dump(list_real_bugs, tf, indent=2, ensure_ascii=False)
                issues_file_path = Path(tf.name)

            logger.debug("Created issues file: %s", issues_file_path)

            # Chuẩn bị lệnh chạy batch_fix
            fix_cmd = [
                sys.executable,
                "-m", "src.app.services.batch_fix.cli",
                str(source_dir),
                "--issues-file",
                str(issues_file_path),
            ]

            if self.serena_available:
                fix_cmd.extend(["--enable-serena", "--serena-mcp"])
                logger.info("Serena enabled")

            logger.debug("Running command: %s", " ".join(fix_cmd))
            success, output_lines = CLIService.run_command_stream(fix_cmd)

            # Luôn cố gắng xoá file tạm
            try:
                issues_file_path.unlink(missing_ok=True)
                logger.info("Cleaned up temporary issues file: %s", issues_file_path)
            except Exception as e:
                logger.warning("Could not cleanup issues file: %s", e)

            output_text = "".join(output_lines)
            logger.debug("Batch fix output:\n%s", output_text)

            if not success:
                logger.error("Batch fix failed")
                return {"success": False, "fixed_count": 0, "error": output_text}

            # Parse JSON summary từ stdout
            summary = self._parse_summary_from_stdout(output_lines) or {}
            logger.debug("Parsed summary: %s", summary)
            
            fixed_count = int(summary.get("fixed_count", 0))
            total_input_tokens = int(summary.get("total_input_tokens", 0))
            total_output_tokens = int(summary.get("total_output_tokens", 0))
            total_tokens = int(summary.get("total_tokens", 0))
            average_similarity = float(summary.get("average_similarity", 0.0))
            threshold_met_count = int(summary.get("threshold_met_count", 0))
            success_flag = bool(summary.get("success", True))

            logger.info(
                "Batch fix completed. Fixed=%d | Tokens: in=%d out=%d total=%d | AvgSim=%.3f | ThresholdMet=%d",
                fixed_count,
                total_input_tokens,
                total_output_tokens,
                total_tokens,
                average_similarity,
                threshold_met_count,
            )

            return {
                "success": success_flag,
                "fixed_count": fixed_count,
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "total_tokens": total_tokens,
                "average_similarity": average_similarity,
                "threshold_met_count": threshold_met_count,
                "output": output_text,
                "message": (
                    f"Successfully fixed {fixed_count} files using LLM with "
                    f"{len(list_real_bugs)} specific issues. Used {total_tokens} tokens total."
                ),
            }

        except Exception as e:
            logger.exception("Error in fix_bugs")
            return {"success": False, "fixed_count": 0, "error": str(e)}
