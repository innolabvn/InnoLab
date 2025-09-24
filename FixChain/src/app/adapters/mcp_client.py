#!/usr/bin/env python3
"""
Real MCP Client for communicating with Serena MCP Server
Implements JSON-RPC protocol to send actual requests to MCP server
"""

import json
import socket
import subprocess
import logging
import uuid
import threading
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class MCPResponse:
    """Response from MCP server"""
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    id: Optional[str] = None

class MCPClient:
    """Client for communicating with MCP servers"""
    
    def __init__(self, host: str = "localhost", port: int = 9000):
        self.host = host
        self.port = port
        self.session_id = None
        self.message_endpoint = None
        self.request_id = 0
        self.sse_url = f"http://{host}:{port}/sse"
        self.pending_responses = {}  # Store pending responses by request ID
        self.sse_listener_thread = None
        self.sse_running = False
        self.initialized = False
        # Auto-initialize on creation
        self._initialize()
        
    def _setup_sse_connection(self) -> bool:
        """Setup SSE connection and get session_id"""
        try:
            import requests
            
            logger.info(f"🔗 Setting up SSE connection to {self.sse_url}")
            
            # Get session_id from SSE endpoint
            response = requests.get(self.sse_url, stream=True, timeout=10)
            
            event_type = None
            for line in response.iter_lines(decode_unicode=True):
                if line.startswith('event: '):
                    event_type = line[7:]  # Remove 'event: ' prefix
                    logger.info(f"📍 Got event type: {event_type}")
                elif line.startswith('data: ') and event_type == 'endpoint':
                    endpoint_path = line[6:]  # Remove 'data: ' prefix
                    logger.info(f"📍 Got endpoint path: {endpoint_path}")
                    
                    # Build full message endpoint URL
                    self.message_endpoint = f"http://{self.host}:{self.port}{endpoint_path}"
                    
                    # Extract session_id from endpoint path
                    if 'session_id=' in endpoint_path:
                        session_id_part = endpoint_path.split('session_id=')[1]
                        self.session_id = session_id_part.split('&')[0]  # Handle potential additional params
                        logger.info(f"📍 Got session_id: {self.session_id}")
                    
                    logger.info(f"📍 Got message endpoint: {self.message_endpoint}")
                    
                    # Start SSE listener thread
                    self._start_sse_listener()
                    return True
                elif line == '':
                    # Empty line indicates end of event
                    event_type = None
                    continue
                    
            logger.error("Failed to get message endpoint from SSE")
            return False
            
        except Exception as e:
            logger.error(f"SSE setup failed: {e}")
            return False
    
    def _start_sse_listener(self):
        """Start SSE listener thread to receive async responses"""
        if self.sse_listener_thread and self.sse_listener_thread.is_alive():
            return
            
        self.sse_running = True
        self.sse_listener_thread = threading.Thread(target=self._sse_listener, daemon=True)
        self.sse_listener_thread.start()
        logger.info("🎧 Started SSE listener thread")
    
    def _sse_listener(self):
        """Listen for SSE responses from server"""
        try:
            import requests
            
            # Use session-specific SSE URL if we have a session_id
            sse_url = self.sse_url
            if self.session_id:
                sse_url = f"{self.sse_url}?session_id={self.session_id}"
            
            logger.info(f"🎧 SSE Listener: Connecting to {sse_url}")
            
            while self.sse_running:
                try:
                    response = requests.get(sse_url, stream=True, timeout=30)
                    logger.info(f"🎧 SSE Connection established, status: {response.status_code}")
                    
                    event_type = None
                    for line in response.iter_lines(decode_unicode=True):
                        if not self.sse_running:
                            break
                            
                        logger.debug(f"🎧 SSE Raw line: '{line}'")
                            
                        if line.startswith('event: '):
                            event_type = line[7:]  # Remove 'event: ' prefix
                            logger.debug(f"🎧 SSE Event type: {event_type}")
                        elif line.startswith('data: '):
                            data_str = line[6:]  # Remove 'data: ' prefix
                            logger.debug(f"🎧 SSE Data (event={event_type}): {data_str}")
                            
                            # Skip endpoint messages
                            if event_type == 'endpoint' or data_str.startswith('/messages/'):
                                logger.debug(f"🎧 Skipping endpoint message")
                                continue
                                
                            # Skip ping messages
                            if data_str == 'ping' or line.startswith(': ping'):
                                logger.debug(f"🎧 Skipping ping message")
                                continue
                                
                            logger.info(f"🎧 SSE Raw data (event={event_type}): {data_str}")
                            
                            # Handle message events (actual JSON-RPC responses)
                            if event_type == 'message':
                                try:
                                    # Parse JSON response
                                    response_data = json.loads(data_str)
                                    
                                    if 'id' in response_data:
                                        request_id = response_data['id']
                                        logger.info(f"🎧 SSE Response for ID {request_id}: {response_data}")
                                        logger.info(f"🎧 Current pending responses: {list(self.pending_responses.keys())}")
                                        
                                        # Store response for pending request
                                        if request_id in self.pending_responses:
                                            logger.info(f"🎧 Storing response for request ID {request_id}")
                                            self.pending_responses[request_id] = response_data
                                        else:
                                            logger.warning(f"🎧 No pending request found for ID {request_id}")
                                            
                                except json.JSONDecodeError:
                                    # Not a JSON response, might be other SSE data
                                    logger.info(f"🎧 SSE Non-JSON data: {data_str}")
                        elif line == '':
                            # Empty line indicates end of event
                            event_type = None
                            continue
                        elif line.startswith(': '):
                            # SSE comment line (like ping)
                            logger.debug(f"🎧 SSE Comment: {line}")
                            continue
                                
                except requests.exceptions.Timeout:
                    logger.debug("🎧 SSE timeout, reconnecting...")
                    continue
                except Exception as e:
                    logger.error(f"🎧 SSE listener error: {e}")
                    time.sleep(1)
                    
        except Exception as e:
            logger.error(f"🎧 SSE listener failed: {e}")
        finally:
            logger.info("🎧 SSE listener stopped")
            
    def _get_next_id(self) -> str:
        """Get next request ID"""
        self.request_id += 1
        return str(self.request_id)
    
    def _create_jsonrpc_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create JSON-RPC 2.0 request"""
        return {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self._get_next_id()
        }
    
    def _send_request_via_sse(self, request: Dict[str, Any]) -> MCPResponse:
        """Send request to MCP server via SSE transport"""
        try:
            import requests
            
            # Setup SSE connection if not already done
            if not self.message_endpoint:
                if not self._setup_sse_connection():
                    return MCPResponse(
                        success=False,
                        error="Failed to setup SSE connection",
                        id=request.get("id")
                    )
            
            # Use the request as-is for MCP protocol
            mcp_request = request
            
            request_id = mcp_request["id"]
            
            # Register pending response
            self.pending_responses[request_id] = None
            
            logger.info(f"🔄 MCP SSE: Sending request to {self.message_endpoint}")
            logger.debug(f"🔄 Request payload: {json.dumps(mcp_request, indent=2)}")
            
            # Send POST request with session_id as query parameter
            response = requests.post(
                self.message_endpoint,
                json=mcp_request,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            logger.info(f"🔄 MCP SSE: Got HTTP {response.status_code}")
            
            if response.status_code == 202:
                # Wait for async response via SSE
                logger.info(f"🔄 Waiting for async response for request ID {request_id}...")
                
                # Wait up to 10 seconds for response (reduced from 30)
                for _ in range(100):  # 10 seconds, check every 0.1s
                    if request_id in self.pending_responses and self.pending_responses[request_id] is not None:
                        sse_response = self.pending_responses[request_id]
                        
                        # Clean up
                        del self.pending_responses[request_id]
                        
                        # Parse SSE response
                        if 'error' in sse_response:
                            return MCPResponse(
                                success=False,
                                error=sse_response['error'].get('message', str(sse_response['error'])) if isinstance(sse_response['error'], dict) else str(sse_response['error']),
                                id=request_id
                            )
                        else:
                            return MCPResponse(
                                success=True,
                                result=sse_response.get('result', {}),
                                id=request_id
                            )
                    
                    time.sleep(0.1)
                
                # Timeout waiting for response
                if request_id in self.pending_responses:
                    del self.pending_responses[request_id]
                    
                return MCPResponse(
                    success=False,
                    error="Timeout waiting for async response",
                    id=request_id
                )
            else:
                # Handle non-202 responses
                try:
                    response_data = response.json()
                    if 'error' in response_data:
                        return MCPResponse(
                            success=False,
                            error=response_data['error'],
                            id=request_id
                        )
                    else:
                        return MCPResponse(
                            success=True,
                            result=response_data.get('result', {}),
                            id=request_id
                        )
                except:
                    return MCPResponse(
                        success=False,
                        error=f"HTTP {response.status_code}: {response.text}",
                        id=request_id
                    )
                    
        except Exception as e:
            logger.error(f"MCP SSE request failed: {e}")
            return MCPResponse(
                success=False,
                error=str(e),
                id=request.get("id")
            )

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> MCPResponse:
        """Call any MCP tool with given arguments"""
        if not self.initialized:
            init_response = self._initialize()
            if not init_response.success:
                return init_response
                
        request = self._create_jsonrpc_request(tool_name, arguments)
        return self._send_request_via_sse(request)
    
    def find_symbol(self, symbol: str, file_path: Optional[str] = None) -> MCPResponse:
        """Find symbol in codebase using MCP server"""
        params = {"symbol": symbol}
        if file_path:
            params["file_path"] = file_path
        return self.call_tool("find_symbol", params)
    
    def replace_symbol(self, symbol: str, new_code: str, file_path: Optional[str] = None) -> MCPResponse:
        """Replace symbol with new code using MCP server"""
        params = {
            "symbol": symbol,
            "new_body": new_code
        }
        if file_path:
            params["file_path"] = file_path
        return self.call_tool("replace_symbol_body", params)
    
    def replace_regex(self, pattern: str, replacement: str, file_path: str) -> MCPResponse:
        """Replace text using regex pattern"""
        params = {
            "pattern": pattern,
            "replacement": replacement,
            "file_path": file_path
        }
        return self.call_tool("replace_regex", params)
    
    def read_file(self, file_path: str) -> MCPResponse:
        """Read file content using MCP server"""
        params = {"file_path": file_path}
        return self.call_tool("read_file", params)
    
    def write_file(self, file_path: str, content: str) -> MCPResponse:
        """Write file content using MCP server"""
        params = {
            "file_path": file_path,
            "content": content
        }
        return self.call_tool("write_file", params)
    
    def get_symbols_overview(self, file_path: str) -> MCPResponse:
        """Get symbols overview for a file"""
        params = {"file_path": file_path}
        return self.call_tool("get_symbols_overview", params)
    
    def find_referencing_symbols(self, symbol: str, file_path: Optional[str] = None) -> MCPResponse:
        """Find symbols that reference the given symbol"""
        params = {"symbol": symbol}
        if file_path:
            params["file_path"] = file_path
        return self.call_tool("find_referencing_symbols", params)
    
    def insert_after_symbol(self, symbol: str, code: str, file_path: Optional[str] = None) -> MCPResponse:
        """Insert code after a symbol"""
        params = {
            "symbol": symbol,
            "code": code
        }
        if file_path:
            params["file_path"] = file_path
        return self.call_tool("insert_after_symbol", params)
    
    def search_pattern(self, pattern: str, file_path: Optional[str] = None) -> MCPResponse:
        """Search for pattern in files"""
        params = {"pattern": pattern}
        if file_path:
            params["file_path"] = file_path
        return self.call_tool("search_pattern", params)
    
    def _initialize(self) -> MCPResponse:
        """Initialize MCP connection"""
        try:
            logger.info("🚀 Initializing MCP client with SSE transport")
            
            # Setup SSE connection
            if not self._setup_sse_connection():
                return MCPResponse(
                    success=False,
                    error="Failed to setup SSE connection"
                )
            
            logger.info("✅ MCP client initialized successfully")
            self.initialized = True
            return MCPResponse(success=True, result={"status": "initialized"})
            
        except Exception as e:
            error_msg = f"MCP initialization error: {str(e)}"
            logger.error(error_msg)
            return MCPResponse(success=False, error=error_msg)
    
    def is_server_available(self) -> bool:
        """Check if MCP server is available"""
        try:
            # Ensure initialized first
            if not self.initialized:
                init_response = self._initialize()
                if not init_response.success:
                    return False
            
            # Try to read a simple file for testing
            response = self.read_file("README.md")
            return response.success or "not found" in (response.error or "")
        except Exception:
            return False
    
    def cleanup(self):
        """Clean up resources"""
        self.sse_running = False
        if self.sse_listener_thread and self.sse_listener_thread.is_alive():
            self.sse_listener_thread.join(timeout=1)
        logger.info("🧹 MCP Client cleaned up")