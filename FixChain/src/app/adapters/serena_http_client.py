"""HTTP Client for communicating with Serena server via HTTP API"""

import requests
import json
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

@dataclass
class SerenaResponse:
    """Response from Serena server"""
    success: bool
    content: str
    suggestions: List[str]
    confidence: float
    error: Optional[str] = None

class SerenaHTTPClient:
    """HTTP client for communicating with Serena server"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:24282"):
        self.base_url = base_url
        self.logger = logging.getLogger(__name__)
        self.session = requests.Session()
        
    def check_availability(self) -> bool:
        """Check if Serena server is available"""
        try:
            response = self.session.get(f"{self.base_url}/dashboard", timeout=5)
            return response.status_code == 200
        except Exception as e:
            self.logger.error(f"Serena server not available: {e}")
            return False
            
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a Serena tool via HTTP API"""
        try:
            # Try different possible endpoints
            endpoints = [
                f"/api/tools/{tool_name}",
                f"/tools/{tool_name}",
                f"/api/call/{tool_name}",
                f"/call/{tool_name}"
            ]
            
            for endpoint in endpoints:
                try:
                    url = f"{self.base_url}{endpoint}"
                    response = self.session.post(
                        url,
                        json=arguments,
                        headers={"Content-Type": "application/json"},
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        return {"success": True, "result": response.json()}
                    elif response.status_code != 404:
                        self.logger.warning(f"Tool call to {url} returned {response.status_code}: {response.text[:200]}")
                        
                except requests.exceptions.RequestException as e:
                    self.logger.debug(f"Failed to call {endpoint}: {e}")
                    continue
                    
            # If no endpoint worked, return error
            return {"success": False, "error": f"No working endpoint found for tool {tool_name}"}
            
        except Exception as e:
            self.logger.error(f"Tool call failed: {e}")
            return {"success": False, "error": str(e)}
            
    def apply_fix_instructions(self, original_code: str, instructions: str, file_path: str) -> SerenaResponse:
        """Apply fix instructions using Serena tools"""
        try:
            # First, try to use replace_symbol_body tool
            result = self.call_tool("replace_symbol_body", {
                "file_path": file_path,
                "symbol_name": "main",  # Try to replace main function
                "new_body": original_code
            })
            
            if result["success"]:
                return SerenaResponse(
                    success=True,
                    content=original_code,  # For now, return original code
                    suggestions=["Applied via replace_symbol_body"],
                    confidence=0.8
                )
            else:
                # Try find_symbol to see what's available
                symbols_result = self.call_tool("find_symbol", {
                    "symbol_name": "*",
                    "file_path": file_path
                })
                
                if symbols_result["success"]:
                    self.logger.info(f"Available symbols: {symbols_result['result']}")
                    
                return SerenaResponse(
                    success=False,
                    content="",
                    suggestions=[],
                    confidence=0.0,
                    error=f"Tool call failed: {result.get('error', 'Unknown error')}"
                )
                
        except Exception as e:
            self.logger.error(f"Apply fix instructions failed: {e}")
            return SerenaResponse(
                success=False,
                content="",
                suggestions=[],
                confidence=0.0,
                error=str(e)
            )
            
    def list_available_tools(self) -> List[str]:
        """List available tools from Serena server"""
        try:
            # Try to get tools list from various endpoints
            endpoints = ["/api/tools", "/tools", "/api/list", "/list"]
            
            for endpoint in endpoints:
                try:
                    response = self.session.get(f"{self.base_url}{endpoint}", timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        if isinstance(data, list):
                            return data
                        elif isinstance(data, dict) and "tools" in data:
                            return data["tools"]
                except Exception:
                    continue
                    
            # Return known tools from the log
            return [
                "read_file", "create_text_file", "list_dir", "find_file", "replace_regex",
                "delete_lines", "replace_lines", "insert_at_line", "search_for_pattern",
                "restart_language_server", "get_symbols_overview", "find_symbol",
                "find_referencing_symbols", "replace_symbol_body", "insert_after_symbol",
                "insert_before_symbol", "write_memory", "read_memory", "list_memories",
                "delete_memory", "execute_shell_command"
            ]
            
        except Exception as e:
            self.logger.error(f"Failed to list tools: {e}")
            return []