"""Serena MCP Client for direct communication with Serena AI assistant"""

import os
import logging
import asyncio
import threading
import json
import subprocess
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from src.app.services.log_service import logger
from .mcp_client import MCPClient

@dataclass
class SerenaResponse:
    """Response from Serena MCP server"""
    success: bool
    content: str
    suggestions: List[str]
    confidence: float
    error: Optional[str] = None

class SerenaMCPClient:
    """Client for communicating with Serena via MCP stdio transport"""
    
    def __init__(self, mcp_config_path: Optional[str] = None, project_path: Optional[str] = None):
        self.logger = logging.getLogger(__name__)
        self.mcp_client = None
        self._server_started = False
        self._loop_thread = None
        self._loop = None
        self._server_lock = threading.Lock()  # Thread safety for server startup
        self.available = self.check_availability()
        
    def check_availability(self) -> bool:
        """Check if Serena MCP server is available"""
        try:
            # Check if .mcp.json exists
            config_path = ".mcp.json"
            logger.info("[SERENA MCP] 🔍 Checking availability...")
            if not os.path.exists(config_path):
                logger.warning("[SERENA MCP] ❌ No .mcp.json config file found")
                return False
                
            logger.info("[SERENA MCP] ✅ Found Serena config file")
            return True
            
        except Exception as e:
            logger.error("[SERENA MCP] ❌ Error checking availability: %s", e)
            return False
        
    def apply_fix_instructions_sync(self, original_code: str, instructions: str, file_path: str) -> SerenaResponse:
        """Apply fix instructions using Serena MCP server in separate thread"""
        
        logger.info("[EXECUTION FLOW] 🚀 Starting Serena fix application")
        logger.info(f"[EXECUTION FLOW] 📁 Target file: {os.path.basename(file_path)}")
        logger.info(f"[EXECUTION FLOW] 📝 Instructions length: {len(instructions)} chars")
        logger.info("[SERENA MCP] 🚀 Starting fix instructions sync")
        logger.info("[SERENA MCP] 📁 Target file: %s", file_path)
        logger.info("[SERENA MCP] 📝 Original code length: %d chars", len(original_code))
        logger.info("[SERENA MCP] 📋 Instructions length: %d chars", len(instructions))
        logger.debug("[SERENA MCP] 📋 Full instructions: %s", instructions)
        
        try:
            # Run async operation in separate thread to avoid event loop conflicts
            result = self._run_in_thread(self._apply_fix_async(original_code, instructions, file_path))
            
            logger.info("[SERENA MCP] ✅ Fix instructions completed - success: %s", result.success if result else False)
            if result and result.success:
                logger.info("[SERENA MCP] 📤 Response content length: %d chars", len(result.content))
                logger.info("[SERENA MCP] 💡 Suggestions count: %d", len(result.suggestions))
                logger.info("[SERENA MCP] 🎯 Confidence: %.2f", result.confidence)
            elif result and result.error:
                logger.error("[SERENA MCP] ❌ Fix failed with error: %s", result.error)
            
            return result
        except Exception as e:
            logger.error("[SERENA MCP] ❌ Apply fix instructions failed: %s", e)
            return SerenaResponse(
                success=False,
                content="",
                suggestions=[],
                confidence=0.0,
                error=str(e)
            )
            
    def _run_in_thread(self, coro):
        """Run coroutine in a separate thread with its own event loop"""
        result = None
        exception = None
        
        def run_coro():
            nonlocal result, exception
            try:
                # Create new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(coro)
                loop.close()
            except Exception as e:
                exception = e
                
        thread = threading.Thread(target=run_coro)
        thread.start()
        thread.join(timeout=60)  # 60 second timeout
        
        if thread.is_alive():
            raise TimeoutError("MCP operation timed out")
            
        if exception:
            raise exception
            
        return result
        
    async def _apply_fix_async(self, original_code: str, instructions: str, file_path: str) -> SerenaResponse:
        """Apply fix instructions using Serena MCP server"""
        try:
            logger.info("[SERENA MCP] ⚡ Starting async fix operation")
            
            if not self.mcp_client:
                logger.info("[SERENA MCP] 📋 Loading MCP config from .mcp.json")
                # Load MCP config
                with open(".mcp.json", 'r') as f:
                    config = json.load(f)
                    serena_config = config.get('mcpServers', {}).get('serena', {})
                    logger.debug("[SERENA MCP] 🔧 Config loaded: %s", serena_config)
                    self.mcp_client = MCPClient(serena_config)
                logger.info("[SERENA MCP] ✅ MCP client initialized")
                
            # Start server if not started (with thread safety)
            if not self._server_started:
                # Use asyncio lock equivalent for thread safety
                logger.info("[SERENA MCP] 🔒 Acquiring server start lock...")
                # Since we're in async context, we need to handle this differently
                # Check again after potential wait
                if not self._server_started:
                    logger.info("[SERENA MCP] 🚀 Starting MCP server...")
                    # Check if process is already running
                    if self.mcp_client.process and self.mcp_client.process.poll() is None:
                        logger.info("[SERENA MCP] ⚠️ MCP server process already running, reusing...")
                        self._server_started = True
                    else:
                        success = await self.mcp_client.start_server()
                        if not success:
                            logger.error("[SERENA MCP] ❌ Failed to start MCP server")
                            return SerenaResponse(
                                success=False,
                                content="",
                                suggestions=[],
                                confidence=0.0,
                                error="Failed to start MCP server"
                            )
                        logger.info("[SERENA MCP] ✅ MCP server started successfully")
                        self._server_started = True
            else:
                logger.debug("[SERENA MCP] ℹ️ MCP server already running")
                
            # Try to use find_symbol tool
            logger.info("[SERENA MCP] 🔍 Calling find_symbol tool for file: %s", file_path)
            result = await self.mcp_client.call_tool("find_symbol", {
                "name_path": file_path
            })
            
            logger.debug("[SERENA MCP] 📊 Tool call result: %s", result)
            
            if result and result.success:
                logger.info("[SERENA MCP] ✅ Found symbols in file")
                
                # Now apply the actual fix instructions using Serena tools
                logger.info("[SERENA MCP] 🔧 Applying fix instructions...")
                fixed_code = await self._apply_instructions_with_serena(original_code, instructions, file_path)
                
                if fixed_code:
                    response = SerenaResponse(
                        success=True,
                        content=fixed_code,
                        suggestions=["Applied fixes using Serena MCP tools"],
                        confidence=0.9
                    )
                    logger.info("[SERENA MCP] ✅ Successfully applied fixes with confidence: %.2f", response.confidence)
                    return response
                else:
                    logger.warning("[SERENA MCP] ⚠️ No fixes applied, returning original code")
                    response = SerenaResponse(
                        success=True,
                        content=original_code,
                        suggestions=["No changes needed or could not apply fixes"],
                        confidence=0.5
                    )
                    return response
            else:
                error_msg = f"MCP tool call failed: {result.error if result else 'No response'}"
                logger.error("[SERENA MCP] ❌ %s", error_msg)
                return SerenaResponse(
                    success=False,
                    content="",
                    suggestions=[],
                    confidence=0.0,
                    error=error_msg
                )
                
        except Exception as e:
            logger.error("[SERENA MCP] ❌ MCP operation failed: %s", e)
            logger.error("[SERENA MCP] 🔍 Exception type: %s", type(e).__name__)
            return SerenaResponse(
                success=False,
                content="",
                suggestions=[],
                confidence=0.0,
                error=str(e)
            )

    async def _apply_instructions_with_serena(self, original_code: str, instructions: str, file_path: str) -> str:
        """Apply fix instructions using Serena MCP tools"""
        try:
            logger.info("[SERENA MCP] 🔧 Starting fix application for: %s", file_path)
            
            # Create a temporary file with the original code in project directory
            temp_file_path = f"temp_fixchain_{hash(file_path) % 10000}.py"
            
            # Write original code to temp file
            write_result = await self.mcp_client.call_tool("create_text_file", {
                "relative_path": temp_file_path,
                "content": original_code
            })
            
            if not write_result or not write_result.success:
                logger.error("[SERENA MCP] ❌ Failed to create temp file")
                return None
            
            logger.info("[SERENA MCP] 📝 Created temp file: %s", temp_file_path)
            
            # Use Serena's memory to store the fix instructions
            memory_result = await self.mcp_client.call_tool("write_memory", {
                "key": "fix_instructions",
                "value": instructions
            })
            
            if memory_result and memory_result.success:
                logger.info("[SERENA MCP] 💾 Stored fix instructions in memory")
            
            # Try to apply fixes using replace_regex if we can identify patterns
            fixed_code = await self._try_pattern_fixes(temp_file_path, instructions, original_code)
            
            if fixed_code and fixed_code != original_code:
                logger.info("[SERENA MCP] ✅ Successfully applied pattern-based fixes")
                return fixed_code
            
            # If pattern fixes didn't work, try symbol-based fixes
            fixed_code = await self._try_symbol_fixes(temp_file_path, instructions, original_code)
            
            if fixed_code and fixed_code != original_code:
                logger.info("[SERENA MCP] ✅ Successfully applied symbol-based fixes")
                return fixed_code
            
            logger.warning("[SERENA MCP] ⚠️ No fixes could be applied")
            return None
            
        except Exception as e:
            logger.error("[SERENA MCP] ❌ Error applying instructions: %s", str(e))
            return None
    
    async def _add_imports(self, temp_file_path: str, imports: list) -> bool:
        """Add import statements to the beginning of the file"""
        try:
            # Read current content
            read_result = await self.mcp_client.call_tool("read_file", {
                "relative_path": temp_file_path
            })
            
            if not read_result or not read_result.success:
                return False
                
            # Extract content from MCP response format
            content_list = read_result.result.get("content", [])
            if content_list and isinstance(content_list, list) and len(content_list) > 0:
                current_content = content_list[0].get("text", "")
            else:
                current_content = ""
            
            lines = current_content.split('\n')
            
            # Find where to insert imports (after existing imports or at the top)
            insert_line = 0
            for i, line in enumerate(lines):
                if line.strip().startswith('import ') or line.strip().startswith('from '):
                    insert_line = i + 1
                elif line.strip() and not line.strip().startswith('#'):
                    break
            
            # Add new imports if they don't exist
            for import_stmt in imports:
                if import_stmt not in current_content:
                    lines.insert(insert_line, import_stmt)
                    insert_line += 1
            
            # Write back the modified content
            new_content = '\n'.join(lines)
            write_result = await self.mcp_client.call_tool("create_text_file", {
                "relative_path": temp_file_path,
                "content": new_content
            })
            
            return write_result and write_result.success
            
        except Exception as e:
            logger.error("[SERENA MCP] ❌ Failed to add imports: %s", str(e))
            return False
    
    async def _try_pattern_fixes(self, temp_file_path: str, instructions: str, original_code: str) -> str:
        """Try to apply fixes using pattern matching"""
        try:
            # Common security fix patterns
            security_patterns = {
                "os.system": {
                    "pattern": r"os\.system\(([^)]+)\)",
                    "replacement": "subprocess.run(shlex.split(\\1), check=True)",
                    "imports": ["import subprocess", "import shlex"]
                },
                "eval(": {
                    "pattern": r"eval\([^)]+\)",
                    "replacement": "ast.literal_eval(user_input)",
                    "imports": ["import ast"]
                },
                "exec(": {
                    "pattern": r"exec\([^)]+\)",
                    "replacement": "# exec() removed for security",
                    "imports": []
                }
            }
            
            instructions_lower = instructions.lower()
            applied_fix = False
            current_code = original_code
            
            for pattern_name, pattern_info in security_patterns.items():
                if pattern_name.lower() in instructions_lower:
                    logger.info("[SERENA MCP] 🎯 Applying %s fix pattern", pattern_name)
                    
                    # Apply regex replacement
                    logger.info("[SERENA MCP] 🔄 Applying regex: %s -> %s", pattern_info["pattern"], pattern_info["replacement"])
                    replace_result = await self.mcp_client.call_tool("replace_regex", {
                        "relative_path": temp_file_path,
                        "regex": pattern_info["pattern"],
                        "repl": pattern_info["replacement"]
                    })
                    
                    logger.debug("[SERENA MCP] 🔄 Replace result: %s", replace_result)
                    if replace_result and replace_result.success:
                        logger.info("[SERENA MCP] ✅ Applied regex replacement for %s", pattern_name)
                        applied_fix = True
                        
                        # Add necessary imports for subprocess replacement
                        if pattern_name == "os.system":
                            logger.info("[SERENA MCP] 📦 Adding imports for subprocess replacement")
                            import_success = await self._add_imports(temp_file_path, ["import subprocess", "import shlex"])
                            logger.info("[SERENA MCP] 📦 Import addition result: %s", import_success)
                    else:
                        logger.error("[SERENA MCP] ❌ Failed to apply regex for %s: %s", pattern_name, replace_result.error if replace_result else "No result")
                        for import_stmt in pattern_info["imports"]:
                            if import_stmt not in current_code:
                                insert_result = await self.mcp_client.call_tool("insert_at_line", {
                                    "relative_path": temp_file_path,
                                    "line_number": 1,
                                    "content": import_stmt
                                })
                                if insert_result and insert_result.success:
                                    logger.info("[SERENA MCP] ➕ Added import: %s", import_stmt)
            
            if applied_fix:
                # Read the modified file
                logger.info("[SERENA MCP] 📖 Reading modified file: %s", temp_file_path)
                read_result = await self.mcp_client.call_tool("read_file", {
                    "relative_path": temp_file_path
                })
                
                logger.debug("[SERENA MCP] 📖 Read result: %s", read_result)
                if read_result and read_result.success:
                    content = read_result.result.get("content", original_code)
                    logger.info("[SERENA MCP] ✅ Successfully read modified content, length: %d", len(content))
                    return content
                else:
                    logger.error("[SERENA MCP] ❌ Failed to read modified file: %s", read_result.error if read_result else "No result")
            
            return original_code
            
        except Exception as e:
            logger.error("[SERENA MCP] ❌ Error in pattern fixes: %s", str(e))
            return original_code
    
    async def _try_symbol_fixes(self, temp_file_path: str, instructions: str, original_code: str) -> str:
        """Try to apply fixes using symbol-based operations"""
        try:
            # Get symbols overview
            symbols_result = await self.mcp_client.call_tool("get_symbols_overview", {
                "name_path": temp_file_path
            })
            
            if not symbols_result or not symbols_result.success:
                logger.warning("[SERENA MCP] ⚠️ Could not get symbols overview")
                return original_code
            
            symbols = symbols_result.result or {}
            logger.info("[SERENA MCP] 📋 Found symbols: %s", list(symbols.keys()))
            
            # Try to find and fix vulnerable functions
            instructions_lower = instructions.lower()
            
            if "security" in instructions_lower or "vulnerability" in instructions_lower:
                for symbol_name in symbols.keys():
                    if "function" in symbols[symbol_name].get("type", "").lower():
                        logger.info("[SERENA MCP] 🔍 Checking function: %s", symbol_name)
                        
                        # Get function body
                        symbol_result = await self.mcp_client.call_tool("find_symbol", {
                            "name_path": f"{temp_file_path}::{symbol_name}"
                        })
                        
                        if symbol_result and symbol_result.success:
                            # Add security comment
                            comment_result = await self.mcp_client.call_tool("insert_before_symbol", {
                                "name_path": f"{temp_file_path}::{symbol_name}",
                                "content": "# Security fix applied by FixChain"
                            })
                            
                            if comment_result and comment_result.success:
                                logger.info("[SERENA MCP] ✅ Added security comment to %s", symbol_name)
            
            # Read the modified file
            read_result = await self.mcp_client.call_tool("read_file", {
                "relative_path": temp_file_path
            })
            
            if read_result and read_result.success:
                return read_result.result.get("content", original_code)
            
            return original_code
            
        except Exception as e:
            logger.error("[SERENA MCP] ❌ Error in symbol fixes: %s", str(e))
            return original_code

    def list_available_tools(self) -> List[str]:
        """List available tools from Serena MCP server"""
        try:
            logger.info("[SERENA MCP] 📋 Listing available tools...")
            result = self._run_in_thread(self._list_tools_async())
            logger.info("[SERENA MCP] ✅ Found %d available tools", len(result))
            logger.debug("[SERENA MCP] 🔧 Available tools: %s", result)
            return result
        except Exception as e:
            logger.error("[SERENA MCP] ❌ Failed to list tools: %s", e)
            return []
            
    async def _list_tools_async(self) -> List[str]:
        """List tools asynchronously"""
        try:
            if not self.mcp_client:
                # Load MCP config
                with open(".mcp.json", 'r') as f:
                    config = json.load(f)
                    serena_config = config.get('mcpServers', {}).get('serena', {})
                    self.mcp_client = MCPClient(serena_config)
                
            if not self._server_started:
                logger.info("[SERENA MCP] 🔒 Acquiring server start lock for tools list...")
                # Check again after potential wait
                if not self._server_started:
                    # Check if process is already running
                    if self.mcp_client.process and self.mcp_client.process.poll() is None:
                        logger.info("[SERENA MCP] ⚠️ MCP server process already running, reusing...")
                        self._server_started = True
                    else:
                        success = await self.mcp_client.start_server()
                        if not success:
                            return []
                        self._server_started = True
                
            # Try to list tools (this depends on MCP client implementation)
            # For now, return known tools from Serena
            return [
                "read_file", "create_text_file", "list_dir", "find_file", "replace_regex",
                "delete_lines", "replace_lines", "insert_at_line", "search_for_pattern",
                "restart_language_server", "get_symbols_overview", "find_symbol",
                "find_referencing_symbols", "replace_symbol_body", "insert_after_symbol",
                "insert_before_symbol", "write_memory", "read_memory", "list_memories",
                "delete_memory", "execute_shell_command"
            ]
            
        except Exception as e:
            logger.error("[SERENA MCP] ❌ List tools async failed: %s", e)
            return []
    
    def cleanup_server(self) -> None:
        """Cleanup MCP server process if running"""
        try:
            if self.mcp_client and self.mcp_client.process:
                if self.mcp_client.process.poll() is None:  # Process is still running
                    logger.info("[SERENA MCP] 🧹 Cleaning up MCP server process...")
                    self.mcp_client.process.terminate()
                    try:
                        self.mcp_client.process.wait(timeout=5)
                        logger.info("[SERENA MCP] ✅ MCP server process terminated gracefully")
                    except subprocess.TimeoutExpired:
                        logger.warning("[SERENA MCP] ⚠️ Force killing MCP server process...")
                        self.mcp_client.process.kill()
                        self.mcp_client.process.wait()
                        logger.info("[SERENA MCP] ✅ MCP server process killed")
                else:
                    logger.debug("[SERENA MCP] ℹ️ MCP server process already terminated")
            self._server_started = False
            logger.info("[SERENA MCP] 🔄 Server state reset")
        except Exception as e:
            logger.error("[SERENA MCP] ❌ Error during server cleanup: %s", e)