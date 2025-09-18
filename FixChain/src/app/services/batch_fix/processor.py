# src/app/services/batch_fix/processor.py
from __future__ import annotations
import os, json, fnmatch, shutil
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from datetime import datetime

from src.app.adapters.serena_client import SerenaMCPClient
from src.app.services.log_service import logger
from src.app.services.batch_fix.models import FixResult
from src.app.services.batch_fix import validators as V
from src.app.services.batch_fix.templates import TemplateManager, strip_markdown_code
from src.app.services.batch_fix.rag_integration import RAGAdapter
from src.app.adapters.llm.google_genai import client, GENERATION_MODEL

class SecureFixProcessor:
    def __init__(self, source_dir: str, backup_dir: Optional[str] = None, similarity_threshold: float = 0.85, enable_serena: bool = False) -> None:
        self.source_dir = os.path.abspath(source_dir)
        self.backup_dir = backup_dir or ""
        self.similarity_threshold = similarity_threshold
        self.ignore_patterns: List[str] = []
        self.tm = TemplateManager()
        self.rag = RAGAdapter()
        self.serena_client = SerenaMCPClient()
        self.enable_serena = enable_serena
        
        if self.enable_serena:
            logger.info("🤖 SecureFixProcessor: Serena MCP integration enabled")
        else:
            logger.info("ℹ️ SecureFixProcessor: Using standard LLM mode (no Serena)")

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
        logger.info(f"[EXECUTION FLOW] 🚀 Starting file processing: {os.path.basename(file_path)}")
        logger.info(f"[EXECUTION FLOW] 📊 Issues count: {len(issues_data) if issues_data else 0}")
        logger.info(f"[EXECUTION FLOW] 🤖 Serena enabled: {self.enable_serena}")
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
                tpl, tpl_vars = self.tm.load(template_type)
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

                # Handle Serena MCP integration if enabled
                if self.enable_serena and "=== SERENA FIX INSTRUCTIONS START ===" in text:
                    logger.info("[SERENA INTEGRATION] 🎯 Detected Serena instructions in LLM response")
                    
                    # Extract Serena instructions from LLM response
                    serena_instructions = self._extract_serena_instructions(text)
                    
                    if serena_instructions:
                        logger.info("[SERENA INTEGRATION] 📋 Extracted Serena instructions (%d chars)", len(serena_instructions))
                        # Log preview of instructions
                        instruction_lines = serena_instructions.split('\n')[:3]
                        logger.debug("[SERENA INTEGRATION] 📝 Instructions preview:")
                        for i, line in enumerate(instruction_lines, 1):
                            logger.info(f"   Instruction {i}: {line.strip()[:80]}{'...' if len(line.strip()) > 80 else ''}")
                        if len(serena_instructions.split('\n')) > 3:
                            lines = serena_instructions.split('\n')
                            logger.info(f"   ... and {len(lines) - 3} more instruction lines")
                        
                        logger.info("🤖 Serena MCP: Executing fix instructions...")
                        
                        # Use Serena to apply the fixes
                        serena_fixed_code = self._apply_serena_fixes(original, serena_instructions, file_path)
                        
                        if serena_fixed_code:
                            fixed_candidate = serena_fixed_code
                            logger.info(f"✅ Serena MCP: Successfully applied fixes!")
                            logger.info(f"   📊 Original code: {len(original)} chars")
                            logger.info(f"   📊 Fixed code: {len(fixed_candidate)} chars")
                            logger.info(f"   📊 Size change: {len(fixed_candidate) - len(original):+d} chars")
                        else:
                            # FALLBACK: Serena failed, extract fixed code from LLM response
                            logger.warning("⚠️ Serena MCP: Failed to apply fixes, initiating fallback...")
                            llm_fixed_code = self._extract_llm_fixed_code(text)
                            if llm_fixed_code:
                                fixed_candidate = llm_fixed_code
                                logger.info(f"🔄 Fallback: Successfully extracted LLM fixed code ({len(fixed_candidate)} chars)")
                            else:
                                logger.warning("⚠️ Fallback: No fixed code found in LLM response, keeping original")
                                fixed_candidate = original
                    else:
                        # FALLBACK: No Serena instructions, extract fixed code from LLM response
                        logger.warning("⚠️ Serena MCP: Failed to extract valid instructions, initiating fallback...")
                        llm_fixed_code = self._extract_llm_fixed_code(text)
                        if llm_fixed_code:
                            # Check similarity before proceeding
                            temp_sim = V.similarity(original, llm_fixed_code)
                            if temp_sim >= 0.99:  # 99% similarity threshold
                                logger.info("🚫 Skipping file - no Serena instructions and code unchanged (similarity: {:.1%})".format(temp_sim))
                                elapsed = (datetime.now()-start).total_seconds()
                                return FixResult(
                                    False, file_path, len(original), len(original),
                                    ["Skipped: No fix instructions and code unchanged"], [],
                                    None, elapsed, temp_sim, input_tokens, output_tokens, total_tokens, False
                                )
                            fixed_candidate = llm_fixed_code
                            logger.info(f"🔄 Fallback: Successfully extracted LLM fixed code ({len(fixed_candidate)} chars)")
                        else:
                            logger.warning("⚠️ Fallback: No fixed code found in LLM response, keeping original")
                            fixed_candidate = original
                elif self.enable_serena:
                    # Serena enabled but no instructions found
                    logger.warning("⚠️ Serena enabled but no Fix Instructions section found in LLM response")
                    logger.info("🔄 Fallback: Using LLM direct output")
                    llm_fixed_code = self._extract_llm_fixed_code(text)
                    if llm_fixed_code:
                        # Check similarity before proceeding
                        temp_sim = V.similarity(original, llm_fixed_code)
                        if temp_sim >= 0.99:  # 99% similarity threshold
                            logger.info("🚫 Skipping file - no Serena instructions and code unchanged (similarity: {:.1%})".format(temp_sim))
                            elapsed = (datetime.now()-start).total_seconds()
                            return FixResult(
                                False, file_path, len(original), len(original),
                                ["Skipped: No fix instructions and code unchanged"], [],
                                None, elapsed, temp_sim, input_tokens, output_tokens, total_tokens, False
                            )
                        fixed_candidate = llm_fixed_code
                    else:
                        fixed_candidate = original
                else:
                    # Serena not enabled, use standard LLM mode
                    logger.info("ℹ️ Using standard LLM mode (Serena disabled)")
                    fixed_candidate = self._extract_llm_fixed_code(text) or original

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

            logger.info(f"[EXECUTION FLOW] ✅ File processing completed - success: True")
            logger.info(f"[EXECUTION FLOW] ⏱️ Duration: {elapsed:.2f}s")
            logger.info(f"[EXECUTION FLOW] 🎯 Tokens used: {total_tokens}")
            
            return result

        except Exception as e:
            elapsed = (datetime.now()-start).total_seconds()
            logger.info(f"[EXECUTION FLOW] ❌ File processing failed - success: False")
            logger.info(f"[EXECUTION FLOW] ⏱️ Duration: {elapsed:.2f}s")
            logger.info(f"[EXECUTION FLOW] 💥 Error: {str(e)}")
            
            return FixResult(False, file_path, len(original) if "original" in locals() else 0, 0, [str(e)], [], None, elapsed, 0.0, 0,0,0, False)
        

    def _extract_serena_instructions(self, llm_response: str) -> Optional[str]:
        """Extract Serena fix instructions from LLM response"""
        try:
            # Find the Serena Instructions section with new format
            start_marker = "=== SERENA FIX INSTRUCTIONS START ==="
            end_marker = "=== SERENA FIX INSTRUCTIONS END ==="
            
            if start_marker not in llm_response or end_marker not in llm_response:
                logger.info("No Serena Fix Instructions section found in LLM response")
                return None
            
            start_idx = llm_response.find(start_marker) + len(start_marker)
            end_idx = llm_response.find(end_marker)
            
            if start_idx >= end_idx:
                logger.error("Invalid Serena instructions format: start marker after end marker")
                return None
            
            instructions = llm_response[start_idx:end_idx].strip()
            
            if instructions:
                logger.info(f"Found Serena instructions ({len(instructions)} chars)")
                logger.info(f"Instructions preview: {instructions[:100]}{'...' if len(instructions) > 100 else ''}")
                return instructions
            else:
                logger.info("Empty Serena instructions section")
                return None
            
        except Exception as e:
            logger.error(f"Error extracting Serena instructions: {str(e)}")
            return None
    def _apply_serena_fixes(self, original_code: str, instructions: str, file_path: str) -> Optional[str]:
        """Apply fixes using Serena MCP based on LLM instructions"""
        try:
            if not self.serena_client:
                logger.error("[SERENA FIXES] ❌ Serena client not initialized")
                return None
            
            logger.info("[SERENA FIXES] 🔧 Preparing to send instructions...")
            logger.info("[SERENA FIXES] 📁 Target file: %s", os.path.basename(file_path))
            logger.info("[SERENA FIXES] 📝 Original code length: %d chars", len(original_code))
            logger.info("[SERENA FIXES] 📋 Instructions length: %d chars", len(instructions))
            
            # Check if Serena is available
            logger.info("[SERENA FIXES] 🔍 Checking Serena MCP availability...")
            if not self.serena_client.available:
                logger.error("[SERENA FIXES] ❌ Serena MCP is not available")
                return None
            
            logger.info("[SERENA FIXES] ✅ Serena MCP is available, sending request...")
            
            # Prepare context for Serena
            context = f"Apply the following fix instructions:\n{instructions}\n\nFile: {file_path}"
            logger.info("[SERENA FIXES] 📤 Sending context to Serena (%d chars)", len(context))
            
            # Use Serena to apply the fixes based on instructions
            logger.info("[SERENA FIXES] ⚡ Executing apply_fix_instructions...")
            serena_response = self.serena_client.apply_fix_instructions_sync(
                original_code=original_code,
                instructions=instructions,
                file_path=file_path
            )
            
            logger.info("[SERENA FIXES] 📥 Received response from Serena MCP")
            
            if serena_response:
                logger.info("[SERENA FIXES] 📊 Response success: %s", serena_response.success)
                if serena_response.success and serena_response.content:
                    logger.info("[SERENA FIXES] ✅ Successfully received fixed code")
                    logger.info("[SERENA FIXES] 📊 Fixed code length: %d chars", len(serena_response.content))
                    logger.info("[SERENA FIXES] 📊 Size change: %+d chars", len(serena_response.content) - len(original_code))
                    
                    # Log preview of fixed code
                    if serena_response.content != original_code:
                        logger.info("[SERENA FIXES] 📊 Code changes detected")
                        fixed_lines = serena_response.content.split('\n')[:3]
                        logger.debug("[SERENA FIXES] 📝 Preview of fixed code:")
                        for i, line in enumerate(fixed_lines, 1):
                            logger.debug("[SERENA FIXES]    Line %d: %s", i, line[:60] + ('...' if len(line) > 60 else ''))
                        if len(serena_response.content.split('\n')) > 3:
                            lines = serena_response.content.split('\n')
                            logger.debug("[SERENA FIXES]    ... and %d more lines", len(lines) - 3)
                    else:
                        logger.info("[SERENA FIXES] ℹ️ No changes made to code")
                    
                    return serena_response.content
                else:
                    error_msg = serena_response.error if hasattr(serena_response, 'error') and serena_response.error else "No improved code returned"
                    logger.error("[SERENA FIXES] ❌ Failed to apply fixes: %s", error_msg)
                    return None
            else:
                logger.error("[SERENA FIXES] ❌ Received null/empty response")
                return None
                
        except Exception as e:
            logger.error("[SERENA FIXES] ❌ Error applying Serena fixes: %s", str(e))
            logger.error("[SERENA FIXES] 🔍 Exception type: %s", type(e).__name__)
            return None
        finally:
            # Cleanup server resources after each fix attempt to prevent multiple instances
            if self.serena_client:
                logger.debug("[SERENA FIXES] 🧹 Cleaning up server resources...")
                self.serena_client.cleanup_server()
    
    def _extract_llm_fixed_code(self, llm_response: str) -> Optional[str]:
        """Extract fixed source code from LLM response when Serena fails (fallback mechanism)"""
        try:
            # Look for "## 2. Fixed Source Code" section (fallback format)
            fixed_code_marker = "## 2. Fixed Source Code"
            if fixed_code_marker in llm_response:
                start_idx = llm_response.find(fixed_code_marker)
                remaining_text = llm_response[start_idx + len(fixed_code_marker):]
                
                # Find the next section marker or end of text
                next_section_idx = remaining_text.find("\n##")
                if next_section_idx != -1:
                    fixed_section = remaining_text[:next_section_idx].strip()
                else:
                    fixed_section = remaining_text.strip()
                
                # Extract code from code blocks
                import re
                code_blocks = re.findall(r'```(?:\w+)?\n(.*?)\n```', fixed_section, re.DOTALL)
                if code_blocks:
                    return code_blocks[0].strip()
                
                # If no code blocks, try to extract the content after the marker
                lines = fixed_section.split('\n')
                code_lines = []
                for line in lines:
                    if line.strip() and not line.startswith('#') and not line.startswith('-'):
                        code_lines.append(line)
                
                if code_lines:
                    return '\n'.join(code_lines)
            
            # Alternative: Look for any code block in the response
            import re
            code_blocks = re.findall(r'```(?:\w+)?\n(.*?)\n```', llm_response, re.DOTALL)
            if code_blocks:
                # Return the largest code block (likely the fixed code)
                return max(code_blocks, key=len).strip()
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting LLM fixed code: {str(e)}")
            return None
    
    def _save_fixed_file(self, original_path: str, fixed_content: str) -> str:
        """Save fixed file directly to original location"""
        # Always overwrite original file
        with open(original_path, 'w', encoding='utf-8') as f:
            f.write(fixed_content)
        return original_path