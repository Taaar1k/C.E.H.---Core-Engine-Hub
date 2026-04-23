# Tool Registry API

> Tool registration, validation, execution, and sandboxing framework.

## Overview

The [`tools`](../../src/c_e_h/tools.py) module provides a framework for registering, validating, and executing tools with built-in security controls. It is the central hub for all agent capabilities including file operations, command execution, web search, and GitHub API access.

## Module-Level Constants

### `registry`

The global [`ToolRegistry`](#toolregistry) instance. All built-in tools are registered against this singleton.

```python
registry = ToolRegistry()
```

### `ALLOWED_IMPORT_MODULES`

Whitelist of modules allowed for the `import_module` tool.

```python
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
```

## Classes

### `ToolDefinition`

```python
class ToolDefinition(BaseModel):
    """Definition of a registered tool."""

    name: str
    description: str
    input_schema: Optional[Type[BaseModel]] = None
    func: Callable
    enabled: bool = True
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Tool name (used in LLM tool calls) |
| `description` | `str` | Tool description (shown to LLM) |
| `input_schema` | `Optional[Type[BaseModel]]` | Pydantic schema for argument validation |
| `func` | `Callable` | Tool function |
| `enabled` | `bool` | Whether tool is enabled |

### `ToolRegistry`

Registry for available agent tools.

```python
class ToolRegistry:
    def __init__(self) -> None
```

**Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `register` | `(name: str, description: str, input_schema: Optional[Type[BaseModel]] = None) -> Callable` | Decorator to register a tool function |
| `get` | `(name: str) -> Optional[ToolDefinition]` | Get tool definition by name |
| `list_tools` | `() -> List[str]` | List all tool names |
| `list_all_tools` | `() -> List[str]` | List all tool names (including disabled) |
| `disable_tool` | `(name: str) -> bool` | Disable a tool by name |
| `enable_tool` | `(name: str) -> bool` | Enable a tool by name |

**Usage:**

```python
@registry.register(
    name="my_tool",
    description="My custom tool",
    input_schema=MySchema,
)
def my_tool(arg1: str, arg2: int = 10) -> str:
    return f"{arg1}: {arg2}"
```

### `PermissionManager`

Manages agent permission modes with graceful degradation.

- Agent starts in `autonomous` mode.
- Error counter tracks consecutive failures.
- After `max_auto_errors` consecutive errors: switch to `approval` mode.
- After `success_reset` consecutive successful steps in approval mode: switch back to `autonomous` mode and reset counters.

```python
class PermissionManager:
    def __init__(
        self,
        initial_state: PermissionState = PermissionState.AUTONOMOUS,
        max_auto_errors: int = DEFAULT_MAX_AUTO_ERRORS,
        success_reset: int = DEFAULT_SUCCESS_RESET,
    ) -> None
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `initial_state` | `PermissionState` | `AUTONOMOUS` | Initial permission state |
| `max_auto_errors` | `int` | `DEFAULT_MAX_AUTO_ERRORS` | Error threshold for mode switch |
| `success_reset` | `int` | `DEFAULT_SUCCESS_RESET` | Success count to reset to autonomous |

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `state` | `PermissionState` | Current permission state |
| `is_autonomous` | `bool` | True if agent is in autonomous mode |
| `error_count` | `int` | Current consecutive error count |
| `success_count` | `int` | Current consecutive success count |
| `max_auto_errors` | `int` | Configurable error threshold |
| `success_reset` | `int` | Configurable success threshold for mode reset |

**Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `record_success` | `() -> None` | Record a successful tool execution |
| `record_error` | `() -> None` | Record a failed tool execution |
| `requires_approval` | `() -> bool` | Check if current step requires user approval |
| `request_approval` | `(tool_name: str, args: Dict[str, Any]) -> bool` | Request user approval for a tool execution |
| `reset` | `() -> None` | Reset all counters and return to autonomous mode |
| `to_dict` | `() -> Dict[str, Any]` | Serialize permission state to dictionary |
| `from_dict` | `(data: Dict[str, Any]) -> "PermissionManager"` | Restore permission manager from dictionary |

### `PermissionState` (Enum)

```python
class PermissionState(str, Enum):
    AUTONOMOUS = "autonomous"
    APPROVAL = "approval"
```

### `ToolExecutor`

Executes tools with validation and permission checks.

```python
class ToolExecutor:
    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        permission_manager: Optional[PermissionManager] = None,
    ) -> None
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tool_registry` | `Optional[ToolRegistry]` | `None` | ToolRegistry instance (uses global `registry` if None) |
| `permission_manager` | `Optional[PermissionManager]` | `None` | PermissionManager instance (creates new if None) |

**Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `execute` | `(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]` | Execute a tool by name with validation and permission checks |

**Return value:**

```python
{
    "success": bool,
    "output": str,
    "error": Optional[str],
}
```

### `MCPAdapter`

Minimal Model Context Protocol adapter for tool interoperability.

```python
class MCPAdapter:
    def __init__(self, tool_registry: Optional[ToolRegistry] = None) -> None
```

**Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `register_mcp_tool` | `(name: str, description: str, input_schema: Dict[str, Any], func: Callable) -> None` | Register an MCP-style tool |
| `list_mcp_tools` | `() -> List[Dict[str, Any]]` | List all registered MCP tools |
| `call_mcp_tool` | `(tool_call: MCPToolCall) -> Dict[str, Any]` | Execute an MCP-style tool call |
| `sync_to_registry` | `() -> int` | Sync MCP tools to the main registry |

### `MCPToolSchema`

```python
class MCPToolSchema(BaseModel):
    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Tool description")
    input_schema: Dict[str, Any] = Field(default_factory=dict, description="JSON Schema for input")
```

### `MCPToolCall`

```python
class MCPToolCall(BaseModel):
    id: str = Field(..., description="Call ID")
    name: str = Field(..., description="Tool name")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
```

## Built-in Tools

All built-in tools are registered against the global `registry` instance. Each tool uses Pydantic schemas for input validation and security functions for sandboxing.

### Pydantic Schemas

| Schema | Fields | Tool |
|--------|--------|------|
| `ReadFileSchema` | `path: str`, `max_lines: int = 100` | `read_file` |
| `WriteFileSchema` | `path: str`, `content: str`, `append: bool = False` | `write_file` |
| `ExecuteCommandSchema` | `command: str`, `timeout: int = 30` | `execute_command` |
| `WebSearchSchema` | `query: str`, `max_results: int = 5` | `web_search` |
| `ListDirectorySchema` | `path: str`, `recursive: bool = False` | `list_directory` |
| `CreateDirectorySchema` | `path: str`, `parents: bool = False` | `create_directory` |
| `DeleteFileSchema` | `path: str` | `delete_file` |
| `ImportModuleSchema` | `module_name: str` | `import_module` |
| `SearchFilesSchema` | `pattern: str`, `path: str = "."` | `search_files` |
| `GithubSchema` | `action: str`, `repo: str`, `path: str = ""` | `github` |

### Tool List

| Tool | Description | Input Schema | Security |
|------|-------------|--------------|----------|
| `read_file` | Read contents of a file with line limit | `path: str`, `max_lines: int = 100` | Path traversal prevention via `safe_path_any(ALLOWED_PATHS)` |
| `write_file` | Write content to a file, optionally appending | `path: str`, `content: str`, `append: bool = False` | Path traversal prevention, input sanitization |
| `execute_command` | Execute a shell command in a sandboxed environment | `command: str`, `timeout: int = 30` | Command whitelist (`ALLOWED_COMMANDS`), `shell=False`, timeout |
| `web_search` | Search the web using Brave Search API | `query: str`, `max_results: int = 5` | Requires `BRAVE_API_KEY` env var |
| `list_directory` | List files and directories in a path | `path: str`, `recursive: bool = False` | Path traversal prevention |
| `create_directory` | Create a new directory (with optional parents) | `path: str`, `parents: bool = False` | Path traversal prevention |
| `delete_file` | Delete a file from the filesystem | `path: str` | Path traversal prevention, security logging |
| `import_module` | Import a Python module from the whitelist | `module_name: str` | Module whitelist (`ALLOWED_IMPORT_MODULES`) |
| `search_files` | Search for files matching a glob pattern | `pattern: str`, `path: str = "."` | Path traversal prevention |
| `github` | GitHub API operations (list_issues, create_issue, list_files, get_file) | `action: str`, `repo: str`, `path: str = ""` | Requires `GITHUB_TOKEN` for authenticated requests |

## Security Functions

The tools module imports security functions from [`src/c_e_h/security.py`](security.py):

```python
from c_e_h.security import (
    safe_path,
    safe_path_any,
    validate_command,
    sanitize_input,
    log_security_event,
    SecurityPolicy,
    SecurityError,
    PathTraversalError,
    CommandNotAllowedError,
    InputValidationError,
)
```

### Path Validation

All file operations validate paths against allowed directories using `safe_path_any()`:

```python
from c_e_h.security import ALLOWED_PATHS

resolved = Path(safe_path_any([str(p) for p in ALLOWED_PATHS], sanitized_path))
```

### Command Execution Sandboxing

| Rule | Implementation |
|------|----------------|
| `shell=False` | No shell interpretation |
| Timeout | 30-second hard limit (configurable) |
| Command whitelist | `ALLOWED_COMMANDS` from `security.py` |
| Environment | Restricted via `sandbox_execute()` |

### Module Import Whitelist

Only modules in `ALLOWED_IMPORT_MODULES` can be imported:

```python
# Standard library
"os", "sys", "json", "re", "math", "datetime", "pathlib", "collections",
"itertools", "functools", "typing", "subprocess", "shutil", "glob",
"hashlib", "logging", "argparse", "textwrap", "string", "io",
"csv", "html", "xml", "urllib", "http", "email", "copy",
"time", "calendar", "random", "secrets",
# Approved third-party
"pydantic", "rich", "yaml", "structlog", "typer",
```

## Helper Functions

### `validate_tool_input()`

```python
def validate_tool_input(schema: Type[BaseModel], args: Dict[str, Any]) -> Dict[str, Any]
```

Validate tool arguments against a Pydantic schema. Returns validated arguments or raises `ValueError`.

### `sandbox_execute()`

```python
def sandbox_execute(
    command: str,
    timeout: int = 30,
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]
```

Execute a command in a sandboxed environment. Returns dict with `stdout`, `stderr`, `returncode`, `timed_out`.

### `_build_restricted_env()`

```python
def _build_restricted_env() -> Dict[str, str]
```

Build a restricted environment dictionary for sandboxed command execution.

## Custom Tool Example

```python
from c_e_h.tools import registry
from pydantic import BaseModel, Field

class CalculateSchema(BaseModel):
    expression: str = Field(..., description="Mathematical expression to evaluate")

@registry.register(
    name="calculate",
    description="Evaluate a mathematical expression",
    input_schema=CalculateSchema,
)
def calculate(expression: str) -> str:
    """Evaluate a math expression safely."""
    import math
    allowed_names = {
        k: v for k, v in math.__dict__.items()
        if not k.startswith("_")
    }
    result = eval(expression, {"__builtins__": {}}, allowed_names)
    return str(result)
```

## Usage Example

```python
from c_e_h.tools import ToolRegistry, ToolExecutor, PermissionManager

# Create registry and executor
registry = ToolRegistry()
permission_manager = PermissionManager()
executor = ToolExecutor(registry, permission_manager)

# List available tools
tools = registry.list_tools()
print(f"Available tools: {tools}")

# Execute a tool
result = executor.execute("read_file", {"path": "./README.md"})
if result["success"]:
    print(result["output"])
else:
    print(f"Error: {result['error']}")

# Permission mode switching
print(f"Current mode: {permission_manager.state}")
permission_manager.record_error()
permission_manager.record_error()
permission_manager.record_error()  # Assuming max_auto_errors=3
print(f"Mode after errors: {permission_manager.state}")  # "approval"
```
