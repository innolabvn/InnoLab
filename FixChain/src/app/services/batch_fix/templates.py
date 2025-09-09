# src/app/services/batch_fix/templates.py
from __future__ import annotations
import json, os
from datetime import datetime
from typing import Optional, Tuple, Dict, Any
from jinja2 import Environment, FileSystemLoader
from FixChain.src.app.services.log_service import logger

class TemplateManager:
    def __init__(self, prompt_dir: Optional[str] = None) -> None:
        self.prompt_dir = prompt_dir or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "prompts")
        self.env = Environment(loader=FileSystemLoader(self.prompt_dir))
        self._setup_file_logger()

    def _setup_file_logger(self) -> None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._log_file = os.path.join(os.getenv("LOG_DIR","var/logs"), f"template_usage_{ts}.log")
        os.makedirs(os.path.dirname(self._log_file), exist_ok=True)

    def load(self, template_type: str, custom_prompt: Optional[str]) -> Tuple[Optional[str], Dict[str, Any]]:
        files = {"fix":"fix.j2","analyze":"analyze.j2","custom":"custom.j2"}
        if custom_prompt:
            # inline template
            content = f"""{custom_prompt}

Code cần sửa:
{{{{ original_code }}}}
Chỉ trả về code đã sửa, không cần markdown formatting hay giải thích.
"""
            return content, {"custom_prompt": custom_prompt}

        fname = files.get(template_type, "fix.j2")
        path = os.path.join(self.prompt_dir, fname)
        if not os.path.exists(path): return None, {}
        template = self.env.get_template(fname)
        return template.render, {}

    def log_template_usage(self, file_path: str, template_type: str, custom_prompt: Optional[str], rendered_prompt: str) -> None:
        data = {
            "file_path": file_path,
            "template_type": template_type,
            "custom_prompt": bool(custom_prompt),
            "prompt_length": len(rendered_prompt),
            "prompt_preview": rendered_prompt[:200] + ("..." if len(rendered_prompt)>200 else "")
        }
        try:
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write("TEMPLATE_USAGE " + json.dumps(data, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("Failed to write template usage log: %s", e)

    def log_ai_response(self, file_path: str, raw: str, cleaned: str) -> None:
        data = {
            "file_path": file_path,
            "raw_response_length": len(raw),
            "cleaned_response_length": len(cleaned),
            "response_preview": cleaned[:200] + ("..." if len(cleaned)>200 else "")
        }
        try:
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write("AI_RESPONSE " + json.dumps(data, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("Failed to write AI response log: %s", e)

def strip_markdown_code(text: str) -> str:
    s = text.strip()
    if "## 3. Fixed Source Code" in s:
        lines = s.splitlines()
        idx = next((i for i,l in enumerate(lines) if "## 3. Fixed Source Code" in l), None)
        if idx is not None: s = "\n".join(lines[idx+1:]).strip()
    if s.startswith("```"):
        lines = s.splitlines()
        lines = lines[1:] if lines and lines[0].startswith("```") else lines
        if lines and lines[-1].strip()=="```": lines = lines[:-1]
        s = "\n".join(lines)
    return s.strip()
