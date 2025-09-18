"""Real MCP Client for communicating with Serena MCP server"""

import asyncio
import json
import logging
import os
import subprocess
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

@dataclass
class MCPResponse:
    """Response from MCP server"""
    success: bool
    result: Any
    error: Optional[str] = None

class MCPClient:
    """Client for communicating with MCP servers via stdio transport"""
    
    def __init__(self, server_config: Dict[str, Any]):
        self.server_config = server_config
        self.process: Optional[subprocess.Popen] = None
        self.logger = logging.getLogger(__name__)
        self._request_id = 0
        
    async def start_server(self) -> bool:
        """Start the MCP server process"""
        try:
            command = self.server_config.get("command")
            args = self.server_config.get("args", [])
            env = dict(os.environ)
            env.update(self.server_config.get("env", {}))
            
            full_command = [command] + args
            
            self.process = subprocess.Popen(
                full_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env
            )
            
            # Log stderr for debugging
            import threading
            def log_stderr():
                if self.process and self.process.stderr:
                    for line in iter(self.process.stderr.readline, ''):
                        if line.strip():
                            self.logger.error(f"MCP Server stderr: {line.strip()}")
            
            stderr_thread = threading.Thread(target=log_stderr, daemon=True)
            stderr_thread.start()
            
            # Give the server a moment to start
            await asyncio.sleep(1)
            
            # Initialize MCP connection
            init_success = await self._initialize_connection()
            if not init_success:
                self.logger.error("Failed to initialize MCP connection")
                return False
            
            self.logger.info("MCP server initialized successfully")
            return True
                
        except Exception as e:
            self.logger.error(f"Failed to start MCP server: {e}")
            return False
    
    async def stop_server(self):
        """Stop the MCP server process"""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
    
    def _get_next_id(self) -> int:
        """Get next request ID"""
        self._request_id += 1
        return self._request_id
    
    async def _initialize_connection(self) -> bool:
        """Initialize MCP connection with the server"""
        self.logger.debug("Starting MCP initialization...")
        
        init_request = {
            "jsonrpc": "2.0",
            "id": self._get_next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "roots": {
                        "listChanged": True
                    },
                    "sampling": {}
                },
                "clientInfo": {
                    "name": "FixChain",
                    "version": "1.0.0"
                }
            }
        }
        
        response = await self._send_request(init_request)
        if response.success:
            self.logger.debug("MCP initialization successful")
            # Send initialized notification
            initialized_notification = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            }
            await self._send_notification(initialized_notification)
            return True
        else:
            self.logger.error(f"MCP initialization failed: {response.error}")
            return False
    
    async def _send_notification(self, notification: Dict[str, Any]) -> None:
        """Send notification to MCP server (no response expected)"""
        try:
            self.logger.debug(f"Sending MCP notification: {json.dumps(notification)}")
            
            if not self.process or not self.process.stdin:
                raise Exception("MCP server process not available")
            
            # Send the notification
            notification_str = json.dumps(notification) + "\n"
            self.process.stdin.write(notification_str)
            self.process.stdin.flush()
            
        except Exception as e:
            self.logger.error(f"Failed to send MCP notification: {e}")
    
    async def _send_request(self, request: Dict[str, Any]) -> MCPResponse:
        """Send request to MCP server and get response"""
        try:
            if not self.process or not self.process.stdin or not self.process.stdout:
                return MCPResponse(False, None, "MCP server not running")
            
            # Send request
            request_json = json.dumps(request) + "\n"
            self.logger.debug(f"Sending MCP request: {request_json.strip()}")
            self.process.stdin.write(request_json)
            self.process.stdin.flush()

            # Read response
            response_line = self.process.stdout.readline()
            if not response_line:
                return MCPResponse(False, None, "No response from server")

            self.logger.debug(f"Received MCP response: {response_line.strip()}")
            response_data = json.loads(response_line.strip())
            
            if "error" in response_data:
                return MCPResponse(False, None, response_data["error"].get("message", "Unknown error"))
            
            return MCPResponse(True, response_data.get("result"))
            
        except Exception as e:
            self.logger.error(f"Error sending MCP request: {e}")
            return MCPResponse(False, None, str(e))
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any] = None) -> MCPResponse:
        """Call a tool on the MCP server"""
        params = {"name": tool_name}
        if arguments:
            params["arguments"] = arguments
            
        request = {
            "jsonrpc": "2.0",
            "id": self._get_next_id(),
            "method": "tools/call",
            "params": params
        }
        
        return await self._send_request(request)
    
    async def list_tools(self) -> MCPResponse:
        """List available tools from MCP server"""
        request = {
            "jsonrpc": "2.0",
            "id": self._get_next_id(),
            "method": "tools/list"
        }
        
        return await self._send_request(request)
    
    async def get_resources(self) -> MCPResponse:
        """Get available resources from MCP server"""
        request = {
            "jsonrpc": "2.0",
            "id": self._get_next_id(),
            "method": "resources/list",
            "params": {}
        }
        
        return await self._send_request(request)