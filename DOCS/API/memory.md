# Memory System API

> Three-tier memory architecture for context management and persistence.

## Overview

The memory system in C.E.H. implements a three-tier architecture:

1. **Persistent Memory** — Configuration and long-term instructions stored in `agent.md` and SQLite
2. **Short-term Memory** — Current session conversation stored in context window + SQLite with token tracking
3. **Long-term Memory** — Semantic memory across sessions stored in vector database (FAISS or ChromaDB)

The memory system is defined in [`src/c_e_h/memory.py`](../../src/c_e_h/memory.py) and consists of four main classes:

| Class | Lines | Description |
|-------|-------|-------------|
| [`SessionManager`](../../src/c_e_h/memory.py:114) | 114–348 | Manages sessions, steps, and context chunks in SQLite |
| [`ContextManager`](../../src/c_e_h/memory.py:355) | 355–542 | Manages short-term context with token tracking and compaction |
| [`PersistentMemory`](../../src/c_e_h/memory.py:773) | 773–964 | Persistent configuration storage using SQLite and `agent.md` |
| [`MemorySystem`](../../src/c_e_h/memory.py:971) | 971–1112 | Main orchestrator combining all tiers |

## Supporting Data Classes

### `SessionModel`

```python
@dataclass
class SessionModel:
    id: str
    created_at: int
    metadata: Dict[str, Any]
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique session identifier (UUID) |
| `created_at` | `int` | Unix timestamp of creation |
| `metadata` | `Dict[str, Any]` | Arbitrary session metadata |

### `StepModel`

```python
@dataclass
class StepModel:
    id: str
    session_id: str
    step_number: int
    role: str
    content: str
    timestamp: int
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique step identifier (UUID) |
| `session_id` | `str` | Parent session ID |
| `step_number` | `int` | Sequential step number |
| `role` | `str` | Message role (`"user"`, `"assistant"`, `"tool"`) |
| `content` | `str` | Step content |
| `timestamp` | `int` | Unix timestamp |

### `ContextChunkModel`

```python
@dataclass
class ContextChunkModel:
    id: str
    session_id: str
    chunk_type: str
    content: str
    token_count: int
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique chunk identifier (UUID) |
| `session_id` | `str` | Parent session ID |
| `chunk_type` | `str` | Chunk type (`"memory"`, `"instruction"`, `"tool"`) |
| `content` | `str` | Chunk content |
| `token_count` | `int` | Estimated token count |

### `AgentConfig`

```python
class AgentConfig(BaseModel):
    name: str = "CEH-Agent"
    version: str = "0.1.0"
    description: str = "Your local AI assistant"
    model_path: str = "./models/llama-3-8b.Q4_K_M.gguf"
    model_n_gpu_layers: int = -1
    model_n_ctx: int = 8192
    model_temperature: float = 0.7
    max_context_tokens: int = 8192
    compaction_strategy: str = "microcompact"
    permission_mode: str = "autonomous"
    max_auto_errors: int = 3
    success_reset: int = 5
    tools: Dict[str, bool] = field(default_factory=lambda: {
        "file_read": True,
        "file_write": True,
        "execute_command": True,
        "web_search": False,
    })
    log_level: str = "INFO"
    log_format: str = "json"
```

## SessionManager

Manages sessions, steps, and context chunks in SQLite. All database operations use atomic transactions.

**Database path:** `.ceh_state.db` (configurable).

### Constructor

```python
def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `db_path` | `str` | `DEFAULT_DB_PATH` | Path to SQLite database |

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `create_session` | `(metadata: Optional[Dict[str, Any]] = None) -> str` | Create a new session and return its ID |
| `get_session` | `(session_id: str) -> Optional[SessionModel]` | Retrieve a session by ID |
| `delete_session` | `(session_id: str) -> bool` | Delete a session and all its steps and chunks atomically |
| `add_step` | `(session_id: str, step_number: int, role: str, content: str) -> str` | Add a step to a session atomically. Returns step ID |
| `get_steps` | `(session_id: str) -> List[StepModel]` | Retrieve all steps for a session ordered by step_number |
| `add_context_chunk` | `(session_id: str, chunk_type: str, content: str, token_count: int) -> str` | Add a context chunk atomically. Returns chunk ID |
| `get_context_chunks` | `(session_id: str) -> List[ContextChunkModel]` | Retrieve all context chunks for a session |
| `delete_context_chunks` | `(session_id: str) -> int` | Delete all context chunks for a session. Returns count deleted |
| `get_eligible_chunks_for_compaction` | `(session_id: str) -> List[ContextChunkModel]` | Return only memory and tool chunks (NOT instruction) for compaction |
| `replace_chunks` | `(session_id: str, new_chunks: List[ContextChunkModel]) -> None` | Atomically replace all context chunks for a session |
| `save_full_state` | `(session_id: str, state: Dict[str, Any]) -> None` | Save full agent state as a context chunk under session |
| `restore_full_state` | `(session_id: str) -> Optional[Dict[str, Any]]` | Restore full agent state from the latest memory chunk |

### SQLite Schema

```sql
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    created_at INTEGER,
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS steps (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    step_number INTEGER,
    role TEXT,
    content TEXT,
    timestamp INTEGER,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS context_chunks (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    chunk_type TEXT,
    content TEXT,
    token_count INTEGER,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
```

## ContextManager

Manages short-term context with token tracking and compaction.

**Strategies:**
- **`snip`**: trim oldest eligible context when limit exceeded.
- **`microcompact`**: summarize trimmed context via LLM call.

**System prompt protection:** chunks with `chunk_type="instruction"` are NEVER trimmed or summarized during compaction.

### Constructor

```python
def __init__(
    self,
    session_manager: SessionManager,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    strategy: str = "microcompact",
    llm_summarize_callback: Optional[callable] = None,
) -> None
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session_manager` | `SessionManager` | Required | Session manager for data access |
| `max_tokens` | `int` | `DEFAULT_MAX_TOKENS` | Maximum token count before compaction |
| `strategy` | `str` | `"microcompact"` | Compaction strategy |
| `llm_summarize_callback` | `Optional[callable]` | `None` | LLM callback for summarization |

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `add_message` | `(session_id: str, role: str, content: str, chunk_type: str = CHUNK_TYPE_MEMORY) -> str` | Add a message to context. Returns chunk ID |
| `add_instruction` | `(session_id: str, content: str) -> str` | Add a protected instruction chunk (system prompt, identity) |
| `add_tool_output` | `(session_id: str, content: str) -> str` | Add a tool output chunk |
| `get_context` | `(session_id: str) -> List[ContextChunkModel]` | Return all context chunks for the session |
| `get_context_text` | `(session_id: str) -> str` | Return concatenated context text (all chunk types) |
| `get_total_token_count` | `(session_id: str) -> int` | Return total token count for all chunks in the session |
| `clear_context` | `(session_id: str) -> int` | Clear all context chunks. Returns count deleted |
| `compact` | `(session_id: str) -> None` | Compact context using the configured strategy |

### Compaction Strategies

#### `snip`

Removes oldest eligible chunks until context is under the token threshold. Instruction chunks are preserved.

```python
# Behavior: removes messages from the beginning of eligible context
# Use case: Simple, fast, no LLM overhead
memory.compact_context()  # Returns None (no summary generated)
```

#### `microcompact`

Summarizes oldest eligible chunks via LLM call, replacing them with a single summary message. Falls back to `snip` if no LLM callback is configured.

```python
# Behavior: sends trimmed messages to LLM for summarization,
#           replaces them with a single summary message
# Use case: Preserves semantic meaning across sessions
summary = memory.compact_context()  # Returns summary string
```

## Vector Database Interfaces

### `VectorDBInterface` (Abstract)

```python
class VectorDBInterface(abc.ABC):
    """Abstract interface for vector database backends."""

    @abc.abstractmethod
    def add_documents(
        self, documents: List[str], metadatas: Optional[List[Dict[str, Any]]] = None
    ) -> List[str]: ...

    @abc.abstractmethod
    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]: ...
```

### `FAISSAdapter`

FAISS-based vector store adapter.

```python
class FAISSAdapter(VectorDBInterface):
    def __init__(self, dim: int = 768, index_type: str = "Flat") -> None
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `dim` | `int` | `768` | Embedding dimension |
| `index_type` | `str` | `"Flat"` | FAISS index type |

**Methods:**

| Method | Description |
|--------|-------------|
| `add_documents(documents, metadatas)` | Add documents to FAISS index |
| `search(query, top_k)` | Semantic search; returns ranked results |
| `delete(ids)` | Delete documents by ID |

### `ChromaDBAdapter`

ChromaDB-based vector store adapter.

```python
class ChromaDBAdapter(VectorDBInterface):
    def __init__(
        self,
        collection_name: str = "ceh_memory",
        persist_path: Optional[str] = None
    ) -> None
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `collection_name` | `str` | `"ceh_memory"` | ChromaDB collection name |
| `persist_path` | `Optional[str]` | `None` | Persistent storage path |

**Methods:**

| Method | Description |
|--------|-------------|
| `add_documents(documents, metadatas)` | Add documents to ChromaDB collection |
| `search(query, top_k)` | Semantic search; returns ranked results |
| `delete(ids)` | Delete documents by ID |
| `close()` | Close ChromaDB client |

## PersistentMemory

Persistent configuration storage using SQLite and `agent.md`.

### Constructor

```python
def __init__(self, db_path: str = DEFAULT_DB_PATH, agent_md_path: str = "agent.md") -> None
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `db_path` | `str` | `DEFAULT_DB_PATH` | Path to SQLite database |
| `agent_md_path` | `str` | `"agent.md"` | Path to agent configuration file |

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `load_config` | `() -> AgentConfig` | Load agent configuration from `agent.md` |
| `save_config` | `(config: AgentConfig) -> None` | Save agent configuration to `agent.md` and SQLite |
| `get` | `(key: str) -> Optional[str]` | Retrieve a config value by key from SQLite |
| `set` | `(key: str, value: str) -> None` | Store a config value by key in SQLite |

## MemorySystem

Main orchestrator for the 3-tier memory system. Combines `PersistentMemory`, `ContextManager`, and `VectorDBInterface` into a unified API.

### Constructor

```python
def __init__(
    self,
    db_path: str = DEFAULT_DB_PATH,
    agent_md_path: str = "agent.md",
    max_tokens: int = DEFAULT_MAX_TOKENS,
    strategy: str = "microcompact",
    vector_db: Optional[VectorDBInterface] = None,
    llm_summarize_callback: Optional[callable] = None,
) -> None
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `db_path` | `str` | `DEFAULT_DB_PATH` | Path to SQLite database |
| `agent_md_path` | `str` | `"agent.md"` | Path to agent configuration file |
| `max_tokens` | `int` | `DEFAULT_MAX_TOKENS` | Maximum token count before compaction |
| `strategy` | `str` | `"microcompact"` | Compaction strategy |
| `vector_db` | `Optional[VectorDBInterface]` | `None` | Optional vector database backend |
| `llm_summarize_callback` | `Optional[callable]` | `None` | LLM callback for summarization |

### Methods

#### Persistent Memory

| Method | Signature | Description |
|--------|-----------|-------------|
| `load_config` | `() -> AgentConfig` | Load agent configuration from `agent.md` |
| `save_config` | `(config: AgentConfig) -> None` | Save agent configuration to `agent.md` and SQLite |

#### Session Management

| Method | Signature | Description |
|--------|-----------|-------------|
| `create_session` | `(metadata: Optional[Dict[str, Any]] = None) -> str` | Create a new session and return its ID |
| `get_session` | `(session_id: str) -> Optional[SessionModel]` | Retrieve a session by ID |
| `delete_session` | `(session_id: str) -> bool` | Delete a session and all its data |

#### Context Management

| Method | Signature | Description |
|--------|-----------|-------------|
| `add_message` | `(session_id: str, role: str, content: str, chunk_type: str = CHUNK_TYPE_MEMORY) -> str` | Add a message to context |
| `add_instruction` | `(session_id: str, content: str) -> str` | Add a protected instruction chunk |
| `add_tool_output` | `(session_id: str, content: str, chunk_type: str = CHUNK_TYPE_TOOL) -> str` | Add a tool output chunk |
| `get_context` | `(session_id: str) -> List[ContextChunkModel]` | Return all context chunks |
| `get_context_text` | `(session_id: str) -> str` | Return concatenated context text |
| `get_total_token_count` | `(session_id: str) -> int` | Return total token count |
| `compact_context` | `(session_id: str) -> None` | Manually trigger context compaction |
| `clear_context` | `(session_id: str) -> int` | Clear all context chunks |

#### Vector DB

| Method | Signature | Description |
|--------|-----------|-------------|
| `store_in_vector_db` | `(documents: List[str], metadatas: Optional[List[Dict[str, Any]]] = None) -> List[str]` | Store documents in the vector DB (optional) |
| `search_vector_db` | `(query: str, top_k: int = 5) -> List[Dict[str, Any]]` | Search the vector DB (optional) |

#### State Persistence

| Method | Signature | Description |
|--------|-----------|-------------|
| `save_full_state` | `(session_id: str, state: Dict[str, Any]) -> None` | Save full agent state to SQLite |
| `restore_full_state` | `(session_id: str) -> Optional[Dict[str, Any]]` | Restore full agent state from SQLite |

#### Steps Management

| Method | Signature | Description |
|--------|-----------|-------------|
| `add_step` | `(session_id: str, step_number: int, role: str, content: str) -> str` | Add a step to a session |
| `get_steps` | `(session_id: str) -> List[StepModel]` | Retrieve all steps for a session |

## Usage Example

```python
from c_e_h.memory import MemorySystem, SessionManager, ContextManager

# Create memory system
memory = MemorySystem(
    db_path=".ceh_state.db",
    agent_md_path="./agent.md",
    max_tokens=8192,
    strategy="microcompact",
)

# Create a session
session_id = memory.create_session(metadata={"model": "llama-3-8b"})

# Add messages to context
memory.add_message(session_id, "user", "Hello, write me a Python function")
memory.add_message(session_id, "assistant", "Sure! Here's a function...")

# Add a protected instruction (system prompt)
memory.add_instruction(session_id, "You are a helpful coding assistant.")

# Add tool output
memory.add_tool_output(session_id, "read_file returned: def hello(): pass")

# Get context
context = memory.get_context(session_id)
for chunk in context:
    print(f"[{chunk.chunk_type}] tokens={chunk.token_count}: {chunk.content[:50]}...")

# Compact context
memory.compact_context(session_id)

# Save full state
memory.save_full_state(session_id, {"config": "value"})

# Restore state
restored = memory.restore_full_state(session_id)

# Vector DB (optional)
if memory.vector_db:
    memory.store_in_vector_db(["Python sorting", "JavaScript sorting"])
    results = memory.search_vector_db("Python sorting", top_k=3)
```
