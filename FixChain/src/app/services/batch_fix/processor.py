# src/app/services/batch_fix/processor.py
from __future__ import annotations
import os, json, fnmatch, shutil
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from datetime import datetime

from FixChain.src.app.services.log_service import logger
from app.services.batch_fix.models import FixResult
from app.services.batch_fix import validators as V
from app.services.batch_fix.templates import TemplateManager, strip_markdown_code
from app.services.batch_fix.rag_integration import RAGAdapter
from app.adapters.llm.google_genai import client, GENERATION_MODEL

class SecureFixProcessor:
    def __init__(self, source_dir: str, backup_dir: Optional[str] = None, similarity_threshold: float = 0.85) -> None:
        self.source_dir = os.path.abspath(source_dir)
        self.backup_dir = backup_dir or ""
        self.similarity_threshold = similarity_threshold
        self.ignore_patterns: List[str] = []
        self.tm = TemplateManager()
        self.rag = RAGAdapter()

    def load_ignore_patterns(self, base_dir: str) -> None:
        defaults = [
            "*.pyc","__pycache__/","*.pyo","*.pyd",".git/",".svn/",".hg/",".bzr/",
            "node_modules/",".npm/",".yarn/",".env",".env.*","*.log","*.tmp",".DS_Store","Thumbs.db",
            "*.min.js","*.min.css","dist/","build/","target/",".idea/",".vscode/","*.swp","*.swo",
            "backups/","logs/","fixed/"
        ]
        self.ignore_patterns = defaults[:]
        fx = os.path.join(base_dir, ".fixignore")
        if os.path.exists(fx):
            try:
                with open(fx, "r", encoding="utf-8") as f:
                    self.ignore_patterns += [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
            except Exception as e:
                logger.warning("Could not read .fixignore: %s", e)

    def should_ignore_file(self, path: str, base_dir: str) -> bool:
        abs_path = os.path.abspath(path)
        if not abs_path.startswith(os.path.abspath(base_dir)): return True
        if self.backup_dir and abs_path.startswith(os.path.abspath(self.backup_dir)): return True
        rel = os.path.relpath(abs_path, os.path.abspath(base_dir)).replace("\\","/")
        for p in self.ignore_patterns:
            if p.endswith("/") and (rel.startswith(p) or f"/{p}" in f"/{rel}/"): return True
            if fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(os.path.basename(path), p): return True
        return False

    def scan_file_only(self, file_path: str) -> FixResult:
        start = datetime.now()
        try:
            code = Path(file_path).read_text(encoding="utf-8")
            issues: List[str] = []
            if len(code) > 10_000: issues.append("Large file (>10KB)")
            ok, errs = V.validate_by_ext(file_path, code)
            if not ok: issues += errs
            return FixResult(True, file_path, len(code), len(code), issues or ["No issues found"], [])
        except Exception as e:
            elapsed = (datetime.now()-start).total_seconds()
            return FixResult(False, file_path, 0, 0, [f"Scan error: {e}"], [], processing_time=elapsed)

    def fix_file_with_validation(
        self,
        file_path: str,
        template_type: str = "fix",
        custom_prompt: Optional[str] = None,
        max_retries: int = 2,
        issues_data: Optional[List[Dict]] = None,
        enable_rag: bool = False,
    ) -> FixResult:
        start = datetime.now()
        input_tokens = output_tokens = total_tokens = 0
        original = ""
        try:
            original = Path(file_path).read_text(encoding="utf-8")
            rag_context = self.rag.search_context(issues_data) if enable_rag else None

            fixed_code = ""
            text = ""
            validation_errors: List[str] = []
            for attempt in range(max_retries + 1):
                # load template
                tpl, tpl_vars = self.tm.load(template_type, custom_prompt)
                if tpl is None:
                    raise RuntimeError("Template not found. Put templates in src/app/prompts/")
                issues_log = json.dumps(issues_data or [], ensure_ascii=False, indent=2)
                rendered = tpl(
                    original_code=original,
                    validation_rules=V.get_rules_for(file_path),
                    issues_log=issues_log,
                    rag_suggestion=rag_context or "",
                    has_rag_suggestion=bool(rag_context),
                    **tpl_vars,
                ) if callable(tpl) else str(tpl)

                self.tm.log_template_usage(file_path, template_type, custom_prompt, rendered)

                # === google-genai call ===
                resp = client.models.generate_content(
                    model=GENERATION_MODEL,
                    contents=rendered
                )
                text = getattr(resp, "text", "") or ""
                fixed_candidate = strip_markdown_code(text)

                usage = getattr(resp, "usage_metadata", None)
                if usage:
                    input_tokens = getattr(usage, "prompt_token_count", 0)
                    output_tokens = getattr(usage, "candidates_token_count", 0)
                    total_tokens = getattr(usage, "total_token_count", 0)

                self.tm.log_ai_response(file_path, text, fixed_candidate)

                ok, errs = V.validate_by_ext(file_path, fixed_candidate)
                if not ok:
                    validation_errors += errs
                    if attempt < max_retries: continue
                    raise RuntimeError("Syntax validation failed: " + "; ".join(errs))

                safe, s_issues = V.validate_safety(original, fixed_candidate)
                if not safe:
                    validation_errors += s_issues
                    if attempt < max_retries: continue
                    raise RuntimeError("Safety validation failed: " + "; ".join(s_issues))

                fixed_code = fixed_candidate
                break

            # write back (overwrite original)
            Path(file_path).write_text(fixed_code, encoding="utf-8")

            elapsed = (datetime.now()-start).total_seconds()
            sim = V.similarity(original, fixed_code)
            meets = sim >= self.similarity_threshold
            result = FixResult(
                True, file_path, len(original), len(fixed_code),
                [f"Size change: {len(fixed_code)-len(original)} bytes", f"Similarity: {sim:.1%}"],
                validation_errors, None, elapsed, sim,
                input_tokens, output_tokens, total_tokens, meets
            )

            if enable_rag:
                try:
                    self.rag.add_fix(result, issues_data, text, fixed_code)
                except Exception as e:
                    logger.warning("Failed to add fix to RAG: %s", e)

            return result

        except Exception as e:
            elapsed = (datetime.now()-start).total_seconds()
            return FixResult(False, file_path, len(original) if "original" in locals() else 0, 0, [str(e)], [], None, elapsed, 0.0, 0,0,0, False)
