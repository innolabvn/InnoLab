"""Serena MCP Client for direct communication with Serena AI assistant via MCP protocol"""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from src.app.services.log_service import logger
from .mcp_client import MCPClient, MCPResponse

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
        # Use stdio transport instead of HTTP to match running server
        self.mcp_client = None  # Will be initialized when needed
        self.stdio_process = None
        
    def _init_stdio_client(self) -> bool:
        """Initialize stdio MCP client if not already done"""
        if self.stdio_process and self.stdio_process.poll() is None:
            return True
            
        try:
            # Start Serena MCP server
            cmd = [
                "uvx", "--from", "git+https://github.com/oraios/serena",
                "serena-mcp-server", "--transport", "stdio",
                "--project", self.project_path
            ]
            
            logger.info(f"🚀 Starting Serena MCP server: {' '.join(cmd)}")
            
            self.stdio_process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=0
            )
            
            # Wait for server to start
            import time
            time.sleep(2)
            
            # Initialize MCP connection
            import uuid
            init_request = {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "roots": {
                            "listChanged": True
                        },
                        "sampling": {}
                    },
                    "clientInfo": {"name": "fixchain-client", "version": "1.0.0"}
                }
            }
            
            response = self._send_init_request(init_request)
            if response and "result" in response:
                logger.info("✅ Serena MCP initialized successfully")
                
                # Send initialized notification (CRITICAL!)
                initialized_notification = {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {}
                }
                
                # Send notification (no response expected)
                import json
                request_json = json.dumps(initialized_notification) + "\n"
                self.stdio_process.stdin.write(request_json)
                self.stdio_process.stdin.flush()
                
                # Wait for server to process notification
                time.sleep(1)
                
                logger.info("✅ Sent initialized notification")
                return True
            else:
                logger.error("❌ Failed to initialize Serena MCP")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to start Serena MCP server: {e}")
            return False
    
    def _send_init_request(self, request: dict) -> dict:
        """Send initialization request to MCP server"""
        try:
            import json
            import select
            import time
            
            # Send request
            request_json = json.dumps(request) + "\n"
            self.stdio_process.stdin.write(request_json)
            self.stdio_process.stdin.flush()
            
            # Read response with timeout
            timeout = 10.0  # 10 second timeout for initialization
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                if self.stdio_process.stdout in select.select([self.stdio_process.stdout], [], [], 0.1)[0]:
                    response_line = self.stdio_process.stdout.readline()
                    if response_line:
                        try:
                            response = json.loads(response_line.strip())
                            if response.get("id") == request["id"]:
                                return response
                        except json.JSONDecodeError:
                            continue
            
            return {"error": "Initialization timeout"}
            
        except Exception as e:
            logger.error(f"Failed to send init request: {e}")
            return {"error": str(e)}
        
    def check_availability(self) -> bool:
        """Check if Serena MCP is available"""
        logger.info("🔍 Checking Serena MCP availability...")
        
        # Check if .mcp.json exists
        config_available = os.path.exists(self.mcp_config_path)
        logger.info(f"   📄 Config file (.mcp.json): {'✅ Found' if config_available else '❌ Not found'} at {self.mcp_config_path}")
        
        # Check if serena CLI is available
        cli_available = shutil.which("serena") is not None
        logger.info(f"   🖥️ Serena CLI: {'✅ Available' if cli_available else '❌ Not available'}")
        
        # Check if uvx can run serena
        uvx_available = False
        try:
            logger.info("   🔄 Testing uvx serena-agent...")
            result = subprocess.run(["uvx", "--from", "serena-agent", "serena", "--help"], 
                                  capture_output=True, text=True, timeout=5)
            uvx_available = result.returncode == 0
            logger.info(f"   📦 UVX serena-agent: {'✅ Available' if uvx_available else '❌ Failed'} (return code: {result.returncode})")
            if not uvx_available and result.stderr:
                logger.info(f"      ⚠️ UVX error: {result.stderr[:200]}")
        except Exception as e:
            logger.info(f"   📦 UVX serena-agent: ❌ Exception - {str(e)}")
        
        # Check if serena module is available
        module_available = importlib.util.find_spec("serena") is not None
        logger.info(f"   🐍 Serena Python module: {'✅ Available' if module_available else '❌ Not available'}")
        
        # For MCP server mode, we only need config file (server is already running)
        overall_available = config_available
        logger.info(f"   🎯 Overall Serena MCP availability: {'✅ AVAILABLE' if overall_available else '❌ NOT AVAILABLE'}")
        logger.debug(f"Serena MCP availability - Config: {config_available}, CLI: {cli_available}, UVX: {uvx_available}, Module: {module_available} => Available: {overall_available}")
        
        return overall_available
        
    def apply_fix_instructions(self, original_code: str, instructions: str, file_path: str) -> SerenaResponse:
        """Apply fix instructions to code using Serena MCP"""
        try:
            # Write original code to temp file in project directory
            temp_dir = os.path.join(self.project_path, 'temp_files')
            os.makedirs(temp_dir, exist_ok=True)
            tmp = os.path.join(temp_dir, os.path.basename(file_path) or "temp.py")

            with open(tmp, "w", encoding="utf-8") as f:
                f.write(original_code)

            # Try to use real Serena MCP first
            if self._can_use_real_serena():
                commands = self._parse_mcp_instructions(instructions)
                if commands:
                    result = self._execute_mcp_json_rpc(commands, tmp, original_code)
                    if result.success:
                        with open(tmp, "w", encoding="utf-8") as f:
                            f.write(result.content)
                        result = {"applied": 1}
                    else:
                        logger.warning(f"MCP execution failed: {result.error}, falling back to local replacement")
                        result = self._apply_local_replacements(tmp, instructions)
                else:
                    logger.warning("No valid MCP commands found")
                    result = self._apply_local_replacements(tmp, instructions)
            else:
                # Fallback to local replacements
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
    def _can_use_real_serena(self) -> bool:
        """Check if we can use real Serena MCP server"""
        try:
            # Check if Serena CLI is available
            result = subprocess.run(["uvx", "--from", "serena-agent", "serena", "--help"], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and "start-mcp-server" in result.stdout:
                self.logger.info("Serena MCP server is available via uvx")
                return True
            return False
        except Exception as e:
            self.logger.debug(f"Serena MCP server check failed: {e}")
            return False
    
    def _apply_serena_mcp_instructions(self, file_path: str, instructions: str) -> dict:
        """Apply instructions using real Serena MCP server"""
        try:
            # Parse Serena MCP instructions
            mcp_commands = self._parse_mcp_instructions(instructions)
            if not mcp_commands:
                return {"applied": 0, "error": "No valid MCP commands found"}
            
            applied = 0
            for command in mcp_commands:
                try:
                    if self._execute_serena_command(file_path, command):
                        applied += 1
                except Exception as e:
                    self.logger.warning(f"Failed to execute Serena command {command}: {e}")
            
            return {"applied": applied}
        except Exception as e:
            self.logger.error(f"Serena MCP execution failed: {e}")
            return {"applied": 0, "error": str(e)}
    
    def _parse_mcp_instructions(self, instructions: str) -> List[Dict[str, Any]]:
        """Parse Serena MCP instructions into command objects"""
        commands = []
        lines = [ln.strip() for ln in instructions.splitlines() if ln.strip() and not ln.strip().startswith("#")]
        
        for line in lines:
            # Parse different MCP command formats
            if line.startswith("find_symbol:"):
                symbol = line.replace("find_symbol:", "").strip()
                commands.append({"action": "find_symbol", "symbol": symbol})
            elif line.startswith("replace_symbol:"):
                # Support both "with" and "->" formats
                content = line.replace("replace_symbol:", "").strip()
                if " -> " in content:
                    parts = content.split(" -> ", 1)
                    if len(parts) == 2:
                        old_code = parts[0].strip()
                        new_code = self._decode_escape_sequences(parts[1].strip())
                        # Improved symbol extraction from old_code
                        symbol = self._extract_symbol_name(old_code)
                        commands.append({"action": "replace_symbol", "symbol": symbol, "old_code": old_code, "new_code": new_code})
                elif " with " in content:
                    parts = content.split(" with ", 1)
                    if len(parts) == 2:
                        symbol = parts[0].strip()
                        new_code = self._decode_escape_sequences(parts[1].strip())
                        commands.append({"action": "replace_symbol", "symbol": symbol, "new_code": new_code})
            elif line.startswith("insert_after_symbol:"):
                parts = line.replace("insert_after_symbol:", "").split(" code ", 1)
                if len(parts) == 2:
                    symbol = parts[0].strip()
                    code = self._decode_escape_sequences(parts[1].strip())
                    commands.append({"action": "insert_after_symbol", "symbol": symbol, "code": code})
            elif line.startswith("find_referencing_symbols:"):
                symbol = line.replace("find_referencing_symbols:", "").strip()
                commands.append({"action": "find_referencing_symbols", "symbol": symbol})
            # Parse simple text replacement instructions and convert to MCP commands
            elif line.startswith("replace ") and " with " in line:
                parts = line.replace("replace ", "").split(" with ", 1)
                if len(parts) == 2:
                    old_text = parts[0].strip().strip('"').strip("'")
                    new_text = self._decode_escape_sequences(parts[1].strip().strip('"').strip("'"))
                    commands.append({"action": "replace_symbol", "symbol": old_text, "old_code": old_text, "new_code": new_text})
        
        return commands

    def _extract_symbol_name(self, code_snippet: str) -> str:
        """Extract symbol name from code snippet for better matching"""
        code_snippet = code_snippet.strip()
        
        # Handle function definitions
        if code_snippet.startswith("def "):
            match = re.match(r'def\s+(\w+)', code_snippet)
            if match:
                return match.group(1)
        
        # Handle class definitions
        if code_snippet.startswith("class "):
            match = re.match(r'class\s+(\w+)', code_snippet)
            if match:
                return match.group(1)
        
        # Handle variable assignments
        if "=" in code_snippet:
            # Get the left side of assignment
            left_side = code_snippet.split("=")[0].strip()
            # Remove type hints if present
            if ":" in left_side:
                left_side = left_side.split(":")[0].strip()
            return left_side
        
        # Handle import statements
        if code_snippet.startswith("import ") or code_snippet.startswith("from "):
            return code_snippet
        
        # Default: return the first word
        words = code_snippet.split()
        return words[0] if words else code_snippet
    
    def _execute_serena_command(self, file_path: str, command: Dict[str, Any]) -> bool:
        """Execute a single Serena MCP command via JSON-RPC"""
        try:
            action = command.get("action")
            
            # Try to use real MCP server first
            if self._can_use_real_serena():
                return self._execute_mcp_json_rpc(file_path, command)
            else:
                # Improved fallback to semantic replacement
                if action == "replace_symbol":
                    symbol = command.get("symbol")
                    old_code = command.get("old_code", symbol)  # Use old_code if available
                    new_code = command.get("new_code")
                    
                    if symbol and new_code:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read()
                        
                        # Try multiple replacement strategies
                        success = False
                        
                        # Strategy 1: Exact old_code match (best for complex replacements)
                        if old_code and old_code in content:
                            content = content.replace(old_code, new_code)
                            success = True
                            logger.info(f"✅ Replaced using exact old_code match: {old_code[:50]}...")
                        
                        # Strategy 2: Symbol-based replacement with regex
                        elif not success:
                            success = self._replace_symbol_with_regex(content, symbol, new_code, file_path)
                        
                        # Strategy 3: Simple symbol replacement (fallback)
                        if not success and symbol in content:
                            content = content.replace(symbol, new_code)
                            with open(file_path, "w", encoding="utf-8") as f:
                                f.write(content)
                            success = True
                            logger.info(f"✅ Replaced using simple symbol match: {symbol}")
                        
                        if success and old_code not in content:
                            # Only write if we haven't written yet
                            with open(file_path, "w", encoding="utf-8") as f:
                                f.write(content)
                        
                        return success
                        
                elif action == "insert_after_symbol":
                    symbol = command.get("symbol")
                    code = command.get("code")
                    if symbol and code:
                        return self._insert_after_symbol_fallback(file_path, symbol, code)
                        
                return False
        except Exception as e:
            logger.error(f"Failed to execute Serena command: {e}")
            return False

    def _replace_symbol_with_regex(self, content: str, symbol: str, new_code: str, file_path: str) -> bool:
        """Advanced regex-based symbol replacement"""
        try:
            # Pattern for function definitions
            func_pattern = rf'def\s+{re.escape(symbol)}\s*\([^)]*\):[^{{}}]*?(?=\n\S|\nclass|\ndef|\Z)'
            if re.search(func_pattern, content, re.MULTILINE | re.DOTALL):
                content = re.sub(func_pattern, new_code, content, flags=re.MULTILINE | re.DOTALL)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                logger.info(f"✅ Replaced function using regex: {symbol}")
                return True
            
            # Pattern for class definitions
            class_pattern = rf'class\s+{re.escape(symbol)}\s*(?:\([^)]*\))?:[^{{}}]*?(?=\nclass|\ndef|\Z)'
            if re.search(class_pattern, content, re.MULTILINE | re.DOTALL):
                content = re.sub(class_pattern, new_code, content, flags=re.MULTILINE | re.DOTALL)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                logger.info(f"✅ Replaced class using regex: {symbol}")
                return True
            
            # Pattern for variable assignments
            var_pattern = rf'^{re.escape(symbol)}\s*=.*?(?=\n\S|\Z)'
            if re.search(var_pattern, content, re.MULTILINE | re.DOTALL):
                content = re.sub(var_pattern, new_code, content, flags=re.MULTILINE | re.DOTALL)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                logger.info(f"✅ Replaced variable using regex: {symbol}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Regex replacement failed for {symbol}: {e}")
            return False

    def _insert_after_symbol_fallback(self, file_path: str, symbol: str, code: str) -> bool:
        """Fallback method to insert code after a symbol"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Find the symbol and insert after it
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if symbol in line:
                    # Insert the new code after this line
                    lines.insert(i + 1, code)
                    break
            else:
                # Symbol not found, append at the end
                lines.append(code)
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write('\n'.join(lines))
            
            logger.info(f"✅ Inserted code after symbol: {symbol}")
            return True
            
        except Exception as e:
            logger.error(f"Insert after symbol failed: {e}")
            return False
    
    def _execute_mcp_json_rpc(self, commands: List[Dict[str, Any]], file_path: str, original_code: str) -> SerenaResponse:
        """Execute MCP commands via JSON-RPC (real implementation)"""
        try:
            # Initialize stdio client if needed
            if not self._init_stdio_client():
                logger.error("❌ Failed to initialize MCP client for JSON-RPC execution")
                return SerenaResponse(success=False, content=original_code, suggestions=[], confidence=0.0, error="MCP client initialization failed")
            
            logger.info(f"🔄 Serena MCP: Starting JSON-RPC execution with {len(commands)} commands")
            current_content = original_code
            successful_commands = 0
            
            for i, cmd in enumerate(commands, 1):
                action = cmd.get("action")
                logger.info(f"   📋 Command {i}/{len(commands)}: {action}")
                
                if action == "find_symbol":
                    symbol = cmd.get("symbol")
                    logger.info(f"      🔍 Finding symbol: {symbol}")
                    response = self._send_stdio_request("find_symbol", {
                        "symbol": symbol, 
                        "file_path": file_path,
                        "file_content": current_content
                    })
                    if response and response.get("success"):
                        logger.info(f"      ✅ Symbol found successfully")
                        successful_commands += 1
                    else:
                        logger.warning(f"      ⚠️ Find symbol failed: {response.get('error', 'Unknown error') if response else 'No response'}")
                        
                elif action == "replace_symbol":
                    symbol = cmd.get("symbol")
                    new_code = cmd.get("new_code")
                    logger.info(f"      🔄 Replacing symbol: {symbol}")
                    logger.info(f"      📝 New code preview: {new_code[:100]}{'...' if len(new_code) > 100 else ''}")
                    
                    response = self._send_stdio_request("replace_symbol", {
                        "symbol": symbol, 
                        "new_code": new_code, 
                        "file_path": file_path,
                        "file_content": current_content
                    })
                    
                    if response and response.get("success"):
                        logger.info(f"      ✅ Symbol replaced successfully")
                        if "content" in response:
                            current_content = response["content"]
                        successful_commands += 1
                    else:
                        logger.warning(f"      ⚠️ Replace symbol failed: {response.get('error', 'Unknown error') if response else 'No response'}")
                        # Fallback to simple replacement
                        if symbol in current_content:
                            current_content = current_content.replace(symbol, new_code)
                            logger.info(f"      🔄 Used fallback replacement")
                            successful_commands += 1
                        
                elif action == "insert_after_symbol":
                    symbol = cmd.get("symbol")
                    new_code = cmd.get("code")  # Note: using 'code' key for insert_after_symbol
                    logger.info(f"      ➕ Inserting after symbol: {symbol}")
                    
                    response = self._send_stdio_request("insert_after_symbol", {
                        "symbol": symbol, 
                        "new_code": new_code, 
                        "file_path": file_path,
                        "file_content": current_content
                    })
                    
                    if response and response.get("success"):
                        logger.info(f"      ✅ Code inserted successfully")
                        if "content" in response:
                            current_content = response["content"]
                        successful_commands += 1
                    else:
                        logger.warning(f"      ⚠️ Insert failed: {response.get('error', 'Unknown error') if response else 'No response'}")
            
            success_rate = successful_commands / len(commands) if commands else 0
            logger.info(f"🎯 Serena MCP execution completed: {successful_commands}/{len(commands)} commands successful ({success_rate:.1%})")
            
            return SerenaResponse(
                success=successful_commands > 0,
                content=current_content,  # Return the accumulated content, not error messages
                suggestions=[],
                confidence=success_rate,
                error=None if successful_commands > 0 else "No commands executed successfully"
            )
            
        except Exception as e:
            logger.error(f"❌ Serena MCP JSON-RPC execution failed: {e}")
            return SerenaResponse(success=False, content=original_code, suggestions=[], confidence=0.0, error=str(e))
    
    def _send_stdio_request(self, method: str, params: dict) -> dict:
        """Send JSON-RPC request to Serena MCP server via stdio using MCP protocol"""
        try:
            if not self.stdio_process or self.stdio_process.poll() is not None:
                logger.error("Stdio process is not running")
                return {"success": False, "error": "Stdio process not available"}
            
            import json
            import uuid
            
            # Get file content from params or read from file_path
            file_path = params.get("file_path", "")
            file_content = params.get("file_content", "")
            
            # If no file_content provided, try to read from file_path
            if not file_content and file_path and os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        file_content = f.read()
                except Exception as e:
                    logger.warning(f"Could not read file {file_path}: {e}")
                    file_content = ""
            
            # Convert to relative path for Serena
            relative_path = os.path.relpath(file_path, self.project_path) if file_path else "temp.py"
            
            # Ensure the file exists for Serena to process
            if file_path and not os.path.exists(file_path):
                # Create a temporary file with the content
                try:
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(file_content)
                    logger.info(f"Created temporary file: {file_path}")
                except Exception as e:
                    logger.warning(f"Could not create temporary file {file_path}: {e}")
            
            # Use tools/call method with replace_regex tool for all operations
            tool_params = {
                "relative_path": relative_path
            }
            
            if method in ["find_symbol", "replace_symbol"]:
                symbol = params.get("symbol", "")
                if method == "find_symbol":
                    # For find_symbol, just use regex to match the symbol
                    tool_params["regex"] = re.escape(symbol)
                    tool_params["repl"] = symbol  # No replacement, just find
                else:  # replace_symbol
                    new_code = params.get("new_code", "")
                    # For replace_symbol, we need to match the entire line containing the symbol
                    # and replace it with the new code
                    escaped_symbol = re.escape(symbol)
                    # Match the line containing the symbol (including assignment) with multiline flag
                    tool_params["regex"] = f"^.*{escaped_symbol}\\s*=.*$"
                    tool_params["repl"] = new_code
            elif method == "insert_after_symbol":
                symbol = params.get("symbol", "")
                new_code = params.get("new_code", "")
                # Insert after symbol by matching symbol and replacing with symbol + new_code
                tool_params["regex"] = re.escape(symbol)
                tool_params["repl"] = symbol + "\n" + new_code
            else:
                # Default parameters for other methods
                tool_params.update(params)
            
            # Create MCP tools/call request
            request = {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tools/call",
                "params": {
                    "name": "replace_regex",
                    "arguments": tool_params
                }
            }
            
            # Send request
            request_json = json.dumps(request) + "\n"
            self.stdio_process.stdin.write(request_json)
            self.stdio_process.stdin.flush()
            
            # Read response with timeout
            import select
            import time
            
            timeout = 10.0  # Increased timeout to 10 seconds
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                if self.stdio_process.stdout in select.select([self.stdio_process.stdout], [], [], 0.1)[0]:
                    response_line = self.stdio_process.stdout.readline()
                    if response_line:
                        try:
                            response = json.loads(response_line.strip())
                            if response.get("id") == request["id"]:
                                if "error" in response:
                                    logger.error(f"MCP Error: {response['error']}")
                                    return {"success": False, "error": response["error"]}
                                else:
                                    result = response.get("result", {})
                                    # MCP tools/call returns content in result.content
                                    if "content" in result:
                                        content = result["content"]
                                        if isinstance(content, list) and len(content) > 0:
                                            # Extract text content from MCP response
                                            text_content = content[0].get("text", "")
                                            # Check if it's an error message
                                            if result.get("isError") or text_content.startswith("Error:"):
                                                return {"success": False, "error": text_content}
                                            else:
                                                # For replace_regex, "OK" means success
                                                if text_content == "OK":
                                                    # For replace_regex, we need to apply the replacement to current content
                                                    # since MCP server doesn't modify the actual file
                                                    if method in ["find_symbol", "replace_symbol"]:
                                                        # Apply the regex replacement to the current content
                                                        regex = tool_params.get("regex", "")
                                                        repl = tool_params.get("repl", "")
                                                        if regex and file_content:
                                                            try:
                                                                modified_content = re.sub(regex, repl, file_content, flags=re.MULTILINE)
                                                                return {"success": True, "content": modified_content}
                                                            except Exception as e:
                                                                logger.warning(f"Failed to apply regex replacement: {e}")
                                                                return {"success": True, "content": file_content}
                                                    return {"success": True, "content": file_content}
                                                return {"success": True, "content": text_content}
                                        elif isinstance(content, str):
                                            return {"success": True, "content": content}
                                    elif isinstance(result, str):
                                        return {"success": True, "content": result}
                                    result["success"] = True
                                    return result
                        except json.JSONDecodeError as e:
                            logger.warning(f"Failed to parse JSON response: {e}")
                            continue
            
            return {"success": False, "error": "Request timeout"}
            
        except Exception as e:
            logger.error(f"Failed to send stdio request: {e}")
            return {"success": False, "error": str(e)}

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
                    # Decode escape sequences in both old and new text
                    old_text = self._decode_escape_sequences(self._unquote(old_text))
                    new_text = self._decode_escape_sequences(self._unquote(new_text))
                    pairs.append((old_text, new_text))
                    break
        return pairs

    @staticmethod
    def _unquote(s: str) -> str:
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            return s[1:-1]
        return s
    
    @staticmethod
    def _decode_escape_sequences(text: str) -> str:
        """Decode escape sequences like \\n to actual newlines"""
        if not text:
            return text
        
        # Replace common escape sequences
        replacements = {
            '\\n': '\n',
            '\\t': '\t',
            '\\r': '\r',
            '\\"': '"',
            "\\'": "'",
            '\\\\': '\\'
        }
        
        result = text
        for escaped, actual in replacements.items():
            result = result.replace(escaped, actual)
        
        return result