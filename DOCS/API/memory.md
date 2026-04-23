# Memory System API

> Three-tier memory architecture for context management and persistence.

## Overview

The [`MemorySystem`](../../src/c_e_h/memory.py) class implements a three-tier memory architecture:

1. **Persistent Memory** — Configuration and long-term instructions stored in `agent.md`
2. **Short-term Memory** — Current session conversation stored in context window + SQLite
3. **Long-term Memory** — Semantic memory across sessions stored in vector database (FAISS)

## Class Definition

```python
class MemorySystem:
    def __init__(
        self,
        persistent_path: str = "agent.md",
        db_path: str = ".ceh_state.db",
        vector_store_path: str | None = None,
        max_context_tokens: int = 8192,
        compaction_strategy: str = "microcompact",
    ) -> None: ...
```

### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `persistent_path` | `str` | `"agent.md"` | Path to persistent config file |
| `db_path` | `str` | `".ceh_state.db"` | Path to SQLite state database |
| `vector_store_path` | `str \| None` | `None` | Path to FAISS vector store (optional) |
| `max_context_tokens` | `int` | `8192` | Maximum context window size |
| `compaction_strategy` | `str` | `"microcompact"` | Context compaction strategy |

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `persistent_config` | `dict` | Current persistent configuration |
| `session_id` | `str` | Current session identifier |
| `context_messages` | `list[dict]` | Current context messages |
| `is_compacting` | `bool` | Whether compaction is in progress |

## Methods

### Persistent Memory

```python
def load_persistent_config(self) -> dict: ...
def save_persistent_config(self, config: dict) -> None: ...
def update_persistent_config(self, updates: dict) -> None: ...
```

| Method | Description |
|--------|-------------|
| `load_persistent_config()` | Load configuration from `agent.md` |
| `save_persistent_config(config)` | Save configuration to `agent.md` |
| `update_persistent_config(updates)` | Merge updates into persistent config |

### Short-term Memory

```python
def add_message(self, role: str, content: str) -> None: ...
def get_context_messages(self) -> list[dict]: ...
def clear_context(self) -> None: ...
def compact_context(self) -> str | None: ...
```

| Method | Description |
|--------|-------------|
| `add_message(role, content)` | Add message to context window |
| `get_context_messages()` | Get all messages in current context |
| `clear_context()` | Clear all messages from context |
| `compact_context()` | Apply compaction strategy; returns summary if `microcompact` |

### Long-term Memory

```python
def store_memory(self, content: str, metadata: dict | None = None) -> str: ...
def search_memories(self, query: str, top_k: int = 5) -> list[MemoryResult]: ...
def delete_memory(self, memory_id: str) -> bool: ...
def list_memories(self, limit: int = 50, offset: int = 0) -> list[MemoryResult]: ...
```

| Method | Description |
|--------|-------------|
| `store_memory(content, metadata)` | Store memory in vector database; returns `memory_id` |
| `search_memories(query, top_k)` | Semantic search; returns ranked results |
| `delete_memory(memory_id)` | Delete a memory by ID |
| `list_memories(limit, offset)` | List memories with pagination |

### Session Management

```python
def create_session(self) -> str: ...
def load_session(self, session_id: str) -> SessionData: ...
def save_session(self, session_id: str, data: SessionData) -> None: ...
def list_sessions(self, limit: int = 20) -> list[SessionSummary]: ...
def delete_session(self, session_id: str) -> bool: ...
```

| Method | Description |
|--------|-------------|
| `create_session()` | Create new session; returns `session_id` |
| `load_session(session_id)` | Load session data |
| `save_session(session_id, data)` | Save session data to SQLite |
| `list_sessions(limit)` | List recent sessions |
| `delete_session(session_id)` | Delete a session |

## Data Classes

### `MemoryResult`

```python
@dataclass
class MemoryResult:
    memory_id: str
    content: str
    score: float
    metadata: dict[str, Any]
    created_at: datetime
```

| Field | Type | Description |
|-------|------|-------------|
| `memory_id` | `str` | Unique memory identifier |
| `content` | `str` | Memory content |
| `score` | `float` | Relevance score (0.0–1.0) |
| `metadata` | `dict[str, Any]` | Associated metadata |
| `created_at` | `datetime` | Creation timestamp |

### `SessionData`

```python
@dataclass
class SessionData:
    session_id: str
    messages: list[dict]
    started_at: datetime
    completed_at: datetime | None = None
    summary: str | None = None
    tool_calls: int = 0
    errors: int = 0
```

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | `str` | Unique session identifier |
| `messages` | `list[dict]` | Conversation messages |
| `started_at` | `datetime` | Session start time |
| `completed_at` | `datetime \| None` | Session end time |
| `summary` | `str \| None` | Auto-generated summary |
| `tool_calls` | `int` | Number of tool calls made |
| `errors` | `int` | Number of errors encountered |

### `SessionSummary`

```python
@dataclass
class SessionSummary:
    session_id: str
    started_at: datetime
    duration_seconds: float | None = None
    message_count: int = 0
    tool_calls: int = 0
    summary: str | None = None
```

## Compaction Strategies

### `snip`

Trims oldest messages when context limit is reached.

```python
# Behavior: removes messages from the beginning of context
# Use case: Simple, fast, no LLM overhead
memory.compact_context()  # Returns None (no summary generated)
```

### `microcompact`

Summarizes trimmed context via LLM call before removing.

```python
# Behavior: sends trimmed messages to LLM for summarization,
#           replaces them with a single summary message
# Use case: Preserves semantic meaning across sessions
summary = memory.compact_context()  # Returns summary string
```

## SQLite Schema

The state database (`.ceh_state.db`) uses the following schema:

```sql
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    started_at INTEGER NOT NULL,
    completed_at INTEGER,
    summary TEXT,
    tool_calls INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0
);

CREATE TABLE context_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE agent_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);
```

## Usage Example

```python
from c_e_h.memory import MemorySystem

# Create memory system
memory = MemorySystem(
    persistent_path="./agent.md",
    db_path=".ceh_state.db",
    vector_store_path="./embeddings/vectorstore",
    max_context_tokens=8192,
    compaction_strategy="microcompact",
)

# Add message to context
memory.add_message("user", "Hello, write me a Python function")
memory.add_message("assistant", "Sure! Here's a function...")

# Search long-term memory
results = memory.search_memories("Python sorting algorithms", top_k=3)
for result in results:
    print(f"[{result.score:.2f}] {result.content[:100]}...")

# Create and save session
session_id = memory.create_session()
memory.save_session(session_id, {
    "messages": memory.get_context_messages(),
    "tool_calls": 5,
    "errors": 0,
})

# Compact context
summary = memory.compact_context()
if summary:
    print(f"Context summarized: {summary[:200]}...")
```
