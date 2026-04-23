"""Tools framework for C.E.H.

Provides:
  - ToolRegistry: central registry for tool discovery and dispatch
  - PermissionManager: autonomous/approval mode with error tracking
  - Pydantic-based tool schema validation
  - Sandboxed subprocess execution (shell=False, restricted env)
  - Built-in tools: read_file, write_file, execute_command, web_search
  - MCP (Model Context Protocol) adapter interface

Constants
---------
PERMISSION_AUTONOMOUS = "autonomous"
PERMISSION_APPROVAL = "approval"
"""

from __future__ import annotations

import logging
import os
import subprocess
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type, Union

from pydantic import BaseModel, Field, ValidationError

from c_e_h.security import (
    PathTraversalError,
    log_security_event,
    safe_path_any,
    sanitize_input,
    validate_command,
)

logger = logging.getLogger(__name__)


def _log_info(msg: str, **kwargs: Any) -> None:
    """Log info message with extra fields (structlog-compatible)."""
    if kwargs:
        extra = " ".join(f"{k}={v!r}" for k, v in kwargs.items())
        logger.info(f"{msg} {extra}")
    else:
        logger.info(msg)


def _log_warning(msg: str, **kwargs: Any) -> None:
    """Log warning message with extra fields."""
    if kwargs:
        extra = " ".join(f"{k}={v!r}" for k, v in kwargs.items())
        logger.warning(f"{msg} {extra}")
    else:
        logger.warning(msg)


def _log_error(msg: str, **kwargs: Any) -> None:
    """Log error message with extra fields."""
    if kwargs:
        extra = " ".join(f"{k}={v!r}" for k, v in kwargs.items())
        logger.error(f"{msg} {extra}")
    else:
        logger.error(msg)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PERMISSION_AUTONOMOUS = "autonomous"
PERMISSION_APPROVAL = "approval"
DEFAULT_MAX_AUTO_ERRORS = 3
DEFAULT_SUCCESS_RESET = 5
SANDBOX_TIMEOUT = 30
ALLOWED_ENV_PREFIXES = ("PATH", "HOME", "USER", "LANG", "LC_", "TERM", "SHELL")
WORKSPACE_ROOT = Path.cwd().resolve()
ALLOWED_PATHS = [WORKSPACE_ROOT, Path("/tmp").resolve()]

# ---------------------------------------------------------------------------
# Permission States
# ---------------------------------------------------------------------------


class PermissionState(str, Enum):
    """Permission states for agent autonomy."""

    AUTONOMOUS = "autonomous"
    APPROVAL = "approval"


# ---------------------------------------------------------------------------
# Tool Schema Models (Pydantic)
# ---------------------------------------------------------------------------


class ReadFileSchema(BaseModel):
    """Schema for read_file tool."""

    path: str = Field(..., description="Path to file to read", min_length=1)
    max_lines: int = Field(default=100, description="Maximum lines to read", ge=1)


class WriteFileSchema(BaseModel):
    """Schema for write_file tool."""

    path: str = Field(..., description="Path to file to write", min_length=1)
    content: str = Field(..., description="Content to write", min_length=0)
    append: bool = Field(default=False, description="Append to file instead of overwriting")


class ExecuteCommandSchema(BaseModel):
    """Schema for execute_command tool."""

    command: str = Field(..., description="Shell command to execute", min_length=1)
    timeout: int = Field(default=30, description="Maximum execution time in seconds", ge=1)


class WebSearchSchema(BaseModel):
    """Schema for web_search tool."""

    query: str = Field(..., description="Search query", min_length=1)
    max_results: int = Field(default=5, description="Maximum number of results", ge=1, le=20)


class ListDirectorySchema(BaseModel):
    """Schema for list_directory tool."""

    path: str = Field(..., description="Directory path to list", min_length=1)
    recursive: bool = Field(default=False, description="List recursively")


class CreateDirectorySchema(BaseModel):
    """Schema for create_directory tool."""

    path: str = Field(..., description="Directory path to create", min_length=1)
    parents: bool = Field(default=False, description="Create parent directories")


class DeleteFileSchema(BaseModel):
    """Schema for delete_file tool."""

    path: str = Field(..., description="File path to delete", min_length=1)


class ImportModuleSchema(BaseModel):
    """Schema for import_module tool."""

    module_name: str = Field(..., description="Module name to import", min_length=1)


class SearchFilesSchema(BaseModel):
    """Schema for search_files tool."""

    pattern: str = Field(..., description="Glob pattern to search for", min_length=1)
    path: str = Field(default=".", description="Directory path to search in")


class GithubSchema(BaseModel):
    """Schema for github tool."""

    action: str = Field(..., description="GitHub action: list_issues, create_issue, list_files, etc.", min_length=1)
    repo: str = Field(..., description="Repository in format owner/repo", min_length=1)
    path: str = Field(default="", description="File path (for list_files)")


# ---------------------------------------------------------------------------
# Tool Definition
# ---------------------------------------------------------------------------


class ToolDefinition(BaseModel):
    """Definition of a registered tool."""

    name: str
    description: str
    input_schema: Optional[Type[BaseModel]] = None
    func: Callable
    enabled: bool = True


# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------


class ToolRegistry:
    """Registry for available agent tools.

    Provides ``register()``, ``get()``, and ``list()`` methods for
    tool discovery and dispatch.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        description: str = "",
        input_schema: Optional[Type[BaseModel]] = None,
    ) -> Callable[[Callable], Callable]:
        """Decorator to register a tool function.

        Args:
            name: Unique tool name.
            description: Human-readable description.
            input_schema: Optional Pydantic model for input validation.

        Returns:
            Decorator function.
        """

        def decorator(func: Callable) -> Callable:
            self._tools[name] = ToolDefinition(
                name=name,
                description=description,
                input_schema=input_schema,
                func=func,
            )
            _log_info("Tool registered", tool_name=name)
            return func

        return decorator

    def get(self, name: str) -> Optional[ToolDefinition]:
        """Retrieve a tool definition by name.

        Args:
            name: Tool name.

        Returns:
            ToolDefinition or None if not found.
        """
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        """List all registered (enabled) tool names.

        Returns:
            List of tool name strings.
        """
        return [name for name, t in self._tools.items() if t.enabled]

    def list_all_tools(self) -> List[str]:
        """List ALL registered tool names (including disabled).

        Returns:
            List of all tool name strings.
        """
        return [name for name in self._tools]

    def disable_tool(self, name: str) -> bool:
        """Disable a tool by name.

        Args:
            name: Tool name.

        Returns:
            True if tool was found and disabled.
        """
        tool = self._tools.get(name)
        if tool:
            tool.enabled = False
            _log_info("Tool disabled", tool_name=name)
            return True
        return False

    def enable_tool(self, name: str) -> bool:
        """Enable a tool by name.

        Args:
            name: Tool name.

        Returns:
            True if tool was found and enabled.
        """
        tool = self._tools.get(name)
        if tool:
            tool.enabled = True
            _log_info("Tool enabled", tool_name=name)
            return True
        return False


# Global registry instance
registry = ToolRegistry()


# ---------------------------------------------------------------------------
# Permission Manager
# ---------------------------------------------------------------------------


class PermissionManager:
    """Manages agent permission modes with graceful degradation.

    - Agent starts in ``autonomous`` mode.
    - Error counter tracks consecutive failures.
    - After ``max_auto_errors`` consecutive errors: switch to ``approval`` mode.
    - After ``success_reset`` consecutive successful steps in approval mode:
      switch back to ``autonomous`` mode and reset counters.
    """

    def __init__(
        self,
        initial_state: PermissionState = PermissionState.AUTONOMOUS,
        max_auto_errors: int = DEFAULT_MAX_AUTO_ERRORS,
        success_reset: int = DEFAULT_SUCCESS_RESET,
    ) -> None:
        self._state = initial_state
        self._max_auto_errors = max_auto_errors
        self._success_reset = success_reset
        self._error_count: int = 0
        self._success_count: int = 0

    @property
    def state(self) -> PermissionState:
        """Current permission state."""
        return self._state

    @property
    def is_autonomous(self) -> bool:
        """True if agent is in autonomous mode."""
        return self._state == PermissionState.AUTONOMOUS

    @property
    def error_count(self) -> int:
        """Current consecutive error count."""
        return self._error_count

    @property
    def success_count(self) -> int:
        """Current consecutive success count."""
        return self._success_count

    @property
    def max_auto_errors(self) -> int:
        """Configurable error threshold."""
        return self._max_auto_errors

    @property
    def success_reset(self) -> int:
        """Configurable success threshold for mode reset."""
        return self._success_reset

    def record_success(self) -> None:
        """Record a successful tool execution.

        If in approval mode and success_reset threshold reached,
        switch back to autonomous mode.
        """
        self._success_count += 1
        self._error_count = 0  # Reset error counter on success

        if (
            self._state == PermissionState.APPROVAL
            and self._success_count >= self._success_reset
        ):
            self._state = PermissionState.AUTONOMOUS
            self._success_count = 0
            _log_info(
                "Permission mode switched to autonomous",
                success_count=self._success_count,
            )

    def record_error(self) -> None:
        """Record a failed tool execution.

        If in autonomous mode and error_count reaches threshold,
        switch to approval mode.
        """
        self._error_count += 1
        self._success_count = 0  # Reset success counter on error

        if (
            self._state == PermissionState.AUTONOMOUS
            and self._error_count >= self._max_auto_errors
        ):
            self._state = PermissionState.APPROVAL
            _log_warning(
                "Permission mode switched to approval",
                error_count=self._error_count,
                threshold=self._max_auto_errors,
            )

    def requires_approval(self) -> bool:
        """Check if current step requires user approval.

        Returns:
            True if in approval mode.
        """
        return self._state == PermissionState.APPROVAL

    def request_approval(self, tool_name: str, args: Dict[str, Any]) -> bool:
        """Request user approval for a tool execution.

        In approval mode, this would typically prompt the user.
        For now, returns True (auto-approve) but logs the request.

        Args:
            tool_name: Name of the tool to execute.
            args: Tool arguments.

        Returns:
            True if approved, False if denied.
        """
        # Sanitize args before logging to avoid exposing sensitive data
        _SENSITIVE_KEYS = {"password", "secret", "token", "api_key", "apikey", "credential"}
        safe_args = {
            k: str(v)[:50] if not isinstance(v, (str, int, float, bool, type(None))) else v
            for k, v in args.items()
            if k.lower() not in _SENSITIVE_KEYS
        }
        _log_info(
            "Approval requested",
            tool_name=tool_name,
            args=safe_args,
        )
        # In a real implementation, this would prompt the user.
        # For now, auto-approve to avoid blocking.
        return True

    def reset(self) -> None:
        """Reset all counters and return to autonomous mode."""
        self._state = PermissionState.AUTONOMOUS
        self._error_count = 0
        self._success_count = 0
        _log_info("Permission manager reset")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize permission state to dictionary."""
        return {
            "state": self._state.value,
            "error_count": self._error_count,
            "success_count": self._success_count,
            "max_auto_errors": self._max_auto_errors,
            "success_reset": self._success_reset,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PermissionManager":
        """Restore permission manager from dictionary."""
        pm = cls(
            initial_state=PermissionState(data.get("state", "autonomous")),
            max_auto_errors=data.get("max_auto_errors", DEFAULT_MAX_AUTO_ERRORS),
            success_reset=data.get("success_reset", DEFAULT_SUCCESS_RESET),
        )
        pm._error_count = data.get("error_count", 0)
        pm._success_count = data.get("success_count", 0)
        return pm


# ---------------------------------------------------------------------------
# Tool Validation
# ---------------------------------------------------------------------------


def validate_tool_input(schema: Type[BaseModel], args: Dict[str, Any]) -> Dict[str, Any]:
    """Validate tool arguments against a Pydantic schema.

    Args:
        schema: Pydantic model class for validation.
        args: Tool arguments dictionary.

    Returns:
        Validated and normalized arguments.

    Raises:
        ValueError: If validation fails.
    """
    # Skip validation for bare BaseModel or None (no fields defined)
    if schema is BaseModel or schema is None:
        return dict(args)
    try:
        validated = schema(**args)
        return validated.model_dump()
    except ValidationError as e:
        error_msg = f"Tool validation failed: {e}"
        _log_error("Tool validation failed", error=error_msg, args=args)
        raise ValueError(error_msg) from e


# ---------------------------------------------------------------------------
# Sandboxed Execution
# ---------------------------------------------------------------------------


def _build_restricted_env() -> Dict[str, str]:
    """Build a restricted environment for sandboxed execution.

    Only allows safe environment variables with known prefixes.
    Removes potentially dangerous variables like PYTHONPATH, LD_PRELOAD, etc.

    Returns:
        Sanitized environment dictionary.
    """
    restricted = {}
    for key, value in os.environ.items():
        if key.startswith(ALLOWED_ENV_PREFIXES) or key in (
            "PATH",
            "HOME",
            "USER",
            "LANG",
            "TERM",
            "SHELL",
        ):
            restricted[key] = value
    # Remove dangerous variables
    for dangerous in (
        "PYTHONPATH",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "DYLD_LIBRARY_PATH",
        "DYLD_FALLBACK_LIBRARY_PATH",
        "PYTHONHASHSEED",
    ):
        restricted.pop(dangerous, None)
    return restricted


def sandbox_execute(
    command: Union[str, List[str]],
    timeout: int = SANDBOX_TIMEOUT,
    work_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute a command in a sandboxed environment.

    Uses ``subprocess.run()`` with ``shell=False``, restricted environment,
    and timeout.

    Args:
        command: Command as string (parsed by shlex) or list of arguments.
        timeout: Maximum execution time in seconds.
        work_dir: Working directory for the command.

    Returns:
        Dict with 'stdout', 'stderr', 'returncode', and 'timed_out'.
    """
    import shlex

    # Parse string command into list for shell=False
    if isinstance(command, str):
        # Safety: do NOT use shell=True; parse manually
        try:
            parts = shlex.split(command)
        except ValueError as e:
            return {
                "stdout": "",
                "stderr": f"Command parse error: {e}",
                "returncode": 1,
                "timed_out": False,
            }
    else:
        parts = list(command)

    # Security: reject commands with dangerous built-ins
    if parts:
        cmd_name = Path(parts[0]).name
        dangerous_cmds = ("rm", "mkfs", "dd", "shutdown", "reboot", "poweroff")
        if cmd_name in dangerous_cmds:
            _log_warning("Blocked dangerous command", command=parts[0])
            return {
                "stdout": "",
                "stderr": f"Command '{cmd_name}' is blocked for security reasons",
                "returncode": 1,
                "timed_out": False,
            }

    env = _build_restricted_env()

    kwargs: Dict[str, Any] = {
        "args": parts,
        "shell": False,
        "env": env,
        "timeout": timeout,
        "capture_output": True,
        "text": True,
    }

    if work_dir:
        kwargs["cwd"] = work_dir

    try:
        result = subprocess.run(**kwargs)  # type: ignore[arg-type]
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"Command timed out after {timeout} seconds",
            "returncode": -1,
            "timed_out": True,
        }
    except FileNotFoundError:
        return {
            "stdout": "",
            "stderr": f"Command not found: {parts[0]}",
            "returncode": 127,
            "timed_out": False,
        }
    except PermissionError:
        return {
            "stdout": "",
            "stderr": f"Permission denied: {parts[0]}",
            "returncode": 13,
            "timed_out": False,
        }


# ---------------------------------------------------------------------------
# Built-in Tools
# ---------------------------------------------------------------------------


# --- read_file ---

@registry.register(
    name="read_file",
    description="Read contents of a file with line limit",
    input_schema=ReadFileSchema,
)
def read_file(path: str, max_lines: int = 100) -> str:
    """Read a file and return its contents.

    Args:
        path: File path to read.
        max_lines: Maximum number of lines to read.

    Returns:
        File contents as string.

    Raises:
        FileNotFoundError: If file does not exist.
        PermissionError: If file cannot be read.
        PathTraversalError: If path is outside allowed directories.
    """
    # Security: sanitize input length
    sanitized_path = sanitize_input(path, max_length=2048)

    # Security: path traversal prevention using safe_path_any with ALLOWED_PATHS
    try:
        resolved = Path(safe_path_any([str(p) for p in ALLOWED_PATHS], sanitized_path))
    except PathTraversalError:
        log_security_event(
            "read_file_path_traversal",
            {"path": sanitized_path, "allowed_paths": [str(p) for p in ALLOWED_PATHS]},
        )
        raise PathTraversalError(f"Path traversal detected: {sanitized_path}")

    # Check if file exists
    if not resolved.exists():
        raise FileNotFoundError(f"File not found: {sanitized_path}")

    if not resolved.is_file():
        raise ValueError(f"Not a file: {sanitized_path}")

    # Read file with line limit
    try:
        with open(resolved, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except PermissionError:
        raise PermissionError(f"Permission denied: {sanitized_path}")
    except UnicodeDecodeError:
        raise ValueError(f"Cannot read non-text file: {sanitized_path}")

    # Apply line limit
    if len(lines) > max_lines:
        truncated = lines[:max_lines]
        truncated.append(f"\n... (truncated, {len(lines) - max_lines} more lines)\n")
        return "".join(truncated)
    return "".join(lines)


# --- write_file ---

@registry.register(
    name="write_file",
    description="Write content to a file, optionally appending",
    input_schema=WriteFileSchema,
)
def write_file(path: str, content: str, append: bool = False) -> str:
    """Write content to a file.

    Args:
        path: File path to write.
        content: Content to write.
        append: If True, append to file instead of overwriting.

    Returns:
        Confirmation message with bytes written.

    Raises:
        PathTraversalError: If path is outside allowed directories.
        PermissionError: If file cannot be written.
    """
    # Security: sanitize inputs
    sanitized_path = sanitize_input(path, max_length=2048)
    sanitized_content = sanitize_input(content, max_length=1_000_000)

    # Security: path traversal prevention using safe_path_any with ALLOWED_PATHS
    try:
        resolved = Path(safe_path_any([str(p) for p in ALLOWED_PATHS], sanitized_path))
    except PathTraversalError:
        log_security_event(
            "write_file_path_traversal",
            {"path": sanitized_path, "allowed_paths": [str(p) for p in ALLOWED_PATHS]},
        )
        raise PathTraversalError(f"Path traversal detected: {sanitized_path}")

    # Ensure parent directory exists
    resolved.parent.mkdir(parents=True, exist_ok=True)

    mode = "a" if append else "w"
    try:
        with open(resolved, mode, encoding="utf-8") as f:
            f.write(sanitized_content)
    except PermissionError:
        raise PermissionError(f"Permission denied: {sanitized_path}")

    bytes_written = len(sanitized_content.encode("utf-8"))
    return f"Successfully wrote {bytes_written} bytes to {sanitized_path}"


# --- execute_command ---

@registry.register(
    name="execute_command",
    description="Execute a shell command in a sandboxed environment",
    input_schema=ExecuteCommandSchema,
)
def execute_command(command: str, timeout: int = 30) -> str:
    """Execute a command in a sandboxed environment.

    Validates the command against the whitelist and enforces shell=False.

    Args:
        command: Shell command to execute.
        timeout: Maximum execution time in seconds.

    Returns:
        Formatted output with stdout, stderr, and return code.

    Raises:
        CommandNotAllowedError: If command is not in the whitelist.
    """
    # Security: sanitize input length
    sanitized_command = sanitize_input(command, max_length=4096)

    # Security: validate command against whitelist
    cmd_name = validate_command(sanitized_command)

    # Security: log allowed command execution
    log_security_event(
        "command_executed",
        {"command": sanitized_command, "cmd_name": cmd_name},
    )

    result = sandbox_execute(sanitized_command, timeout=timeout)

    output_parts = [f"Command: {sanitized_command}"]
    output_parts.append(f"Return code: {result['returncode']}")

    if result["stdout"]:
        output_parts.append(f"stdout:\n{result['stdout']}")
    if result["stderr"]:
        output_parts.append(f"stderr:\n{result['stderr']}")
    if result["timed_out"]:
        output_parts.append("TIMEOUT: Command exceeded time limit")

    return "\n".join(output_parts)


# --- web_search ---

@registry.register(
    name="web_search",
    description="Search the web using Brave Search API",
    input_schema=WebSearchSchema,
)
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web using Brave Search API.

    Requires BRAVE_API_KEY environment variable.
    Falls back gracefully if API key is not set.

    Args:
        query: Search query string.
        max_results: Maximum number of results to return (1-20).

    Returns:
        Formatted search results or configuration message.
    """
    import os

    api_key = os.environ.get("BRAVE_API_KEY")
    if not api_key:
        return (
            "Web search requires BRAVE_API_KEY environment variable. "
            "Get a free key at https://brave.com/search/api/ and set it in your environment."
        )

    try:
        import json
        import urllib.parse
        import urllib.request

        url = f"https://api.search.brave.com/res/v1/web/search?q={urllib.parse.quote(query)}&count={min(max_results, 20)}"
        request = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        })
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))

        results = data.get("web", {}).get("results", [])
        if not results:
            return f"No results found for: {query}"

        output_parts = [f"Search results for: {query}\n"]
        for i, result in enumerate(results[:max_results], 1):
            title = result.get("title", "No title")
            url = result.get("url", "")
            snippet = result.get("description", "")
            output_parts.append(f"{i}. {title}\n   {url}\n   {snippet}\n")

        return "\n".join(output_parts)
    except Exception as e:
        return f"Web search failed: {e}"


# --- list_directory ---

@registry.register(
    name="list_directory",
    description="List files and directories in a path",
    input_schema=ListDirectorySchema,
)
def list_directory(path: str, recursive: bool = False) -> str:
    """List contents of a directory.

    Args:
        path: Directory path to list.
        recursive: If True, list recursively.

    Returns:
        Formatted directory listing.

    Raises:
        FileNotFoundError: If directory does not exist.
        PathTraversalError: If path is outside allowed directories.
    """
    sanitized_path = sanitize_input(path, max_length=2048)

    try:
        resolved = Path(safe_path_any([str(p) for p in ALLOWED_PATHS], sanitized_path))
    except PathTraversalError:
        raise PathTraversalError(f"Path traversal detected: {sanitized_path}")

    if not resolved.exists():
        raise FileNotFoundError(f"Path not found: {sanitized_path}")

    if not resolved.is_dir():
        raise ValueError(f"Not a directory: {sanitized_path}")

    if recursive:
        output_parts = [f"Directory listing (recursive): {sanitized_path}\n"]
        for root, dirs, files in os.walk(resolved):
            level = root.replace(str(resolved), "").count(os.sep)
            indent = "  " * level
            output_parts.append(f"{indent}[DIR] {root.name}/")
            subindent = "  " * (level + 1)
            for file in sorted(files):
                output_parts.append(f"{subindent}  {file}")
        return "\n".join(output_parts)
    else:
        output_parts = [f"Directory listing: {sanitized_path}\n"]
        for item in sorted(resolved.iterdir()):
            prefix = "[DIR] " if item.is_dir() else "      "
            output_parts.append(f"{prefix}{item.name}")
        return "\n".join(output_parts)


# --- create_directory ---

@registry.register(
    name="create_directory",
    description="Create a new directory (with optional parents)",
    input_schema=CreateDirectorySchema,
)
def create_directory(path: str, parents: bool = False) -> str:
    """Create a directory.

    Args:
        path: Directory path to create.
        parents: If True, create parent directories as needed.

    Returns:
        Confirmation message.

    Raises:
        PathTraversalError: If path is outside allowed directories.
    """
    sanitized_path = sanitize_input(path, max_length=2048)

    try:
        resolved = Path(safe_path_any([str(p) for p in ALLOWED_PATHS], sanitized_path))
    except PathTraversalError:
        raise PathTraversalError(f"Path traversal detected: {sanitized_path}")

    mkdir_kwargs = {"exist_ok": True}
    if parents:
        mkdir_kwargs["parents"] = True

    resolved.mkdir(**mkdir_kwargs)
    return f"Directory created: {sanitized_path}"


# --- delete_file ---

@registry.register(
    name="delete_file",
    description="Delete a file from the filesystem",
    input_schema=DeleteFileSchema,
)
def delete_file(path: str) -> str:
    """Delete a file.

    Args:
        path: File path to delete.

    Returns:
        Confirmation message.

    Raises:
        FileNotFoundError: If file does not exist.
        PathTraversalError: If path is outside allowed directories.
        PermissionError: If file cannot be deleted.
    """
    sanitized_path = sanitize_input(path, max_length=2048)

    try:
        resolved = Path(safe_path_any([str(p) for p in ALLOWED_PATHS], sanitized_path))
    except PathTraversalError:
        raise PathTraversalError(f"Path traversal detected: {sanitized_path}")

    if not resolved.exists():
        raise FileNotFoundError(f"File not found: {sanitized_path}")

    if not resolved.is_file():
        raise ValueError(f"Not a file: {sanitized_path}")

    resolved.unlink()
    log_security_event("file_deleted", {"path": sanitized_path})
    return f"File deleted: {sanitized_path}"


# --- import_module ---

# Whitelist of allowed modules for import_module tool
ALLOWED_IMPORT_MODULES: frozenset = frozenset({
    # Standard library
    "os", "sys", "json", "re", "math", "datetime", "pathlib", "collections",
    "itertools", "functools", "typing", "subprocess", "shutil", "glob",
    "hashlib", "logging", "argparse", "textwrap", "string", "io",
    "csv", "html", "xml", "urllib", "http", "email", "copy",
    "time", "calendar", "random", "secrets",
    # Approved third-party
    "pydantic", "rich", "yaml", "structlog", "typer",
})


@registry.register(
    name="import_module",
    description="Import a Python module from the whitelist",
    input_schema=ImportModuleSchema,
)
def import_module(module_name: str) -> str:
    """Import a module from the whitelist.

    Only modules in ALLOWED_IMPORT_MODULES can be imported.

    Args:
        module_name: Module name to import.

    Returns:
        Module info or error message.

    Raises:
        SecurityError: If module is not in whitelist.
    """
    base_module = module_name.split(".")[0]
    if base_module not in ALLOWED_IMPORT_MODULES:
        raise ValueError(
            f"Module '{base_module}' is not in the import whitelist. "
            f"Allowed: {sorted(ALLOWED_IMPORT_MODULES)}"
        )

    try:
        import importlib
        module = importlib.import_module(module_name)
        attrs = dir(module)
        public_attrs = [a for a in attrs if not a.startswith("_")]
        return (
            f"Module '{module_name}' imported successfully.\n"
            f"Type: {type(module)}\n"
            f"File: {getattr(module, '__file__', 'N/A')}\n"
            f"Public members ({len(public_attrs)}): {', '.join(public_attrs[:20])}"
            + ("..." if len(public_attrs) > 20 else "")
        )
    except ImportError as e:
        return f"Failed to import '{module_name}': {e}"
    except Exception as e:
        return f"Error importing '{module_name}': {e}"


# --- search_files ---

@registry.register(
    name="search_files",
    description="Search for files matching a glob pattern",
    input_schema=SearchFilesSchema,
)
def search_files(pattern: str, path: str = ".") -> str:
    """Search for files matching a glob pattern.

    Args:
        pattern: Glob pattern (e.g., '*.py', '**/*.md').
        path: Directory to search in.

    Returns:
        List of matching file paths.
    """
    sanitized_path = sanitize_input(path, max_length=2048)
    sanitized_pattern = sanitize_input(pattern, max_length=2048)

    try:
        resolved = Path(safe_path_any([str(p) for p in ALLOWED_PATHS], sanitized_path))
    except PathTraversalError:
        raise PathTraversalError(f"Path traversal detected: {sanitized_path}")

    if not resolved.is_dir():
        raise ValueError(f"Not a directory: {sanitized_path}")

    matches = sorted(resolved.glob(sanitized_pattern))
    if not matches:
        return f"No files matching '{sanitized_pattern}' in {sanitized_path}"

    output_parts = [f"Found {len(matches)} file(s) matching '{sanitized_pattern}' in {sanitized_path}:"]
    for m in matches:
        size = m.stat().st_size if m.is_file() else 0
        output_parts.append(f"  {m.relative_to(resolved)} ({size} bytes)")

    return "\n".join(output_parts)


# --- github ---

@registry.register(
    name="github",
    description="GitHub API operations (list_issues, create_issue, list_files, etc.)",
    input_schema=GithubSchema,
)
def github(action: str, repo: str, path: str = "") -> str:
    """Perform GitHub API operations.

    Requires GITHUB_TOKEN environment variable for authenticated requests.

    Args:
        action: GitHub action (list_issues, create_issue, list_files, get_file).
        repo: Repository in format owner/repo.
        path: File path (for list_files/get_file actions).

    Returns:
        GitHub API response formatted as text.
    """
    import json
    import os

    token = os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    api_base = f"https://api.github.com/repos/{repo}"

    try:
        if action == "list_issues":
            url = f"{api_base}/issues"
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=15) as response:
                issues = json.loads(response.read().decode("utf-8"))
            if not issues:
                return f"No issues found in {repo}"
            output_parts = [f"Issues in {repo}:"]
            for issue in issues[:20]:
                state = issue.get("state", "?")
                title = issue.get("title", "No title")
                num = issue.get("number", "?")
                output_parts.append(f"  #{num} [{state}] {title}")
            return "\n".join(output_parts)

        elif action == "list_files":
            api_path = f"{api_base}/contents/{path}" if path else api_base
            url = api_path
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=15) as response:
                files = json.loads(response.read().decode("utf-8"))
            if not files:
                return f"No files found at {path} in {repo}"
            output_parts = [f"Files in {repo}/{path or '/'}:"]
            for f in files:
                ftype = f.get("type", "?")
                name = f.get("name", "?")
                size = f.get("size", 0)
                output_parts.append(f"  [{ftype}] {name} ({size} bytes)")
            return "\n".join(output_parts)

        elif action == "get_file":
            if not path:
                return "Error: 'path' parameter required for get_file action"
            url = f"{api_base}/contents/{path}"
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))
            content_b64 = data.get("content", "")
            import base64
            content = base64.b64decode(content_b64).decode("utf-8") if content_b64 else ""
            return f"File: {repo}/{path}\n---\n{content[:5000]}"

        elif action == "create_issue":
            if not token:
                return "Error: GITHUB_TOKEN environment variable required for create_issue"
            url = f"{api_base}/issues"
            data_json = json.dumps({
                "title": "New Issue",
                "body": "Issue body",
            }).encode("utf-8")
            request = urllib.request.Request(url, data=data_json, headers=headers, method="POST")
            with urllib.request.urlopen(request, timeout=15) as response:
                result = json.loads(response.read().decode("utf-8"))
            return f"Issue created: #{result.get('number')} - {result.get('html_url')}"

        else:
            return (
                f"Unknown action: {action}\n"
                f"Supported actions: list_issues, create_issue, list_files, get_file"
            )

    except urllib.error.HTTPError as e:
        return f"GitHub API error: {e.code} {e.reason}"
    except urllib.error.URLError as e:
        return f"Network error: {e.reason}"
    except Exception as e:
        return f"GitHub operation failed: {e}"


# ---------------------------------------------------------------------------
# Tool Executor
# ---------------------------------------------------------------------------


class ToolExecutor:
    """Executes tools with validation and permission checks.

    Args:
        tool_registry: ToolRegistry instance.
        permission_manager: PermissionManager instance.
    """

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        permission_manager: Optional[PermissionManager] = None,
    ) -> None:
        self.registry = tool_registry if tool_registry is not None else registry
        self.permission_manager = permission_manager or PermissionManager()

    def execute(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool by name with validation and permission checks.

        Args:
            tool_name: Name of the tool to execute.
            args: Tool arguments.

        Returns:
            Dict with 'success', 'output', and optional 'error'.
        """
        # Check permission
        if self.permission_manager.requires_approval():
            if not self.permission_manager.request_approval(tool_name, args):
                return {
                    "success": False,
                    "output": "Tool execution denied by user",
                    "error": "Approval denied",
                }

        # Get tool
        tool_def = self.registry.get(tool_name)
        if tool_def is None:
            return {
                "success": False,
                "output": "",
                "error": f"Tool not found: {tool_name}",
            }

        if not tool_def.enabled:
            return {
                "success": False,
                "output": "",
                "error": f"Tool disabled: {tool_name}",
            }

        # Validate input
        try:
            validated_args = validate_tool_input(tool_def.input_schema, args)
        except ValueError as e:
            self.permission_manager.record_error()
            return {
                "success": False,
                "output": "",
                "error": str(e),
            }

        # Execute tool
        try:
            output = tool_def.func(**validated_args)
            self.permission_manager.record_success()
            return {
                "success": True,
                "output": str(output),
                "error": None,
            }
        except (ValueError, TypeError, FileNotFoundError, PermissionError, OSError) as e:
            self.permission_manager.record_error()
            _log_error("Tool execution failed", tool_name=tool_name, error=e)
        except Exception as e:
            # Catch-all for unexpected errors from user-defined tool functions
            self.permission_manager.record_error()
            _log_error("Tool execution failed (unexpected)", tool_name=tool_name, error=e)
            return {
                "success": False,
                "output": "",
                "error": f"Execution error: {e}",
            }


# ---------------------------------------------------------------------------
# MCP (Model Context Protocol) Adapter
# ---------------------------------------------------------------------------


class MCPToolSchema(BaseModel):
    """MCP-style tool schema."""

    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Tool description")
    input_schema: Dict[str, Any] = Field(
        default_factory=dict, description="JSON Schema for input"
    )


class MCPToolCall(BaseModel):
    """MCP-style tool call."""

    id: str = Field(..., description="Call ID")
    name: str = Field(..., description="Tool name")
    arguments: Dict[str, Any] = Field(
        default_factory=dict, description="Tool arguments"
    )


class MCPAdapter:
    """Minimal Model Context Protocol adapter for tool interoperability.

    Provides a bridge between MCP-style tool calls and the C.E.H. ToolRegistry.
    """

    def __init__(self, tool_registry: Optional[ToolRegistry] = None) -> None:
        self.registry = tool_registry if tool_registry is not None else registry
        self._mcp_tools: Dict[str, Dict[str, Any]] = {}

    def register_mcp_tool(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        handler: Callable,
    ) -> None:
        """Register an MCP-style tool.

        Args:
            name: Tool name.
            description: Tool description.
            input_schema: JSON Schema dict for input validation.
            handler: Callable that executes the tool.
        """
        self._mcp_tools[name] = {
            "name": name,
            "description": description,
            "input_schema": input_schema,
            "handler": handler,
        }
        _log_info("MCP tool registered", tool_name=name)

    def list_mcp_tools(self) -> List[Dict[str, Any]]:
        """List all registered MCP tools.

        Returns:
            List of MCP tool schema dicts.
        """
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["input_schema"],
            }
            for t in self._mcp_tools.values()
        ]

    def call_mcp_tool(self, tool_call: MCPToolCall) -> Dict[str, Any]:
        """Execute an MCP-style tool call.

        Args:
            tool_call: MCPToolCall instance.

        Returns:
            Dict with 'id', 'content' (list of text blocks), and optional 'error'.
        """
        handler = self._mcp_tools.get(tool_call.name)
        if handler is None:
            return {
                "id": tool_call.id,
                "error": f"Unknown MCP tool: {tool_call.name}",
                "content": [{"type": "text", "text": f"Unknown tool: {tool_call.name}"}],
            }

        try:
            result = handler["handler"](**tool_call.arguments)
            return {
                "id": tool_call.id,
                "content": [{"type": "text", "text": str(result)}],
                "error": None,
            }
        except (ValueError, TypeError, FileNotFoundError, PermissionError, OSError) as e:
            _log_error("MCP tool call failed", tool=tool_call.name, error=e)
        except Exception as e:
            # Catch-all for unexpected errors from MCP handler functions
            _log_error("MCP tool call failed (unexpected)", tool=tool_call.name, error=e)
            return {
                "id": tool_call.id,
                "content": [{"type": "text", "text": f"Error: {e}"}],
                "error": str(e),
            }

    def sync_to_registry(self) -> int:
        """Sync MCP tools to the C.E.H. ToolRegistry.

        Returns:
            Number of tools synced.
        """
        count = 0
        for name, mcp_tool in self._mcp_tools.items():
            if not self.registry.get(name):
                self.registry.register(
                    name=name,
                    description=mcp_tool["description"],
                )(mcp_tool["handler"])
                count += 1
        return count


# ---------------------------------------------------------------------------
# Initialize built-in tools in registry
# ---------------------------------------------------------------------------

# Built-in tools are already registered via decorators above.
# This module-level registry instance contains them all.
