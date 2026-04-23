# Tool Registry API

> Tool registration, validation, execution, and sandboxing framework.

## Overview

The [`ToolRegistry`](../../src/c_e_h/tools.py) module provides a framework for registering, validating, and executing tools with built-in security controls.

## Class Definition

```python
class ToolRegistry:
    def __init__(self, permission_manager: PermissionManager | None = None) -> None: ...

    def register(self, tool: Tool) -> None: ...
    def unregister(self, tool_name: str) -> None: ...
    def get_tool(self, tool_name: str) -> Tool: ...
    def list_tools(self) -> list[ToolInfo]: ...
    def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult: ...
    def validate(self, tool_name: str, arguments: dict[str, Any]) -> bool: ...
```

### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `permission_manager` | `PermissionManager \| None` | `None` | Permission manager for access control |

## Decorator

### `@tool`

```python
def tool(
    name: str,
    description: str,
    requires_permission: bool = False,
    schema: type[BaseModel] | None = None,
) -> Callable: ...
```

Decorator for registering tool functions.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | Required | Tool name (used in LLM tool calls) |
| `description` | `str` | Required | Tool description (shown to LLM) |
| `requires_permission` | `bool` | `False` | Whether tool requires user approval |
| `schema` | `type[BaseModel] \| None` | `None` | Pydantic schema for argument validation |

## Classes

### `Tool`

```python
@dataclass
class Tool:
    name: str
    description: str
    func: Callable
    schema: type[BaseModel] | None
    requires_permission: bool
    is_enabled: bool = True
```

### `ToolResult`

```python
@dataclass
class ToolResult:
    success: bool
    data: Any | None = None
    error: str | None = None
    execution_time_ms: float = 0.0
```

### `ToolInfo`

```python
@dataclass
class ToolInfo:
    name: str
    description: str
    requires_permission: bool
    is_enabled: bool
    parameter_schema: dict | None
```

## Built-in Tools

| Tool | Description | Permission | Schema |
|------|-------------|------------|--------|
| `read_file` | Read file contents | ✅ (within cwd) | `path: str` |
| `write_file` | Write/overwrite file | ⚠️ (approval) | `path: str, content: str` |
| `execute_command` | Run shell command | ⚠️ (approval) | `command: str, args: list[str]` |
| `web_search` | Search web via Brave | ❌ (disabled by default) | `query: str, num_results: int` |
| `list_directory` | List directory contents | ✅ (within cwd) | `path: str` |
| `create_directory` | Create directory | ✅ (within cwd) | `path: str` |
| `delete_file` | Delete file | ⚠️ (approval) | `path: str` |
| `import_module` | Import Python module | ⚠️ (whitelist) | `module_name: str` |

## Security Controls

### Path Validation

All file operations validate paths against the working directory:

```python
def validate_path(requested: str, base: Path) -> Path:
    """Block path traversal attacks."""
    resolved = (base / requested).resolve()
    if not str(resolved).startswith(str(base.resolve())):
        raise SecurityError(f"Path traversal blocked: {requested}")
    return resolved
```

### Command Execution Sandboxing

| Rule | Implementation |
|------|----------------|
| `shell=False` | No shell interpretation |
| Timeout | 30-second hard limit |
| Dangerous patterns | Blocked (`rm -rf`, `mkfs`, `dd if=`, etc.) |
| Environment | Whitelisted variables only |
| Working directory | Restricted to project `cwd` |

### Module Import Whitelist

Only standard library + approved packages can be imported:

```python
ALLOWED_MODULES = {
    # Standard library
    "os", "sys", "json", "pathlib", "subprocess", "re",
    "datetime", "typing", "collections", "itertools",
    # Approved third-party
    "pydantic", "rich", "typer",
}
```

## Custom Tool Example

```python
from c_e_h.tools import tool, ToolResult
from pydantic import BaseModel, Field

class CalculateSchema(BaseModel):
    expression: str = Field(..., description="Mathematical expression to evaluate")

@tool(
    name="calculate",
    description="Evaluate a mathematical expression",
    requires_permission=False,
    schema=CalculateSchema,
)
def calculate(expression: str) -> ToolResult:
    """Evaluate a math expression safely."""
    try:
        # Only allow math operations
        allowed_names = {
            k: v for k, v in math.__dict__.items()
            if not k.startswith("_")
        }
        result = eval(expression, {"__builtins__": {}}, allowed_names)
        return ToolResult(success=True, data={"result": result})
    except Exception as e:
        return ToolResult(success=False, error=str(e))
```

## Usage Example

```python
from c_e_h.tools import ToolRegistry, ToolResult

# Create registry
registry = ToolRegistry()

# Register a custom tool
@tool(
    name="weather",
    description="Get current weather for a location",
    requires_permission=True,
)
def get_weather(location: str) -> ToolResult:
    # Implementation...
    return ToolResult(success=True, data={"temp": 72, "unit": "F"})

# List available tools
for info in registry.list_tools():
    print(f"{info.name}: {info.description} [{'⚠️' if info.requires_permission else '✅'}]")

# Execute a tool
result = registry.execute("read_file", {"path": "./README.md"})
if result.success:
    print(result.data)
else:
    print(f"Error: {result.error}")

# Validate before executing
if registry.validate("write_file", {"path": "./output.txt", "content": "Hello"}):
    print("Arguments are valid")
```
