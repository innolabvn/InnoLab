# src\app\adapters\serena_client.py
"""
serena_client.py
Minimal MCP client for Serena to apply precise code edits.

Features:
- Spawn Serena MCP server via stdio (no ports).
- Activate project (LSP index) so symbol tools work.
- Apply fixes by: symbol, regex/pattern, or line range.
- Find referencing symbols (impact analysis).
- Execute shell commands (format/lint/test) if tool is exposed.
- Safe param mapping (auto-adapt to tool input schema).
- Clean async context mgmt + helpful errors.

Requirements:
    pip install mcp
    # and make sure `serena` is in PATH (pip/uv install).

Basic usage:
    import asyncio
    from serena_client import SerenaClient

    async def demo():
        async with SerenaClient(project_path="/app") as sc:
            await sc.activate_project()

            # 1) Replace function body by symbol
            await sc.apply_patch_by_symbol(
                name_path="mypkg.module:MyClass.method",
                relative_path="src/mypkg/module.py",
                new_body="def method(self, x):\n    return x * 2\n",
            )

            # 2) Regex replace
            await sc.apply_patch_by_regex(
                path="src/mypkg/utils.py",
                pattern=r"DEBUG\\s*=\\s*True",
                replacement="DEBUG = False",
            )

            # 3) Replace lines (120..130)
            await sc.replace_lines(
                path="src/mypkg/legacy.py",
                start_line=120, end_line=130,
                new_text="result = compute(value)\\nreturn result\\n",
            )

            # 4) Find references to a symbol
            refs = await sc.find_referencing_symbols(
                name_path="mypkg.module:MyClass.method",
                relative_path="src/mypkg/module.py",
                include_definitions=False,
                kinds=["reference"],        # depending on LS/tool schema
                max_results=100,
            )
            print(refs)

            # 5) Run formatter/tests (if tool is exposed by your Serena build)
            await sc.execute_shell_command("uv run pytest -q", timeout_s=600)

    asyncio.run(demo())
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class SerenaError(RuntimeError):
    pass


def _read_mcp_json(mcp_json_path: Path) -> Optional[List[str]]:
    """
    Read .mcp.json and return ['command', *args] for 'serena' server if present.
    """
    try:
        data = json.loads(mcp_json_path.read_text(encoding="utf-8"))
        servers = data.get("mcpServers") or data.get("servers") or {}
        serena = servers.get("serena")
        if not serena:
            return None
        cmd = serena.get("command")
        args = serena.get("args", [])
        if not cmd:
            return None
        if isinstance(args, list):
            return [cmd] + args
        return [cmd, str(args)]
    except FileNotFoundError:
        return None
    except Exception as e:
        raise SerenaError(f"Cannot parse {mcp_json_path}: {e}") from e


def _default_serena_cmd(project_path: str, enable_dashboard: bool = False) -> List[str]:
    """
    Fallback stdio server command if .mcp.json is not provided.
    """
    return [
        "serena", "start-mcp-server",
        "--project", project_path,
        "--log-level", "INFO"
    ]


class SerenaClient:
    """
    Minimal, safe wrapper around Serena MCP.

    - Spawns the server via stdio.
    - Initializes MCP session.
    - Discovers tool schemas â†’ maps wrapper params to tool-specific keys.
    """

    def __init__(
        self,
        project_path: str,
        serena_cmd: Optional[List[str]] = None,
        mcp_json_path: Optional[str] = None,
        enable_dashboard: bool = False,
        init_timeout_s: int = 60,
    ) -> None:
        """
        Args:
            project_path: Absolute path to repo root. Serena will index this.
            serena_cmd: Explicit command to start the server (['serena', 'start-mcp-server', ...]).
            mcp_json_path: If provided (e.g. '/app/.mcp.json'), read 'serena' server command from it.
            enable_dashboard: True only in dev; prod should keep False.
            init_timeout_s: Timeout for initial LSP indexing/handshake.
        """
        self.project_path = str(Path(project_path).resolve())
        self.init_timeout_s = init_timeout_s
        self._tools_index: Dict[str, Dict[str, Any]] = {}

        resolved_cmd: Optional[List[str]] = None
        if serena_cmd:
            resolved_cmd = serena_cmd
        elif mcp_json_path:
            resolved_cmd = _read_mcp_json(Path(mcp_json_path))
        if not resolved_cmd:
            resolved_cmd = _default_serena_cmd(self.project_path, enable_dashboard)

        if isinstance(resolved_cmd, (list, tuple)):
            _cmd, _args = resolved_cmd[0], list(resolved_cmd[1:])
        else:
            _cmd, _args = str(resolved_cmd), []

        self._server_params = StdioServerParameters(command=_cmd, args=_args)
        self._session: Optional[ClientSession] = None
        self._client_ctx = None

    async def __aenter__(self) -> "SerenaClient":
        self._client_ctx = stdio_client(self._server_params)
        self._read, self._write = await asyncio.wait_for(
            self._client_ctx.__aenter__(), timeout=self.init_timeout_s
        )
        self._session = ClientSession(self._read, self._write)
        await asyncio.wait_for(self._session.initialize(), timeout=self.init_timeout_s)
        await self._refresh_tools_index()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._session:
            try:
                await self._session.shutdown() # type: ignore
            except Exception:
                pass
        if self._client_ctx:
            await self._client_ctx.__aexit__(exc_type, exc, tb)

    async def _refresh_tools_index(self) -> None:
        assert self._session is not None
        tools = await self._session.list_tools()
        index: Dict[str, Dict[str, Any]] = {}
        for t in tools.tools:
            index[t.name] = {
                "inputSchema": getattr(t, "inputSchema", None),
                "description": getattr(t, "description", ""),
            }
        self._tools_index = index

    # ---------- Public high-level APIs ----------

    async def list_tools(self) -> List[str]:
        """Return list of exposed tool names (cached)."""
        if not self._tools_index:
            await self._refresh_tools_index()
        return sorted(self._tools_index.keys())

    async def activate_project(self, path: Optional[str] = None) -> Dict[str, Any]:
        """
        Ensure Serena activates/loads the project (good to call once on startup).
        """
        path = path or self.project_path
        return await self._call_tool_flex(
            "activate_project",
            {
                "path": path,
                "project_path": path,
                "root": path,
            },
            must_exist=False,
        )

    async def apply_patch_by_symbol(
        self,
        name_path: str,
        relative_path: str,
        new_body: str,
    ) -> Dict[str, Any]:
        """
        Replace the body of a function/method/class identified by its name path.
        Example name_path: "pkg.mod:Class.method" or "pkg.mod:function".
        """
        await self._call_tool_flex(
            "find_symbol",
            {
                "name_path": name_path,
                "relative_path": relative_path,
                "path": relative_path,
                "file": relative_path,
            },
            must_exist=False,
        )
        return await self._call_tool_flex(
            "replace_symbol_body",
            {
                "name_path": name_path,
                "relative_path": relative_path,
                "path": relative_path,
                "file": relative_path,
                "new_body": new_body,
                "body": new_body,
                "text": new_body,
            },
        )

    async def apply_patch_by_regex(
        self,
        path: str,
        pattern: str,
        replacement: str,
        count: Optional[int] = None,
        flags: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Regex-based replacement inside a file. Use anchors/context to be safe.
        """
        payload: Dict[str, Any] = {
            "path": path,
            "file": path,
            "file_path": path,
            "pattern": pattern,
            "regex": pattern,
            "replacement": replacement,
            "with": replacement,
        }
        if count is not None:
            payload.update({"count": count, "max_replacements": count})
        if flags:
            payload.update({"flags": flags})
        return await self._call_tool_flex("replace_regex", payload)

    async def replace_lines(
        self,
        path: str,
        start_line: int,
        end_line: int,
        new_text: str,
    ) -> Dict[str, Any]:
        """
        Replace a line range [start_line, end_line] (1-based, inclusive).
        """
        return await self._call_tool_flex(
            "replace_lines",
            {
                "path": path,
                "file": path,
                "file_path": path,
                "start": start_line,
                "start_line": start_line,
                "from_line": start_line,
                "end": end_line,
                "end_line": end_line,
                "to_line": end_line,
                "text": new_text,
                "new_text": new_text,
                "replacement": new_text,
            },
        )

    async def search_for_pattern(
        self, path: str, pattern: str, max_matches: Optional[int] = None
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "path": path,
            "file": path,
            "file_path": path,
            "pattern": pattern,
            "regex": pattern,
        }
        if max_matches is not None:
            payload.update({"max_matches": max_matches, "limit": max_matches})
        return await self._call_tool_flex("search_for_pattern", payload)

    async def read_file(self, path: str, max_bytes: Optional[int] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "path": path,
            "file": path,
            "file_path": path,
        }
        if max_bytes is not None:
            payload.update({"max_bytes": max_bytes, "limit": max_bytes})
        return await self._call_tool_flex("read_file", payload)

    async def insert_after_symbol(
        self, name_path: str, relative_path: str, text: str
    ) -> Dict[str, Any]:
        return await self._call_tool_flex(
            "insert_after_symbol",
            {
                "name_path": name_path,
                "relative_path": relative_path,
                "path": relative_path,
                "file": relative_path,
                "text": text,
                "new_text": text,
            },
        )

    async def insert_before_symbol(
        self, name_path: str, relative_path: str, text: str
    ) -> Dict[str, Any]:
        return await self._call_tool_flex(
            "insert_before_symbol",
            {
                "name_path": name_path,
                "relative_path": relative_path,
                "path": relative_path,
                "file": relative_path,
                "text": text,
                "new_text": text,
            },
        )

    async def find_referencing_symbols(
        self,
        name_path: str,
        relative_path: str,
        include_definitions: Optional[bool] = None,
        kinds: Optional[List[str]] = None,
        max_results: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Find locations that reference a given symbol. Helpful for impact analysis before/after edits.
        """
        payload: Dict[str, Any] = {
            "name_path": name_path,
            "relative_path": relative_path,
            "path": relative_path,
            "file": relative_path,
        }
        if include_definitions is not None:
            payload.update({
                "include_definitions": include_definitions,
                "include_defs": include_definitions,
                "with_definitions": include_definitions,
            })
        if kinds:
            payload.update({
                "kinds": kinds,
                "symbol_kinds": kinds,
                "symbolKinds": kinds,
                "types": kinds,
            })
        if max_results is not None:
            payload.update({
                "max_results": max_results,
                "limit": max_results,
            })
        return await self._call_tool_flex("find_referencing_symbols", payload)

    async def execute_shell_command(
        self,
        command: str,
        timeout_s: Optional[int] = None,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        shell: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Execute a shell command via Serena tool (if exposed).
        Typical uses: run formatter/linter/tests after patch.
        """
        payload: Dict[str, Any] = {
            "command": command,
            "cmd": command,
            "shell_command": command,
            "sh": command,
            "bash": command,
        }
        if cwd:
            payload.update({
                "cwd": cwd,
                "workdir": cwd,
                "working_directory": cwd,
                "dir": cwd,
            })
        if env:
            payload.update({
                "env": env,
                "environment": env,
            })
        if shell is not None:
            payload.update({"shell": shell})
        if timeout_s is not None:
            payload.update({
                "timeout": timeout_s,
                "timeout_s": timeout_s,
                "seconds": timeout_s,
            })

        # Default longer timeout for tool call (command itself may run long)
        call_timeout = max(timeout_s or 120, 120)
        return await self._call_tool_flex("execute_shell_command", payload, timeout_s=call_timeout)

    # ---------- Internal helpers ----------

    async def _call_tool_flex(
        self,
        tool: str,
        candidate_params: Dict[str, Any],
        *,
        must_exist: bool = True,
        timeout_s: int = 120,
    ) -> Dict[str, Any]:
        """
        Call a Serena tool, auto-mapping candidate_params to the tool's input schema.

        - If tool missing and must_exist=True â†’ raise SerenaError with available tools.
        - If schema unknown, we send params as-is (best effort).
        """
        assert self._session is not None

        if tool not in self._tools_index:
            await self._refresh_tools_index()
        if tool not in self._tools_index:
            msg = f"Tool '{tool}' not exposed by Serena."
            if must_exist:
                raise SerenaError(msg + f" Available: {', '.join(sorted(self._tools_index.keys()))}")
            else:
                return {"ok": False, "tool": tool, "skipped": True, "reason": "tool not available"}

        schema = self._tools_index[tool].get("inputSchema") or {}
        properties: Dict[str, Any] = schema.get("properties") or {}
        required: List[str] = schema.get("required") or []

        # Build param map respecting schema keys; allow synonyms
        params = self._map_params(properties, candidate_params)

        # Check required keys â€” if missing, attach debug info
        missing = [k for k in required if k not in params]
        if missing:
            raise SerenaError(
                f"Missing required params for tool '{tool}': {missing}. "
                f"Provided candidates: {list(candidate_params.keys())}. "
                f"Schema props: {list(properties.keys())}"
            )

        try:
            result = await asyncio.wait_for(
                self._session.call_tool(tool, params),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError as e:
            raise SerenaError(f"Timeout calling tool '{tool}'") from e

        payload = getattr(result, "content", None)
        if isinstance(payload, list) and payload:
            first = payload[0]
            if hasattr(first, "text") and first.text is not None:
                return {"ok": True, "tool": tool, "result": first.text}
            if hasattr(first, "json") and first.json is not None:
                return {"ok": True, "tool": tool, "result": first.json}
        return {"ok": True, "tool": tool, "raw": getattr(result, "__dict__", {})}

    @staticmethod
    def _map_params(
        schema_props: Dict[str, Any],
        candidates: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Map friendly keys to the exact keys expected by the tool schema.
        We keep only keys present in schema; if schema empty â†’ pass everything.
        """
        if not schema_props:
            return {k: v for k, v in candidates.items() if v is not None}

        schema_keys = set(schema_props.keys())
        out: Dict[str, Any] = {}

        synonyms: Dict[str, List[str]] = {
            # file-ish
            "path": ["path", "file", "file_path", "filepath", "relative_path"],
            "name_path": ["name_path", "symbol", "symbol_path", "qualified_name"],
            # search/replace
            "pattern": ["pattern", "regex", "regexp"],
            "replacement": ["replacement", "with", "new_text", "text"],
            "new_body": ["new_body", "body", "text"],
            "start": ["start", "start_line", "from_line", "line_start"],
            "end": ["end", "end_line", "to_line", "line_end"],
            # limits/counts
            "max_matches": ["max_matches", "limit"],
            "max_results": ["max_results", "limit"],
            "count": ["count", "max_replacements"],
            "flags": ["flags"],
            # referencing symbols / options
            "include_definitions": ["include_definitions", "include_defs", "with_definitions"],
            "kinds": ["kinds", "symbol_kinds", "symbolKinds", "types"],
            # shell exec
            "command": ["command", "cmd", "shell_command", "sh", "bash"],
            "cwd": ["cwd", "workdir", "working_directory", "dir"],
            "env": ["env", "environment"],
            "shell": ["shell"],
            "timeout": ["timeout", "timeout_s", "seconds"],
        }

        # Direct matches first
        for k, v in candidates.items():
            if k in schema_keys and v is not None:
                out[k] = v

        # Synonym mapping
        for group, alias_list in synonyms.items():
            value = None
            for a in alias_list:
                if a in candidates and candidates[a] is not None:
                    value = candidates[a]
                    break
            if value is None:
                continue

            # If any alias already matched directly, skip
            already = any((a in out) for a in alias_list)
            if already:
                continue

            # Find schema key within this group
            for a in alias_list:
                if a in schema_keys and a not in out:
                    out[a] = value
                    break

            # Or the group name itself
            if group in schema_keys and group not in out:
                out[group] = value

        return out


# Optional quick test
if __name__ == "__main__":
    async def _quick():
        proj = os.environ.get("CODE_ROOT") or os.getcwd()
        async with SerenaClient(project_path=proj) as sc:
            print("Tools:", ", ".join(await sc.list_tools()))

    asyncio.run(_quick())