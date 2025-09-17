"""Serena MCP Client for direct communication with Serena AI assistant"""

import importlib.util
import os
import re
import shutil
import logging
from typing import List, Optional
from dataclasses import dataclass
from src.app.services.log_service import logger

@dataclass
class SerenaResponse:
    """Response from Serena MCP"""
    success: bool
    content: str
    suggestions: List[str]
    confidence: float
    error: Optional[str] = None

class SerenaMCPClient:
    """Client for communicating with Serena MCP"""
    
    def __init__(self, mcp_config_path: Optional[str] = None, project_path: Optional[str] = None):
        cur_dir = os.path.dirname(os.path.abspath(__file__))
        fixchain_dir = os.path.dirname(os.path.dirname(os.path.dirname(cur_dir)))
        self.mcp_config_path = mcp_config_path or os.path.join(fixchain_dir, ".mcp.json")
        self.project_path = project_path or os.path.dirname(fixchain_dir)
        self.logger = logging.getLogger(__name__)
        self.available = self.check_availability()
        
    def check_availability(self) -> bool:
        # Serena không bắt buộc cho bản local-fallback, nhưng nếu có thì good-to-know
        try:
            has_cfg = os.path.exists(self.mcp_config_path)
            has_cli = shutil.which("serena") is not None
            has_uvx = shutil.which("uvx") is not None
            has_mod = importlib.util.find_spec("serena") is not None
            ok = bool(has_cfg and (has_cli or has_uvx or has_mod))
            logger.debug(f"Serena MCP availability - Config: {has_cfg}, CLI: {has_cli}, UVX: {has_uvx}, Module: {has_mod} => Available: {ok}")
            return ok
        except Exception as e:
            self.logger.warning(f"Serena availability check failed: {e}")
            return False
        
    def apply_fix_instructions(self, original_code: str, instructions: str, file_path: str) -> SerenaResponse:
        """Apply fix instructions to code using Serena MCP"""
        try:
            # Write original code to temp file in project directory
            temp_dir = os.path.join(self.project_path, 'temp_files')
            os.makedirs(temp_dir, exist_ok=True)
            tmp = os.path.join(temp_dir, os.path.basename(file_path) or "temp.py")

            with open(tmp, "w", encoding="utf-8") as f:
                f.write(original_code)

            result = self._apply_local_replacements(tmp, instructions)
            final = ""
            with open(tmp, "r", encoding="utf-8") as f:
                final = f.read()
            try:
                os.remove(tmp)
            except Exception:
                pass

            if result["applied"] > 0:
                return SerenaResponse(True, final, [], 0.9)
            return SerenaResponse(False, "", [], 0.0, result.get("error") or "No changes applied")
        except Exception as e:
            self.logger.error(f"apply_fix_instructions error: {e}")
            return SerenaResponse(False, "", [], 0.0, str(e))


# ---- Helpers ----
    def _apply_local_replacements(self, file_path: str, instructions: str) -> dict:
        """
        Hỗ trợ các dạng:
          - replace X with Y
          - change X to Y
          - use Y instead of X
          - substitute Y for X
        Dạng đơn giản: thay chuỗi thuần túy (không regex).
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            applied = 0
            for old_text, new_text in self._parse_instructions(instructions):
                if old_text and old_text in content:
                    content = content.replace(old_text, new_text)
                    applied += 1
                else:
                    self.logger.info(f"Text not found, skip: {old_text[:80]}")

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            return {"applied": applied}
        except Exception as e:
            self.logger.error(f"Local replacement failed: {e}")
            return {"applied": 0, "error": str(e)}

    def _parse_instructions(self, instructions: str):
        lines = [ln.strip() for ln in instructions.splitlines() if ln.strip() and not ln.strip().startswith("#")]
        patterns = [
            (r'^replace\s+(.+?)\s+with\s+(.+?)$', False),
            (r'^change\s+(.+?)\s+to\s+(.+?)$',   False),
            (r'^use\s+(.+?)\s+instead\s+of\s+(.+?)$', True),   # group1=new, group2=old
            (r'^substitute\s+(.+?)\s+for\s+(.+?)$',    True),  # group1=new, group2=old
        ]
        pairs = []
        for raw in lines:
            s = raw.lower()
            for pat, swap in patterns:
                m = re.match(pat, s)
                if m:
                    a, b = (m.group(1).strip(), m.group(2).strip())
                    old_text, new_text = (b, a) if swap else (a, b)
                    pairs.append((self._unquote(old_text), self._unquote(new_text)))
                    break
        return pairs

    @staticmethod
    def _unquote(s: str) -> str:
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            return s[1:-1]
        return s