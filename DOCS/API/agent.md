# Agent Class API

> Core agent class, task loop, and lifecycle management.

## Overview

The [`Agent`](../../src/c_e_h/agent.py) class is the central orchestrator of C.E.H. It manages the task loop, context window, decision-making, and error handling.

## Class Definition

```python
class Agent:
    def __init__(
        self,
        model_path: str,
        config: dict | None = None,
        memory: MemorySystem | None = None,
        tools: ToolRegistry | None = None,
        llama_backend: LlamaBackend | None = None,
    ) -> None: ...
```

### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model_path` | `str` | Required | Path to GGUF model file |
| `config` | `dict \| None` | `None` | Agent configuration dictionary |
| `memory` | `MemorySystem \| None` | `None` | Memory system instance (auto-created if `None`) |
| `tools` | `ToolRegistry \| None` | `None` | Tool registry instance (auto-created if `None`) |
| `llama_backend` | `LlamaBackend \| None` | `None` | LLM backend instance (auto-created if `None`) |

## Properties

| Property | Type | Description |
|----------|------|-------------|
| [`agent_id`](#agent_id) | `str` | Unique identifier for this agent instance |
| [`permissions`](#permissions) | `PermissionManager` | Permission management object |
| [`memory`](#memory) | `MemorySystem` | Memory system reference |
| [`tools`](#tools) | `ToolRegistry` | Tool registry reference |
| [`llama_backend`](#llama_backend) | `LlamaBackend` | LLM backend reference |
| [`context_window`](#context_window) | `ContextWindow` | Active context window manager |
| [`state`](#state) | `AgentState` | Current agent state enum |

### `agent_id`

```python
@property
def agent_id(self) -> str: ...
```

Returns a UUID v4 string identifying this agent instance. Persisted across restarts if the same config is used.

### `permissions`

```python
@property
def permissions(self) -> PermissionManager: ...
```

Returns the [`PermissionManager`](#permissionmanager) instance controlling tool execution permissions.

### `memory`

```python
@property
def memory(self) -> MemorySystem: ...
```

Returns the [`MemorySystem`](memory.md) instance for context and session management.

### `tools`

```python
@property
def tools(self) -> ToolRegistry: ...
```

Returns the [`ToolRegistry`](tools.md) instance for tool management.

### `llama_backend`

```python
@property
def llama_backend(self) -> LlamaBackend: ...
```

Returns the [`LlamaBackend`](llama_backend.md) instance for LLM inference.

### `context_window`

```python
@property
def context_window(self) -> ContextWindow: ...
```

Returns the active [`ContextWindow`](#contextwindow) managing conversation history and compaction.

### `state`

```python
@property
def state(self) -> AgentState: ...
```

Returns the current [`AgentState`](#agentstate) enum value.

## Methods

### `run()`

```python
def run(self, prompt: str) -> AgentResponse: ...
```

Execute a single-shot agent run with the given prompt.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `prompt` | `str` | User prompt to process |

**Returns:** [`AgentResponse`](#agentresponse) with the agent's output.

**Raises:**

| Exception | Condition |
|-----------|-----------|
| `RuntimeError` | If agent is not initialized |
| `ContextFullError` | If context window is full and compaction fails |

---

### `run_loop()`

```python
def run_loop(self, prompt: str) -> list[AgentResponse]: ...
```

Execute the full agent task loop (multi-step reasoning with tool use).

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `prompt` | `str` | Initial user prompt |

**Returns:** List of [`AgentResponse`](#agentresponse) objects, one per loop iteration.

**Loop Behavior:**

1. Send prompt to LLM
2. Parse LLM output for tool calls or final response
3. If tool call: execute tool, add result to context, repeat
4. If final response: return result
5. Stop if max iterations reached or context full

---

### `record_error()`

```python
def record_error(self) -> None: ...
```

Record a tool execution error. Increments error counter and may trigger permission degradation.

---

### `record_success()`

```python
def record_success(self) -> None: ...
```

Record a successful tool execution. May reset permission mode if success threshold reached.

---

### `reset_context()`

```python
def reset_context(self) -> None: ...
```

Reset the context window to empty, clearing conversation history.

---

### `save_state()`

```python
def save_state(self) -> None: ...
```

Persist agent state (permissions, error count, session ID) to SQLite database.

---

### `load_state()`

```python
def load_state(self) -> None: ...
```

Restore agent state from SQLite database.

## Enums

### `AgentState`

```python
class AgentState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING_FOR_INPUT = "waiting_for_input"
    ERROR = "error"
    SHUTDOWN = "shutdown"
```

## Data Classes

### `AgentResponse`

```python
@dataclass
class AgentResponse:
    text: str
    tool_calls: list[ToolCall] | None = None
    is_final: bool = False
    iteration: int = 0
    error: str | None = None
```

| Field | Type | Description |
|-------|------|-------------|
| `text` | `str` | Response text |
| `tool_calls` | `list[ToolCall] \| None` | Tool calls made in this iteration |
| `is_final` | `bool` | Whether this is the final response |
| `iteration` | `int` | Loop iteration number |
| `error` | `str \| None` | Error message if failed |

### `ToolCall`

```python
@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    call_id: str
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Tool name |
| `arguments` | `dict[str, Any]` | Tool arguments |
| `call_id` | `str` | Unique call identifier |

## PermissionManager

```python
class PermissionManager:
    def __init__(self, config: dict) -> None: ...

    @property
    def mode(self) -> PermissionMode: ...

    def request_permission(self, tool_name: str, args: dict) -> bool: ...
    def grant_permission(self, tool_name: str) -> None: ...
    def revoke_permission(self, tool_name: str) -> None: ...
    def degrade_to_approval(self) -> None: ...
    def reset_to_autonomous(self) -> None: ...
```

### `PermissionMode` Enum

```python
class PermissionMode(Enum):
    AUTONOMOUS = "autonomous"
    APPROVAL = "approval"
```

## ContextWindow

```python
class ContextWindow:
    def __init__(self, max_tokens: int, strategy: str) -> None: ...

    @property
    def current_tokens(self) -> int: ...
    @property
    def is_full(self) -> bool: ...

    def add_message(self, role: str, content: str) -> None: ...
    def compact(self) -> str | None: ...
    def clear(self) -> None: ...
    def get_messages(self) -> list[dict]: ...
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_tokens` | `int` | Required | Maximum token capacity |
| `strategy` | `str` | Required | Compaction strategy (`snip` or `microcompact`) |

## Usage Example

```python
from c_e_h.agent import Agent
from c_e_h.memory import MemorySystem
from c_e_h.tools import ToolRegistry

# Create agent with defaults
agent = Agent(model_path="./models/llama-3-8b.Q4_K_M.gguf")

# Single-shot run
response = agent.run("Write a Python function to calculate Fibonacci numbers")
print(response.text)

# Multi-step run
responses = agent.run_loop("Refactor this code to use async/await")
for i, resp in enumerate(responses):
    print(f"Iteration {i}: {resp.text[:100]}...")

# Check state
print(f"Agent state: {agent.state}")
print(f"Permission mode: {agent.permissions.mode}")
print(f"Context usage: {agent.context_window.current_tokens}/{8192}")
```
