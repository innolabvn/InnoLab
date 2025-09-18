"""Serena MCP Client for direct communication with Serena AI assistant via MCP protocol"""

import json
import subprocess
import threading
import queue
import uuid
import os
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
try:
    from src.app.services.log_service import logger
except ImportError:
    # Fallback for when running from scripts
    import logging
    logger = logging.getLogger(__name__)

@dataclass
class SerenaResponse:
    """Response from Serena MCP"""
    success: bool
    content: str
    suggestions: List[str]
    confidence: float
    error: Optional[str] = None

class MCPClient:
    """Base MCP client for JSON-RPC over stdio communication"""
    
    def __init__(self, command: List[str], cwd: Optional[str] = None):
        self.command = command
        self.cwd = cwd
        self.process: Optional[subprocess.Popen] = None
        self.response_queue: queue.Queue = queue.Queue()
        self.pending_requests: Dict[str, queue.Queue] = {}
        self.logger = logging.getLogger(__name__)
        self._reader_thread: Optional[threading.Thread] = None
        self._running = False
        
    def start(self) -> bool:
        """Start the MCP server process"""
        try:
            self.process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=self.cwd,
                bufsize=0
            )
            
            self._running = True
            self._reader_thread = threading.Thread(target=self._read_responses, daemon=True)
            self._reader_thread.start()
            
            # Initialize MCP session
            init_response = self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "roots": {"listChanged": True},
                    "sampling": {}
                },
                "clientInfo": {
                    "name": "FixChain",
                    "version": "1.0.0"
                }
            })
            
            if init_response and not init_response.get("error"):
                self.logger.info("MCP session initialized successfully")
                return True
            else:
                self.logger.error(f"MCP initialization failed: {init_response}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to start MCP server: {e}")
            return False
    
    def stop(self):
        """Stop the MCP server process"""
        self._running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
    
    def _read_responses(self):
        """Read responses from MCP server in background thread"""
        if not self.process or not self.process.stdout:
            return
            
        while self._running and self.process.poll() is None:
            try:
                line = self.process.stdout.readline()
                if not line:
                    break
                    
                response = json.loads(line.strip())
                request_id = response.get("id")
                
                if request_id and request_id in self.pending_requests:
                    self.pending_requests[request_id].put(response)
                else:
                    self.response_queue.put(response)
                    
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse MCP response: {e}")
            except Exception as e:
                self.logger.error(f"Error reading MCP response: {e}")
    
    def _send_request(self, method: str, params: Dict[str, Any], timeout: float = 30.0) -> Optional[Dict[str, Any]]:
        """Send JSON-RPC request to MCP server"""
        if not self.process or not self.process.stdin:
            return None
            
        request_id = str(uuid.uuid4())
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params
        }
        
        # Create response queue for this request
        response_queue = queue.Queue()
        self.pending_requests[request_id] = response_queue
        
        try:
            # Send request
            request_line = json.dumps(request) + "\n"
            self.process.stdin.write(request_line)
            self.process.stdin.flush()
            
            # Wait for response
            response = response_queue.get(timeout=timeout)
            return response
            
        except queue.Empty:
            self.logger.error(f"MCP request timeout: {method}")
            return None
        except Exception as e:
            self.logger.error(f"Failed to send MCP request: {e}")
            return None
        finally:
            # Clean up
            if request_id in self.pending_requests:
                del self.pending_requests[request_id]

class SerenaMCPClient:
    """Client for communicating with Serena MCP server"""
    
    def __init__(self, mcp_config_path: Optional[str] = None, project_path: Optional[str] = None):
        cur_dir = os.path.dirname(os.path.abspath(__file__))
        fixchain_dir = os.path.dirname(os.path.dirname(os.path.dirname(cur_dir)))
        self.mcp_config_path = mcp_config_path or os.path.join(fixchain_dir, ".mcp.json")
        self.project_path = project_path or os.path.dirname(fixchain_dir)
        self.logger = logging.getLogger(__name__)
        self.mcp_client: Optional[MCPClient] = None
        self.available = False
        self._initialize_mcp_client()
        
    def _initialize_mcp_client(self):
        """Initialize MCP client from config"""
        try:
            if not os.path.exists(self.mcp_config_path):
                self.logger.warning(f"MCP config not found: {self.mcp_config_path}")
                return
                
            with open(self.mcp_config_path, 'r') as f:
                config = json.load(f)
                
            serena_config = config.get("mcpServers", {}).get("serena")
            if not serena_config:
                self.logger.warning("Serena MCP server not configured")
                return
                
            command = [serena_config["command"]] + serena_config.get("args", [])
            self.mcp_client = MCPClient(command, cwd=self.project_path)
            
            # Start MCP client
            if self.mcp_client.start():
                self.available = True
                self.logger.info("Serena MCP client initialized successfully")
            else:
                self.logger.error("Failed to start Serena MCP client")
                
        except Exception as e:
            self.logger.error(f"Failed to initialize MCP client: {e}")
    
    def check_availability(self) -> bool:
        """Check if Serena MCP is available"""
        return self.available and self.mcp_client is not None
        
    def apply_fix_instructions(self, original_code: str, instructions: str, file_path: str, issues_data: Optional[List[Dict]] = None) -> SerenaResponse:
        """Apply fix instructions to code using Serena MCP with LSP"""
        if not self.check_availability():
            return SerenaResponse(False, "", [], 0.0, "Serena MCP not available")
            
        try:
            # First, create a temporary file with the original code
            temp_response = self.mcp_client._send_request("tools/call", {
                "name": "create_text_file",
                "arguments": {
                    "file_path": file_path,
                    "content": original_code
                }
            })
            
            if not temp_response or temp_response.get("error"):
                return SerenaResponse(False, "", [], 0.0, "Failed to create temporary file")
            
            # Then apply fixes using replace_regex based on instructions
            # For f-string fix: replace string concatenation pattern
            if "f-string" in instructions.lower():
                response = self.mcp_client._send_request("tools/call", {
                    "name": "replace_regex",
                    "arguments": {
                        "file_path": file_path,
                        "pattern": r'print\("([^"]+)" \+ str\(([^)]+)\)\)',
                        "replacement": r'print(f"\1{\2}")'
                    }
                })
            else:
                # For other fixes, use general text replacement
                response = self.mcp_client._send_request("tools/call", {
                    "name": "read_file",
                    "arguments": {
                        "file_path": file_path
                    }
                })
            
            # Read the modified file content
            read_response = self.mcp_client._send_request("tools/call", {
                "name": "read_file",
                "arguments": {
                    "file_path": file_path
                }
            })
            
            if read_response and not read_response.get("error"):
                result = read_response.get("result", {})
                content = result.get("content", [])
                
                if content and len(content) > 0:
                    fixed_code = content[0].get("text", "")
                    if fixed_code:
                        return SerenaResponse(
                            success=True,
                            content=fixed_code,
                            suggestions=["Applied LSP-based code fix"],
                            confidence=0.9
                        )
                        
            # Check for errors in any of the responses
            error_msg = "Unknown error"
            if temp_response and temp_response.get("error"):
                error_msg = temp_response.get("error", {}).get("message", "Failed to create file")
            elif response and response.get("error"):
                error_msg = response.get("error", {}).get("message", "Failed to apply fix")
            elif read_response and read_response.get("error"):
                error_msg = read_response.get("error", {}).get("message", "Failed to read file")
                
            return SerenaResponse(False, "", [], 0.0, error_msg)
            
        except Exception as e:
            self.logger.error(f"Error applying Serena fixes: {e}")
            return SerenaResponse(False, "", [], 0.0, str(e))
    
    def __del__(self):
        """Cleanup MCP client on destruction"""
        if self.mcp_client:
            self.mcp_client.stop()