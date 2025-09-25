# src/app/services/batch_fix/templates.py
from __future__ import annotations
import json, os
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader
from src.app.services.log_service import logger

root_env_path = Path(__file__).resolve().parents[4]
load_dotenv(root_env_path)


class TemplateManager:
    def __init__(self, prompt_dir: Optional[str] = None) -> None:
        self.prompt_dir = prompt_dir or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "prompts")
        self.env = Environment(loader=FileSystemLoader(self.prompt_dir))
        ts = datetime.now().strftime("%m%d_%H%M%S")
        self._log_file = os.path.join(os.getenv("LOG_DIR","logs"), f"template_usage_{ts}.log")
        os.makedirs(os.path.dirname(self._log_file), exist_ok=True)

    def load(self, template_type: str):
        files = {
            "fix":"fix.j2", 
            "fix_with_serena":"fix_with_serena.j2"
        }

        fname = files.get(template_type, "fix.j2")
        path = os.path.join(self.prompt_dir, fname)
        if not os.path.exists(path): 
            return None, {}
        template = self.env.get_template(fname)
        logger.debug(f"Get template: {template}")
        return template.render, {}

    def log_template_usage(self, file_path: str, template_type: str, rendered_prompt: str) -> None:
        data = {
            "file_path": file_path,
            "template_type": template_type,
            "prompt_length": len(rendered_prompt),
            "prompt_preview": rendered_prompt[:100]
        }
        logger.debug(f"Template data: {data}")
        try:
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write("TEMPLATE_USAGE " + json.dumps(data, ensure_ascii=False) + "\n")
                logger.debug("Writing template usage")
        except Exception as e:
            logger.warning("Failed to write template usage log: %s", e)

    def log_ai_response(self, file_path: str, text: str, fixed_candidate: str) -> None:
        data = {
            "file_path": file_path,
            "raw_response_length": len(text),
            "cleaned_response_length": len(fixed_candidate),
            "response_preview": fixed_candidate[:200]
        }
        try:
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write("AI_RESPONSE " + json.dumps(data, ensure_ascii=False) + "\n")
                logger.debug(f"AI response: {data}")
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
    logger.debug(f"strip_markdown_code return: {s.strip()[:200]}...")
    return s.strip()
