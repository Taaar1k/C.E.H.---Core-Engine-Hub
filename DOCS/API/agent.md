# Agent Class API

> Core agent class, task loop, and lifecycle management.

## Overview

The [`Agent`](../../src/c_e_h/agent.py) class is the central orchestrator of C.E.H. It manages the task loop, context window, decision-making, and error handling.

## Class Definition

```python
class Agent:
    MAX_RETRIES: int = 3
    BASE_RETRY_DELAY: float = 1.0

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        display_mode: Literal["clean", "streaming"] = "clean",
    ) -> None: ...

    @classmethod
    def from_agent_md(cls, path: str = "agent.md") -> "Agent": ...
```

The [`Agent`](../../src/c_e_h/agent.py) class is the central orchestrator of C.E.H. It manages the task loop, context window, decision-making, and error handling. The LLM backend is lazy-loaded on first use via [`_ensure_backend()`](src/c_e_h/agent.py:340).

### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | [`AgentConfig`] | `None` | Agent configuration (auto-created if `None`) |
| `display_mode` | `Literal["clean", "streaming"]` | `"clean"` | Output display mode |

### Class Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `MAX_RETRIES` | `int` | `3` | Maximum retry attempts for failed generations |
| `BASE_RETRY_DELAY` | `float` | `1.0` | Base delay in seconds between retries |

### Static Methods

| Method | Returns | Description |
|--------|---------|-------------|
| [`from_agent_md(path)`](src/c_e_h/agent.py:142) | `Agent` | Load configuration from `agent.md` YAML file |
| [`_parse_config(data)`](src/c_e_h/agent.py:165) | `AgentConfig` | Parse raw config dictionary into `AgentConfig` |

## Properties

| Attribute | Type | Description |
|-----------|------|-------------|
| [`config`](#config) | [`AgentConfig`] | Agent configuration |
| [`state`](#state) | [`AgentState`] | Current agent state dataclass |
| [`display_mode`](#display_mode) | `Literal["clean", "streaming"]` | Output display mode |

### `config`

```python
@property
def config(self) -> AgentConfig: ...
```

Returns the [`AgentConfig`](#agentconfig) instance containing model path, GPU layers, context size, and other settings.

### `state`

```python
@property
def state(self) -> AgentState: ...
```

Returns the current [`AgentState`](#agentstate) dataclass with session metadata.

### `display_mode`

```python
@property
def display_mode(self) -> Literal["clean", "streaming"]: ...
```

Returns the output display mode. `"clean"` shows only the final response with a spinner; `"streaming"` shows tokens as they arrive.

## Methods

## Methods

### `run()`

```python
def run(self, prompt: str) -> str: ...
```

Execute one step of the agent loop with retry logic. This is the primary entry point for agent interaction.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `prompt` | `str` | User prompt to process |

**Returns:** `str` — The agent's generated response text.

**Implementation:** Calls [`_generate_response_with_retry_clean()`](src/c_e_h/agent.py:255) with up to `MAX_RETRIES` (3) attempts, using `BASE_RETRY_DELAY` (1.0s) between retries.

---

### `_ensure_backend()`

```python
def _ensure_backend(self) -> None: ...
```

Lazy-load and initialize [`LlamaBackend`](llama_backend.md) if not already loaded. Called automatically before first inference.

---

### `_generate_response_with_retry_clean(prompt: str) -> str`

Generate response with clean retry logic. Called by `run()`.

---

### `_generate_response(prompt: str) -> str`

Generate response by calling LLM backend. Handles context overflow detection.

---

### `_estimate_tokens(text: str) -> int`

Estimate token count from text (rough approximation: ~4 chars per token).

---

### `save_state() -> Dict[str, Any]`

Save current agent state (timestamps, metadata) to dictionary.

---

### `load_state(data: Dict[str, Any]) -> None`

Restore agent state from a previously saved dictionary.

---

### `get_state_json() -> str`

Get agent state as a JSON string for serialization.

---

### `load_state_json(json_str: str) -> "Agent"`

Class method to create an `Agent` instance from a JSON string.

---

### `from_agent_md(path: str = "agent.md") -> "Agent"`

Class method to load configuration from `agent.md` YAML file and create an `Agent` instance.

## Data Classes

### `AgentConfig`

```python
class AgentConfig(BaseModel):
    """Agent configuration loaded from agent.md."""
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | `"CEH-Agent"` | Agent display name |
| `version` | `str` | `"0.1.0"` | Agent version |
| `description` | `str` | `"Your local AI assistant"` | Agent description |
| `model_path` | `str` | `"./models/llama-3-8b.Q4_K_M.gguf"` | Default GGUF model path |
| `n_gpu_layers` | `int` | `-1` | GPU offload layers (`-1` = all) |
| `n_ctx` | `int` | `8192` | Context window size |
| `temperature` | `float` | `0.7` | Sampling temperature |
| `max_context_tokens` | `int` | `8192` | Maximum context tokens |
| `compaction_strategy` | `str` | `"microcompact"` | Context compaction strategy |
| `permission_mode` | `str` | `"autonomous"` | Default permission mode |
| `max_auto_errors` | `int` | `3` | Errors before permission degradation |
| `success_reset` | `int` | `5` | Successes before permission reset |
| `tools` | `Dict[str, bool]` | `{file_read: True, file_write: True, execute_command: True, web_search: False}` | Tool enablement flags |
| `log_level` | `str` | `"INFO"` | Logging verbosity |
| `log_format` | `str` | `"json"` | Log format |
| `models_directory` | `Optional[str]` | `None` | Default model scan directory |
| `default_profile` | `Optional[str]` | `None` | Default profile name from `profiles.yaml` |

### `AgentState`

```python
@dataclass
class AgentState:
    """Represents the current state of the agent."""
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `step_count` | `int` | `0` | Current step count in agent loop |
| `mode` | `str` | `"autonomous"` | Current permission mode |
| `auto_errors` | `int` | `0` | Consecutive error count |
| `context` | `List[Dict[str, Any]]` | `[]` | Conversation context |
| `last_response` | `Optional[str]` | `None` | Last generated response |
| `started_at` | `Optional[str]` | `None` | ISO-8601 start timestamp |

| Method | Returns | Description |
|--------|---------|-------------|
| [`to_dict()`](src/c_e_h/agent.py:85) | `Dict[str, Any]` | Serialize state to dictionary |
| [`from_dict(data)`](src/c_e_h/agent.py:90) | `AgentState` | Restore state from dictionary |

## Usage Example

```python
from c_e_h.agent import Agent, AgentConfig

# Create agent with default config
agent = Agent()

# Create agent with custom config
config = AgentConfig(
    name="MyAgent",
    model_path="./models/my-model.gguf",
    n_gpu_layers=32,
    temperature=0.5,
)
agent = Agent(config=config)

# Load from agent.md
agent = Agent.from_agent_md("agent.md")

# Single-shot run
response = agent.run("Write a Python function to calculate Fibonacci numbers")
print(response)

# Check state
print(f"Agent state: {agent.state}")
print(f"Step count: {agent.state.step_count}")
print(f"Permission mode: {agent.state.mode}")
```
