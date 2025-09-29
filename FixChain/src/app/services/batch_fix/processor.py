# src/app/services/batch_fix/processor.py
from __future__ import annotations
import os, json, fnmatch
import re
from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime
from src.app.services.log_service import logger
from src.app.services.batch_fix.models import FixResult
from src.app.services.batch_fix import validators as V
from src.app.services.batch_fix.templates import TemplateManager, strip_markdown_code
from src.app.services.batch_fix.rag_integration import RAGAdapter
from src.app.adapters.llm.google_genai import client, GENERATION_MODEL

MARKER_START = "=== SERENA FIX INSTRUCTIONS START ==="
MARKER_END = "=== SERENA FIX INSTRUCTIONS END ==="
_RE_FLAG_MAP = {
    "I": re.IGNORECASE, "IGNORECASE": re.IGNORECASE,
    "M": re.MULTILINE,  "MULTILINE": re.MULTILINE,
    "S": re.DOTALL,     "DOTALL": re.DOTALL,
    "X": re.VERBOSE,    "VERBOSE": re.VERBOSE,
}

class SecureFixProcessor:
    def __init__(self, source_dir: str) -> None:
        self.source_dir = os.path.abspath(source_dir)
        self.similarity_threshold = 0.85
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
        rel = os.path.relpath(abs_path, os.path.abspath(base_dir)).replace("\\","/")
        for p in self.ignore_patterns:
            if p.endswith("/") and (rel.startswith(p) or f"/{p}" in f"/{rel}/"): return True
            if fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(os.path.basename(path), p): return True
        return False

    def fix_buggy_file(self, file_path: str, template_type: str, issues_data: Optional[List[Dict]] = None) -> FixResult:
        """
        issues_data generate: 
        -> labeled_signals = self._normalize_labeled_signals(list_bugs)
        -> list_real_bugs = analysis.get("list_bugs")
        issues_data format:
        {
        "app.py": [
            {
            "key": "2e018b6e4219d525e9e9f6283d2d8403_0",
            "label": "BUG",
            "id": "python_lang_insecure_http",
            "classification": "True Positive",
            "reason": "The code uses HTTP instead of HTTPS. RAG: insecure HTTP connection",
            "title": "Usage of insecure HTTP connection",
            "lang": "python",
            "file_name": "app.py",
            "code_snippet": "        requests.post(\"http://example.com/collect\", json={\"pwd\": password})",
            "line_number": "187",
            "severity": "CRITICAL"
            },
            {
            "key": "65c9c2496677f21552e48b34c59791e4_0",
            "label": "BUG",
            "id": "python_lang_weak_hash_md5",
            "classification": "True Positive",
            "reason": "The code uses MD5 for hashing, which is a weak hashing algorithm. RAG: weak hashing library (MDx)",
            "title": "Usage of weak hashing library (MDx)",
            "lang": "python",
            "file_name": "app.py",
            "code_snippet": "    pwd_hash = hashlib.md5(password.encode()).hexdigest()",
            "line_number": "48",
            "severity": "MEDIUM"
            }
        ]
        }
        """
        start = datetime.now()
        input_tokens = output_tokens = total_tokens = 0
        rag_context = self.rag.search_context(issues_data) or ""
        logger.debug(f"Fixer RAG retrieved context: {rag_context[:100]}")
        original = ""
        final_content = ""
        validation_errors = []
        try:
            original = Path(file_path).read_text(encoding="utf-8") 
            # load template
            tpl, tpl_vars = self.tm.load(template_type)
            if tpl is None:
                raise RuntimeError("Template not found. Put templates in src/app/prompts/")
            
            ok, errs = V.validate_by_ext(file_path, original)
            if not ok:
                validation_errors += errs
            
            rendered = tpl(
                original_code=original,
                validation_rules=V.get_rules_for(file_path),
                validation_errors=validation_errors,
                issues_log=json.dumps(issues_data or [], ensure_ascii=False, indent=2),
                rag_suggestion=rag_context,
                has_rag_suggestion=bool(rag_context),
                **tpl_vars,
            ) if callable(tpl) else str(tpl)

            self.tm.log_template_usage(file_path, template_type, rendered)

            # === google-genai call ===
            resp = client.models.generate_content(model=GENERATION_MODEL, contents=rendered)
            text = getattr(resp, "text", "") or ""
            logger.debug(f"Gemini response: {text[:100]}")

            default_llm_file  = strip_markdown_code(text)

            sections  = self._extract_sections(text)
            logger.debug(sections)
            serena_json  = sections.get("serena_json")
            fixed_code_block = sections.get("fixed_code_block")

            if serena_json:
                logger.info(f"Applying Serena-based patches, preview: {serena_json[:200]}")
                serena_applied = self._apply_serena_fixes(original, serena_json, file_path)

                if serena_applied:
                    try:
                        logger.debug("Applied Serena patches")
                        final_content = Path(file_path).read_text(encoding="utf-8")
                    except Exception as e:
                        logger.warning("Patched but could not read back file: %s", e)
                else:
                    if fixed_code_block:
                        final_content = strip_markdown_code(fixed_code_block)
                        logger.debug(f"Fixed code block preview: {fixed_code_block[:100]}")
                        logger.info("Serena returned no changes; fallback to LLM full-file replacement")
                    else:
                        logger.error("No fixed code in LLM response")
                        final_content = default_llm_file
            elif fixed_code_block:
                final_content = strip_markdown_code(fixed_code_block)
                logger.debug(f"Fixed code block preview: {fixed_code_block[:100]}")
                logger.info("No serena instruction returned; fallback to LLM full-file replacement")
            else:
                logger.error("No serena instruction and fixed code in LLM response")
                final_content = default_llm_file

            if final_content:
                logger.debug(f"Final content: {final_content[:100]}")
                Path(file_path).write_text(final_content, encoding="utf-8")

                safe, s_issues = V.validate_safety(original, final_content)
                if not safe:
                    validation_errors += s_issues
            else:
                raise RuntimeError("No valid fixed content produced") 
            

            usage = getattr(resp, "usage_metadata", None)
            if usage:
                input_tokens = getattr(usage, "prompt_token_count", 0)
                output_tokens = getattr(usage, "candidates_token_count", 0)
                total_tokens = getattr(usage, "total_token_count", 0)

            self.tm.log_ai_response(file_path, text, default_llm_file)

            elapsed = (datetime.now()-start).total_seconds()
            similar = V.similarity(original, final_content)
            meet_similar = similar >= self.similarity_threshold
            result = FixResult(
                success=True, 
                file_path=file_path, 
                original_size=len(original), 
                fixed_size=len(final_content),
                message=f"Size change: {len(final_content)-len(original)} bytes",
                validation_errors=validation_errors,
                processing_time=elapsed, 
                similarity_ratio=similar,
                input_tokens=input_tokens, 
                output_tokens=output_tokens, 
                total_tokens=total_tokens, 
                meets_threshold=meet_similar
            )

            try:
                self.rag.add_fix(result, issues_data, final_content)
            except Exception as e:
                logger.warning("Failed to add fix to RAG: %s", e)

        except Exception as e:
            result = FixResult(
                success=False, 
                file_path=file_path, 
                original_size=len(original), 
                fixed_size=0,
                message=f"{e}",
                validation_errors=validation_errors,
                processing_time=0, 
                similarity_ratio=0,
                input_tokens=0, 
                output_tokens=0, 
                total_tokens=0, 
                meets_threshold=False
            )

        return result
        
    def _clean_instruction_block(self, s: str) -> str:
        """Make the LLM block parseable:
        - drop code fences ```json ... ```
        - extract the substring between START/END markers
        - normalize quotes
        - remove trailing commas before } or ]
        """
        if not s:
            return ""
        s = s.strip().replace("\r\n", "\n").replace("\r", "\n")

        # 1) Strip outer code fences if present
        s = re.sub(r"^```(?:json|yaml)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*```$", "", s)

        # 2) Extract JSON between markers if present
        m = re.search(rf"{re.escape(MARKER_START)}\s*(.*?)\s*{re.escape(MARKER_END)}", s, re.DOTALL)
        if m:
            s = m.group(1).strip()

        # 3) Normalize smart quotes
        s = (s.replace("\u201c", '"')
            .replace("\u201d", '"')
            .replace("\u2018", "'")
            .replace("\u2019", "'"))

        # 4) Remove trailing commas before } or ]
        s = re.sub(r",(\s*[}\]])", r"\1", s)

        return s
    
    def _extract_sections(self, llm_response: str) -> Dict[str, Optional[str]]:
        """Extract Serena JSON, Change Log, and Fixed Code by hard markers."""
        def grab(start: str, end: str) -> Optional[str]:
            if start not in llm_response or end not in llm_response:
                return None
            s = llm_response.find(start) + len(start)
            e = llm_response.find(end, s)
            if e == -1 or s >= e:
                return None
            return llm_response[s:e].strip()

        return {
            "serena_json": grab("=== SERENA FIX INSTRUCTIONS START ===",
                                "=== SERENA FIX INSTRUCTIONS END ==="),
            "change_log": grab("=== CHANGE LOG START ===",
                            "=== CHANGE LOG END ==="),
            "fixed_code_block": grab("=== FIXED SOURCE CODE START ===",
                                    "=== FIXED SOURCE CODE END ==="),
        }

    def _safe_join(self, base: str, rel: str) -> str:
        p = Path(base).joinpath(rel).resolve()
        if not str(p).startswith(str(Path(base).resolve())):
            raise ValueError(f"Path escapes project root: {rel}")
        return str(p)

    def _repo_root_guess(self) -> str:
        # ưu tiên .git lên trên, hoặc dùng self.source_dir
        here = Path(self.source_dir).resolve()
        for p in [here] + list(here.parents):
            if (p / ".git").exists():
                return str(p)
        return str(here)

    def _parse_instructions(self, instructions: str) -> dict:
        payload = self._clean_instruction_block(instructions)
        if not payload:
            raise ValueError("Empty Serena instructions")
        
        try:
            return json.loads(payload)
        except Exception:
            try:
                import yaml  # optional
                return yaml.safe_load(payload)
            except Exception:
                raise ValueError("Serena instructions must be JSON or YAML")

    def _norm_regex_flags(self, flags: Any) -> Optional[int]:
        """Chuyển flags từ 'MULTILINE' | 'M' | ['MULTILINE','IGNORECASE'] | int → int bitmask."""
        if flags is None or flags == "":
            return None
        if isinstance(flags, int):
            return flags
        parts: List[str]
        if isinstance(flags, str):
            parts = re.split(r"[|,\s]+", flags.strip())
        elif isinstance(flags, list):
            parts = [str(x) for x in flags]
        else:
            return None
        val = 0
        for p in parts:
            if not p:
                continue
            key = p.upper()
            if key in _RE_FLAG_MAP:
                val |= _RE_FLAG_MAP[key]
            else:
                logger.warning("Unknown regex flag: %s", p) if hasattr(self, "logger") else None
        return val or None

    async def _run_serena_steps(self, project_root: str, steps: list) -> int:
        """Trả về số step áp dụng thành công."""
        from src.app.adapters.serena_client import SerenaClient, SerenaError  # tránh import vòng
        applied = 0
        async with SerenaClient(project_path=project_root) as sc:
            tools = await sc.list_tools()
            logger.debug("Serena tools: %s", tools) if hasattr(self, "logger") else None

            for idx, step in enumerate(steps, start=1):
                op = (step.get("op") or "").lower()
                try:
                    # chuẩn hoá số liệu
                    if op == "regex_replace":
                        # flags → int
                        norm = self._norm_regex_flags(step.get("flags"))
                        if norm is not None:
                            step["flags"] = norm
                        # compile thử để bắt pattern lỗi sớm
                        try:
                            re.compile(step["pattern"], norm or 0)
                        except re.error as e:
                            logger.error("Invalid regex at step %d: %s", idx, e)
                            continue

                        await sc.apply_patch_by_regex(
                            path=step["path"],
                            pattern=step["pattern"],
                            replacement=step["replacement"],
                            count=step.get("count"),
                            flags=step.get("flags"),  # đã là int
                        )
                        applied += 1

                    elif op == "replace_symbol_body":
                        await sc.apply_patch_by_symbol(
                            name_path=step["name_path"],
                            relative_path=step.get("relative_path") or step.get("path") or "",
                            new_body=step["new_body"],
                        )
                        applied += 1

                    elif op == "replace_lines":
                        await sc.replace_lines(
                            path=step["path"],
                            start_line=int(step["start_line"]),
                            end_line=int(step["end_line"]),
                            new_text=step["new_text"],
                        )
                        applied += 1

                    elif op == "insert_before_symbol":
                        await sc.insert_before_symbol(
                            name_path=step["name_path"],
                            relative_path=step.get("relative_path") or step.get("path") or "",
                            text=step["text"],
                        )
                        applied += 1

                    elif op == "insert_after_symbol":
                        await sc.insert_after_symbol(
                            name_path=step["name_path"],
                            relative_path=step.get("relative_path") or step.get("path") or "",
                            text=step["text"],
                        )
                        applied += 1

                    elif op == "exec":
                        # chỉ chạy nếu tool có mặt (tránh fail ở build Serena không expose tool này)
                        if "execute_shell_command" in tools:
                            await sc.execute_shell_command(
                                command=step["command"],
                                timeout_s=step.get("timeout_s", 300),
                                cwd=step.get("cwd"),
                                env=step.get("env"),
                                shell=step.get("shell"),
                            )
                        else:
                            logger.info("Skip exec: execute_shell_command not exposed")
                    else:
                        logger.warning("Unknown Serena op at step %d: %s", idx, op)

                except SerenaError as e:
                    # log đầy đủ và sang step kế tiếp
                    logger.error("Serena step %d (%s) failed: %s", idx, op, e, exc_info=True)
                except Exception as e:
                    logger.error("Unexpected error at step %d (%s): %s", idx, op, e, exc_info=True)

        return applied

    def _apply_serena_fixes(self, original_code: str, instructions: str, file_path: str) -> Optional[str]:
        try:
            payload = self._parse_instructions(instructions)
            project_root = payload.get("project_root") or self._repo_root_guess()
            steps = payload.get("steps") or []
            if not steps:
                logger.info("No steps in Serena instructions")
                return None

            # Bảo vệ path: ép về tương đối, tránh thoát root
            fixed_steps = []
            for st in steps:
                st = dict(st)  # copy
                p = st.get("path")
                if p:
                    # giữ tương đối với root
                    abs_p = self._safe_join(project_root, p)
                    st["path"] = str(Path(abs_p).relative_to(project_root))
                rp = st.get("relative_path")
                if rp:
                    abs_rp = self._safe_join(project_root, rp)
                    st["relative_path"] = str(Path(abs_rp).relative_to(project_root))
                fixed_steps.append(st)

            import asyncio
            applied = asyncio.run(self._run_serena_steps(project_root, fixed_steps))

            return "OK" if applied > 0 else None
        except Exception as e:
            logger.error("Apply Serena fixes failed: %s", e, exc_info=True)
            return None