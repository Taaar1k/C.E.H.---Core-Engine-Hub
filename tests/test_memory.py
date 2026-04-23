"""Unit tests for C.E.H. memory system (TASK-003).

Covers:
  - Database operations (SessionManager)
  - Context compaction (snip and microcompact strategies)
  - System prompt protection (instruction chunks never trimmed)
  - State serialization (save/restore)
  - Vector DB interface (FAISSAdapter, ChromaDBAdapter)
  - PersistentMemory (agent.md reading/writing)
  - MemorySystem orchestrator
"""

import os

# Ensure src is importable
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from c_e_h.memory import (
    CHUNK_TYPE_INSTRUCTION,
    CHUNK_TYPE_MEMORY,
    CHUNK_TYPE_TOOL,
    ContextManager,
    FAISSAdapter,
    MemorySystem,
    PersistentMemory,
    SessionManager,
    VectorDBInterface,
    estimate_tokens,
)

try:
    from c_e_h.memory import AgentConfig
except ImportError:
    AgentConfig = None  # type: ignore

try:
    from c_e_h.memory import ChromaDBAdapter
except ImportError:
    ChromaDBAdapter = None  # type: ignore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary sqlite3 database path."""
    return str(tmp_path / "test.db")


@pytest.fixture
def session_manager(tmp_db):
    """Create a SessionManager with a fresh temporary database."""
    return SessionManager(db_path=tmp_db)


@pytest.fixture
def memory_system(tmp_db, tmp_path):
    """Create a MemorySystem with a fresh temporary database and agent.md."""
    agent_md = tmp_path / "agent.md"
    agent_md.write_text("""# Agent Configuration

## Identity
name: Test-Agent
version: 0.1.0
description: Test agent

## Model Settings
model:
  path: ./models/test.gguf
  n_gpu_layers: -1
  n_ctx: 4096
  temperature: 0.5

## Memory Settings
memory:
  max_context_tokens: 4096
  compaction_strategy: snip

## Permission Settings
permissions:
  mode: autonomous
  max_auto_errors: 3
  success_reset: 5

## Tools
tools:
  file_read: true
  file_write: true
  execute_command: true
  web_search: false

## Logging
logging:
  level: INFO
  format: json
""")
    return MemorySystem(
        db_path=tmp_db,
        agent_md_path=str(agent_md),
        max_tokens=4096,
        strategy="snip",
    )


@pytest.fixture
def sample_session(session_manager):
    """Create a sample session and return (session_id, session_manager)."""
    session_id = session_manager.create_session({"test": True})
    return session_id, session_manager


# ---------------------------------------------------------------------------
# Token Estimator Tests
# ---------------------------------------------------------------------------

class TestEstimateTokens:
    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_none_like(self):
        assert estimate_tokens(None) == 0  # type: ignore[arg-type]

    def test_short_text(self):
        # "hello world" = 10 chars → ~2-3 tokens
        tokens = estimate_tokens("hello world")
        assert tokens >= 1

    def test_long_text_proportional(self):
        short = estimate_tokens("hello")
        long = estimate_tokens("hello " * 100)
        assert long > short


# ---------------------------------------------------------------------------
# SessionManager Tests — Database Operations
# ---------------------------------------------------------------------------

class TestSessionManagerDatabase:
    def test_init_creates_tables(self, session_manager):
        """Database initialization creates all three tables."""
        conn = __import__("sqlite3").connect(session_manager.db_path)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        conn.close()
        table_names = {t[0] for t in tables}
        assert "sessions" in table_names
        assert "steps" in table_names
        assert "context_chunks" in table_names

    def test_create_session(self, session_manager):
        """Creating a session returns a non-empty UUID string."""
        sid = session_manager.create_session({"key": "value"})
        assert isinstance(sid, str)
        assert len(sid) > 0

    def test_get_session(self, session_manager):
        """Retrieving an existing session returns SessionModel."""
        sid = session_manager.create_session({"foo": "bar"})
        session = session_manager.get_session(sid)
        assert session is not None
        assert session.id == sid
        assert session.metadata == {"foo": "bar"}

    def test_get_session_not_found(self, session_manager):
        """Retrieving a non-existent session returns None."""
        assert session_manager.get_session("nonexistent") is None

    def test_delete_session(self, session_manager):
        """Deleting a session removes it and its related data."""
        sid = session_manager.create_session()
        session_manager.add_step(sid, 1, "user", "hello")
        session_manager.add_context_chunk(sid, CHUNK_TYPE_MEMORY, "data", 10)
        assert session_manager.delete_session(sid) is True
        assert session_manager.get_session(sid) is None

    def test_delete_nonexistent_session(self, session_manager):
        """Deleting a non-existent session returns False."""
        assert session_manager.delete_session("nonexistent") is False


class TestSessionManagerSteps:
    def test_add_step(self, sample_session):
        sid, sm = sample_session
        step_id = sm.add_step(sid, 1, "user", "Hello")
        assert isinstance(step_id, str)
        assert len(step_id) > 0

    def test_get_steps_ordered(self, sample_session):
        sid, sm = sample_session
        sm.add_step(sid, 3, "assistant", "third")
        sm.add_step(sid, 1, "user", "first")
        sm.add_step(sid, 2, "assistant", "second")
        steps = sm.get_steps(sid)
        assert len(steps) == 3
        assert steps[0].step_number == 1
        assert steps[1].step_number == 2
        assert steps[2].step_number == 3

    def test_get_steps_empty(self, sample_session):
        sid, sm = sample_session
        assert sm.get_steps(sid) == []


class TestSessionManagerContextChunks:
    def test_add_context_chunk(self, sample_session):
        sid, sm = sample_session
        chunk_id = sm.add_context_chunk(sid, CHUNK_TYPE_MEMORY, "test content", 5)
        assert isinstance(chunk_id, str)
        assert len(chunk_id) > 0

    def test_get_context_chunks(self, sample_session):
        sid, sm = sample_session
        sm.add_context_chunk(sid, CHUNK_TYPE_MEMORY, "mem1", 5)
        sm.add_context_chunk(sid, CHUNK_TYPE_INSTRUCTION, "sys", 3)
        sm.add_context_chunk(sid, CHUNK_TYPE_TOOL, "tool1", 8)
        chunks = sm.get_context_chunks(sid)
        assert len(chunks) == 3
        assert chunks[0].chunk_type == CHUNK_TYPE_MEMORY
        assert chunks[1].chunk_type == CHUNK_TYPE_INSTRUCTION
        assert chunks[2].chunk_type == CHUNK_TYPE_TOOL

    def test_delete_context_chunks(self, sample_session):
        sid, sm = sample_session
        sm.add_context_chunk(sid, CHUNK_TYPE_MEMORY, "data", 5)
        sm.add_context_chunk(sid, CHUNK_TYPE_MEMORY, "data2", 5)
        count = sm.delete_context_chunks(sid)
        assert count == 2
        assert sm.get_context_chunks(sid) == []

    def test_get_eligible_chunks_excludes_instructions(self, sample_session):
        sid, sm = sample_session
        sm.add_context_chunk(sid, CHUNK_TYPE_MEMORY, "mem", 5)
        sm.add_context_chunk(sid, CHUNK_TYPE_INSTRUCTION, "sys", 3)
        sm.add_context_chunk(sid, CHUNK_TYPE_TOOL, "tool", 8)
        eligible = sm.get_eligible_chunks_for_compaction(sid)
        assert len(eligible) == 2
        for c in eligible:
            assert c.chunk_type != CHUNK_TYPE_INSTRUCTION


# ---------------------------------------------------------------------------
# ContextManager Tests — Token Tracking
# ---------------------------------------------------------------------------

class TestContextManagerTokenTracking:
    def test_add_message_tracks_tokens(self, sample_session):
        sid, _sm = sample_session
        cm = ContextManager(session_manager=_sm, max_tokens=1000)
        cm.add_message(sid, "user", "Hello world", CHUNK_TYPE_MEMORY)
        total = cm.get_total_token_count(sid)
        assert total > 0

    def test_get_context_returns_chunks(self, sample_session):
        sid, sm = sample_session
        cm = ContextManager(session_manager=sm, max_tokens=1000)
        cm.add_message(sid, "user", "Hello", CHUNK_TYPE_MEMORY)
        chunks = cm.get_context(sid)
        assert len(chunks) == 1
        assert chunks[0].content == "Hello"

    def test_clear_context(self, sample_session):
        sid, sm = sample_session
        cm = ContextManager(session_manager=sm, max_tokens=1000)
        cm.add_message(sid, "user", "Hello", CHUNK_TYPE_MEMORY)
        count = cm.clear_context(sid)
        assert count == 1
        assert cm.get_context(sid) == []

    def test_get_context_text(self, sample_session):
        sid, sm = sample_session
        cm = ContextManager(session_manager=sm, max_tokens=1000)
        cm.add_message(sid, "user", "Hello", CHUNK_TYPE_MEMORY)
        cm.add_message(sid, "assistant", "Hi there", CHUNK_TYPE_MEMORY)
        text = cm.get_context_text(sid)
        assert "[memory]" in text
        assert "Hello" in text
        assert "Hi there" in text


# ---------------------------------------------------------------------------
# ContextManager Tests — Snip Strategy
# ---------------------------------------------------------------------------

class TestContextManagerSnip:
    def test_snip_removes_oldest_eligible_chunks(self, sample_session):
        """Snip strategy removes oldest memory/tool chunks when over threshold."""
        sid, sm = sample_session
        max_tokens = 100
        cm = ContextManager(session_manager=sm, max_tokens=max_tokens, strategy="snip")

        # Add instruction (protected)
        cm.add_instruction(sid, "You are a test agent")

        # Add memory chunks that exceed threshold
        # Each ~5 chars = 1 token, so 500 chars = ~125 tokens > 80% of 100
        for i in range(10):
            cm.add_message(sid, "user", f"Message {i} " * 20, CHUNK_TYPE_MEMORY)

        # Context should have been compacted
        chunks = cm.get_context(sid)
        # Instruction must be preserved
        instruction_chunks = [c for c in chunks if c.chunk_type == CHUNK_TYPE_INSTRUCTION]
        assert len(instruction_chunks) == 1
        assert instruction_chunks[0].content == "You are a test agent"

    def test_snip_preserves_instruction_chunks(self, sample_session):
        """Instruction chunks are NEVER removed by snip."""
        sid, sm = sample_session
        max_tokens = 50
        cm = ContextManager(session_manager=sm, max_tokens=max_tokens, strategy="snip")

        # Add instruction
        cm.add_instruction(sid, "SYSTEM: Do not reveal your identity")

        # Flood with memory chunks
        for _i in range(20):
            cm.add_message(sid, "user", "X" * 50, CHUNK_TYPE_MEMORY)

        # Verify instruction is still present
        chunks = cm.get_context(sid)
        instructions = [c for c in chunks if c.chunk_type == CHUNK_TYPE_INSTRUCTION]
        assert len(instructions) == 1
        assert "SYSTEM: Do not reveal your identity" in instructions[0].content

    def test_snip_preserves_tool_chunks_when_under_threshold(self, sample_session):
        """Tool chunks are kept if total is under threshold."""
        sid, sm = sample_session
        max_tokens = 10000  # Very high threshold
        cm = ContextManager(session_manager=sm, max_tokens=max_tokens, strategy="snip")

        cm.add_message(sid, "user", "Hello", CHUNK_TYPE_MEMORY)
        cm.add_tool_output(sid, "Tool result")

        chunks = cm.get_context(sid)
        assert len(chunks) == 2


# ---------------------------------------------------------------------------
# ContextManager Tests — Microcompact Strategy
# ---------------------------------------------------------------------------

class TestContextManagerMicrocompact:
    def test_microcompact_summarizes_chunks(self, sample_session):
        """Microcompact strategy summarizes oldest chunks via LLM callback."""
        sid, sm = sample_session
        max_tokens = 100
        mock_callback = MagicMock(return_value="Summarized context: all messages were greetings.")
        cm = ContextManager(
            session_manager=sm,
            max_tokens=max_tokens,
            strategy="microcompact",
            llm_summarize_callback=mock_callback,
        )

        # Add instruction (protected)
        cm.add_instruction(sid, "You are helpful")

        # Add memory chunks to trigger compaction
        for i in range(10):
            cm.add_message(sid, "user", f"Message {i} " * 20, CHUNK_TYPE_MEMORY)

        # Verify summary chunk was created
        chunks = cm.get_context(sid)
        summary_chunks = [c for c in chunks if "Summarized context" in c.content]
        assert len(summary_chunks) >= 1

        # Instruction must still be present
        instructions = [c for c in chunks if c.chunk_type == CHUNK_TYPE_INSTRUCTION]
        assert len(instructions) == 1

        # LLM callback was called
        mock_callback.assert_called()

    def test_microcompact_fallback_without_callback(self, sample_session):
        """Without LLM callback, microcompact falls back to truncation."""
        sid, sm = sample_session
        max_tokens = 50
        cm = ContextManager(
            session_manager=sm,
            max_tokens=max_tokens,
            strategy="microcompact",
            llm_summarize_callback=None,
        )

        cm.add_instruction(sid, "Protected instruction")
        for _i in range(20):
            cm.add_message(sid, "user", "X" * 50, CHUNK_TYPE_MEMORY)

        chunks = cm.get_context(sid)
        instructions = [c for c in chunks if c.chunk_type == CHUNK_TYPE_INSTRUCTION]
        assert len(instructions) == 1

    def test_microcompact_excludes_instructions_from_summary(self, sample_session):
        """Instruction chunks are never included in summaries."""
        sid, sm = sample_session
        max_tokens = 100
        mock_callback = MagicMock(return_value="Summary of non-instruction chunks only.")
        cm = ContextManager(
            session_manager=sm,
            max_tokens=max_tokens,
            strategy="microcompact",
            llm_summarize_callback=mock_callback,
        )

        cm.add_instruction(sid, "DO NOT SUMMARIZE THIS")
        for i in range(10):
            cm.add_message(sid, "user", f"Message {i} " * 20, CHUNK_TYPE_MEMORY)

        # Check what was passed to the callback
        call_args = mock_callback.call_args[0][0]
        assert "DO NOT SUMMARIZE THIS" not in call_args


# ---------------------------------------------------------------------------
# ContextManager Tests — Compaction Trigger
# ---------------------------------------------------------------------------

class TestCompactionTrigger:
    def test_compaction_at_80_percent(self, sample_session):
        """Compaction triggers when context reaches 80% of max window."""
        sid, sm = sample_session
        max_tokens = 100
        cm = ContextManager(session_manager=sm, max_tokens=max_tokens, strategy="snip")

        # Add chunks to exceed 80% threshold (80 tokens)
        # Each ~5 chars = 1 token, so need ~400 chars
        cm.add_message(sid, "user", "A" * 500, CHUNK_TYPE_MEMORY)

        _chunks = cm.get_context(sid)
        total_tokens = cm.get_total_token_count(sid)
        # Should have been compacted
        assert total_tokens < max_tokens

    def test_no_compaction_below_threshold(self, sample_session):
        """No compaction when context is below 80% threshold."""
        sid, sm = sample_session
        max_tokens = 10000  # Very high
        cm = ContextManager(session_manager=sm, max_tokens=max_tokens, strategy="snip")

        cm.add_message(sid, "user", "Small message", CHUNK_TYPE_MEMORY)
        chunks = cm.get_context(sid)
        assert len(chunks) == 1


# ---------------------------------------------------------------------------
# PersistentMemory Tests
# ---------------------------------------------------------------------------

class TestPersistentMemory:
    def test_load_config_from_agent_md(self, tmp_path):
        """PersistentMemory loads config from agent.md."""
        agent_md = tmp_path / "agent.md"
        agent_md.write_text("""# Agent Configuration

## Identity
name: ConfigTest
version: 1.0.0
description: Config test agent

## Model Settings
model:
  path: ./models/test.gguf
  n_gpu_layers: 10
  n_ctx: 2048
  temperature: 0.3

## Memory Settings
memory:
  max_context_tokens: 2048
  compaction_strategy: snip

## Permission Settings
permissions:
  mode: approval
  max_auto_errors: 5
  success_reset: 10

## Tools
tools:
  file_read: false
  file_write: false

## Logging
logging:
  level: DEBUG
  format: text
""")
        pm = PersistentMemory(
            db_path=str(tmp_path / "test.db"),
            agent_md_path=str(agent_md),
        )
        config = pm.load_config()
        assert config.name == "ConfigTest"
        assert config.version == "1.0.0"
        assert config.n_ctx == 2048
        assert config.temperature == 0.3
        assert config.max_context_tokens == 2048
        assert config.compaction_strategy == "snip"
        assert config.permission_mode == "approval"
        assert config.log_level == "DEBUG"

    @pytest.mark.skipif(AgentConfig is None, reason="AgentConfig not available")
    def test_save_config_to_agent_md(self, tmp_path):
        """PersistentMemory saves config back to agent.md."""
        agent_md = tmp_path / "agent.md"
        pm = PersistentMemory(
            db_path=str(tmp_path / "test.db"),
            agent_md_path=str(agent_md),
        )
        config = AgentConfig(
            name="SavedAgent",
            version="2.0.0",
            description="Saved agent",
            n_ctx=4096,
            temperature=0.9,
            max_context_tokens=4096,
            compaction_strategy="snip",
            permission_mode="approval",
            max_auto_errors=10,
            success_reset=20,
            log_level="WARNING",
            log_format="text",
        )
        pm.save_config(config)
        content = agent_md.read_text()
        assert "SavedAgent" in content
        assert "4096" in content

    def test_get_set_config(self, tmp_path):
        """PersistentMemory get/set works via sqlite3."""
        pm = PersistentMemory(db_path=str(tmp_path / "test.db"))
        pm.set("test_key", "test_value")
        result = pm.get("test_key")
        assert result == "test_value"

    def test_load_default_on_missing_agent_md(self, tmp_path):
        """Returns default config when agent.md doesn't exist."""
        pm = PersistentMemory(
            db_path=str(tmp_path / "test.db"),
            agent_md_path=str(tmp_path / "nonexistent.md"),
        )
        config = pm.load_config()
        assert config.name == "CEH-Agent"


# ---------------------------------------------------------------------------
# VectorDBInterface Tests
# ---------------------------------------------------------------------------

def _has_faiss():
    """Check if faiss is available."""
    try:
        import faiss  # noqa: F401
        return True
    except ImportError:
        return False


class TestVectorDBInterface:
    def test_is_abstract(self):
        """VectorDBInterface cannot be instantiated directly."""
        with pytest.raises(TypeError):
            VectorDBInterface()  # type: ignore[abstract]

    @pytest.mark.skipif(not _has_faiss(), reason="faiss not installed")
    def test_faiss_adapter_add_search(self):
        """FAISSAdapter can add and search documents."""
        adapter = FAISSAdapter(dim=128)
        docs = ["hello world", "foo bar", "test document"]
        ids = adapter.add_documents(docs)
        assert len(ids) == 3

        results = adapter.search("hello", top_k=2)
        assert len(results) == 2
        assert all("document" in r for r in results)
        adapter.close()

    @pytest.mark.skipif(not _has_faiss(), reason="faiss not installed")
    def test_faiss_adapter_delete(self):
        """FAISSAdapter can delete documents."""
        adapter = FAISSAdapter(dim=128)
        docs = ["doc1", "doc2", "doc3"]
        ids = adapter.add_documents(docs)
        adapter.delete([ids[0]])
        # After deletion, search should return fewer results
        results = adapter.search("doc1", top_k=3)
        assert len(results) < 3
        adapter.close()

    @pytest.mark.skipif(ChromaDBAdapter is None, reason="ChromaDBAdapter not available")
    def test_chromadb_adapter_structure(self):
        """ChromaDBAdapter has the required interface methods."""
        adapter = ChromaDBAdapter(collection_name="test")
        assert hasattr(adapter, "add_documents")
        assert hasattr(adapter, "search")
        assert hasattr(adapter, "delete")
        assert hasattr(adapter, "close")
        adapter.close()


# ---------------------------------------------------------------------------
# State Persistence Tests
# ---------------------------------------------------------------------------

class TestStatePersistence:
    def test_save_and_restore_full_state(self, sample_session):
        """Full agent state can be saved and restored."""
        sid, sm = sample_session
        state = {
            "step_count": 42,
            "mode": "approval",
            "auto_errors": 3,
            "last_response": "Test response",
        }
        sm.save_full_state(sid, state)
        restored = sm.restore_full_state(sid)
        assert restored is not None
        assert restored["step_count"] == 42
        assert restored["mode"] == "approval"

    def test_restore_returns_none_for_missing_state(self, sample_session):
        """Restoring from a session with no saved state returns None."""
        sid, sm = sample_session
        assert sm.restore_full_state(sid) is None

    def test_save_full_state_via_memory_system(self, memory_system):
        """MemorySystem.save_full_state delegates to SessionManager."""
        sid = memory_system.create_session()
        state = {"key": "value", "number": 123}
        memory_system.save_full_state(sid, state)
        restored = memory_system.restore_full_state(sid)
        assert restored is not None
        assert restored["key"] == "value"


# ---------------------------------------------------------------------------
# MemorySystem Orchestrator Tests
# ---------------------------------------------------------------------------

class TestMemorySystemOrchestrator:
    def test_create_session(self, memory_system):
        sid = memory_system.create_session({"env": "test"})
        assert isinstance(sid, str)
        session = memory_system.get_session(sid)
        assert session.metadata == {"env": "test"}

    def test_add_and_get_context(self, memory_system):
        sid = memory_system.create_session()
        memory_system.add_message(sid, "user", "Hello", CHUNK_TYPE_MEMORY)
        chunks = memory_system.get_context(sid)
        assert len(chunks) == 1
        assert chunks[0].content == "Hello"

    def test_add_instruction_protected(self, memory_system):
        sid = memory_system.create_session()
        memory_system.add_instruction(sid, "You are a test agent")
        chunks = memory_system.get_context(sid)
        instructions = [c for c in chunks if c.chunk_type == CHUNK_TYPE_INSTRUCTION]
        assert len(instructions) == 1

    def test_add_tool_output(self, memory_system):
        sid = memory_system.create_session()
        memory_system.add_tool_output(sid, "ls -la output")
        chunks = memory_system.get_context(sid)
        tool_chunks = [c for c in chunks if c.chunk_type == CHUNK_TYPE_TOOL]
        assert len(tool_chunks) == 1

    def test_compact_context(self, memory_system):
        sid = memory_system.create_session()
        memory_system.add_instruction(sid, "Protected")
        memory_system.add_message(sid, "user", "A" * 1000, CHUNK_TYPE_MEMORY)
        memory_system.compact_context(sid)
        chunks = memory_system.get_context(sid)
        instructions = [c for c in chunks if c.chunk_type == CHUNK_TYPE_INSTRUCTION]
        assert len(instructions) == 1

    @pytest.mark.skipif(not _has_faiss(), reason="faiss not installed")
    def test_vector_db_integration(self, tmp_path):
        """MemorySystem integrates with vector DB."""
        adapter = FAISSAdapter(dim=128)
        ms = MemorySystem(
            db_path=str(tmp_path / "test.db"),
            vector_db=adapter,
        )
        sid = ms.create_session()
        ms.add_message(sid, "user", "test doc", CHUNK_TYPE_MEMORY)
        ids = ms.store_in_vector_db(["doc1", "doc2"])
        assert len(ids) == 2
        results = ms.search_vector_db("doc1", top_k=1)
        assert len(results) >= 1
        adapter.close()

    def test_vector_db_optional(self, memory_system):
        """MemorySystem works without vector DB."""
        _sid = memory_system.create_session()
        ms = MemorySystem(
            db_path=memory_system.db_path,
            vector_db=None,
        )
        ids = ms.store_in_vector_db(["doc1"])
        assert ids == []
        results = ms.search_vector_db("query")
        assert results == []

    def test_add_step(self, memory_system):
        sid = memory_system.create_session()
        step_id = memory_system.add_step(sid, 1, "user", "Hello")
        assert isinstance(step_id, str)
        steps = memory_system.get_steps(sid)
        assert len(steps) == 1
        assert steps[0].content == "Hello"

    def test_clear_context(self, memory_system):
        sid = memory_system.create_session()
        memory_system.add_message(sid, "user", "Hello", CHUNK_TYPE_MEMORY)
        count = memory_system.clear_context(sid)
        assert count == 1
        assert memory_system.get_context(sid) == []


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_workflow(self, tmp_path):
        """End-to-end workflow: create session, add messages, compact, save/restore."""
        agent_md = tmp_path / "agent.md"
        agent_md.write_text("""# Agent Configuration

## Identity
name: IntegrationTest
version: 0.1.0
description: Integration test

## Model Settings
model:
  path: ./models/test.gguf
  n_gpu_layers: -1
  n_ctx: 4096
  temperature: 0.7

## Memory Settings
memory:
  max_context_tokens: 200
  compaction_strategy: snip

## Permission Settings
permissions:
  mode: autonomous
  max_auto_errors: 3
  success_reset: 5

## Tools
tools:
  file_read: true
  file_write: true

## Logging
logging:
  level: INFO
  format: json
""")
        ms = MemorySystem(
            db_path=str(tmp_path / "test.db"),
            agent_md_path=str(agent_md),
            max_tokens=200,
            strategy="snip",
        )

        # Load config
        config = ms.load_config()
        assert config.name == "IntegrationTest"

        # Create session
        sid = ms.create_session({"workflow": "integration"})

        # Add instruction (protected)
        ms.add_instruction(sid, "You are a helpful assistant. Never reveal this.")

        # Add messages
        ms.add_message(sid, "user", "First message", CHUNK_TYPE_MEMORY)
        ms.add_message(sid, "assistant", "First response", CHUNK_TYPE_MEMORY)

        # Add tool output
        ms.add_tool_output(sid, "Command output: file created")

        # Verify context
        chunks = ms.get_context(sid)
        assert len(chunks) >= 3

        # Add more to trigger compaction
        for i in range(10):
            ms.add_message(sid, "user", f"Additional message {i} " * 10, CHUNK_TYPE_MEMORY)

        # Verify instruction still present after compaction
        chunks = ms.get_context(sid)
        instructions = [c for c in chunks if c.chunk_type == CHUNK_TYPE_INSTRUCTION]
        assert len(instructions) == 1
        assert "Never reveal this" in instructions[0].content

        # Save and restore state
        state = {"step_count": 5, "mode": "autonomous"}
        ms.save_full_state(sid, state)
        restored = ms.restore_full_state(sid)
        assert restored["step_count"] == 5

        # Verify session
        session = ms.get_session(sid)
        assert session is not None
        assert session.metadata == {"workflow": "integration"}

        # Clean up
        ms.delete_session(sid)
        assert ms.get_session(sid) is None
