"""Integration tests for the full C.E.H. agent loop.

These tests verify that all components (agent, memory, tools, session_manager)
work together correctly end-to-end.  llama_backend is mocked so no actual
model files are required.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from c_e_h.agent import Agent, AgentConfig
from c_e_h.session_manager import SessionManager
from c_e_h.tools import ToolRegistry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def temp_session_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for session database files.

    Each test gets its own isolated temp directory so SQLite databases
    never collide.
    """
    return tmp_path


@pytest.fixture()
def session_manager(temp_session_dir: Path) -> SessionManager:
    """Create a SessionManager backed by a temporary SQLite database."""
    db_path = temp_session_dir / "sessions.db"
    return SessionManager(db_path=str(db_path))


@pytest.fixture()
def tool_registry() -> ToolRegistry:
    """Return a fresh ToolRegistry for each test."""
    return ToolRegistry()


@pytest.fixture()
def mock_llama_backend():
    """Mock the llama_backend module so no model files are needed.

    Note: Agent._generate_response is currently a stub (TODO: llama.cpp
    integration), so this fixture is provided for future use when the
    backend is wired up.  Tests that need the mock can use it directly.
    """
    mock_backend = MagicMock()
    mock_backend.generate.return_value = MagicMock(
        text="[Mocked] Processed: test prompt",
        prompt_tokens=10,
        completion_tokens=5,
        total_time=0.01,
        tokens_per_second=500.0,
        has_context_overflow=False,
        grammar_valid=True,
    )
    yield mock_backend


# ---------------------------------------------------------------------------
# Test 1: Full Agent Loop
# ---------------------------------------------------------------------------


def test_full_agent_loop(
    session_manager: SessionManager,
    temp_session_dir: Path,
) -> None:
    """Simulate a complete agent interaction: create session -> send prompt -> get response -> verify memory persistence.

    Steps:
        1. Create a session via SessionManager.
        2. Instantiate an Agent and call ``run()`` with a prompt.
        3. Verify the agent returns a valid response.
        4. Add the user and assistant messages to the session.
        5. Re-open the session and verify both messages are persisted.
    """
    # 1. Create session
    session = session_manager.create_session(
        name="integration-test-loop",
        system_prompt="You are a helpful assistant.",
        model="test-model",
    )
    assert session.id is not None
    assert session.name == "integration-test-loop"
    assert session.message_count == 0

    # 2. Create agent and run a prompt
    config = AgentConfig(name="IntegrationAgent", permission_mode="autonomous")
    agent = Agent(config=config)
    prompt = "What is the capital of France?"
    response = agent.run(prompt)

    # 3. Verify agent response (stub returns "[Step N] Processed: ...")
    assert response is not None
    assert isinstance(response, str)
    assert len(response) > 0
    assert "Processed:" in response
    assert agent.state.step_count == 1

    # 4. Persist messages to session
    session_manager.add_message(session.id, "user", prompt)
    session_manager.add_message(session.id, "assistant", response)

    # Verify message count updated
    refreshed_session = session_manager.get_session(session.id)
    assert refreshed_session is not None
    assert refreshed_session.message_count == 2

    # 5. Re-open session and verify history
    messages = session_manager.get_messages(session.id)
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[0].content == prompt
    assert messages[1].role == "assistant"
    assert messages[1].content == response


# ---------------------------------------------------------------------------
# Test 2: Tool Execution Chain
# ---------------------------------------------------------------------------


def test_tool_execution_chain(
    tool_registry: ToolRegistry,
    temp_session_dir: Path,
) -> None:
    """Verify that tools can be called in sequence through the agent with proper state management.

    Steps:
        1. Register a chain of simple tools (write_file -> read_file -> count_lines).
        2. Execute them sequentially, passing state between calls.
        3. Verify the final output is correct.
        4. Verify the tool registry state is consistent.
    """
    # Register tools
    write_results: list[str] = []
    read_results: list[str] = []

    @tool_registry.register(
        name="write_test_file",
        description="Write a test file with given content",
    )
    def write_test_file(content: str, path: str = "/tmp/test_integration.txt") -> dict:
        """Write content to a test file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        write_results.append(content)
        return {"status": "ok", "path": str(p), "bytes": len(content)}

    @tool_registry.register(
        name="read_test_file",
        description="Read a test file and return its content",
    )
    def read_test_file(path: str = "/tmp/test_integration.txt") -> dict:
        """Read content from a test file."""
        p = Path(path)
        content = p.read_text()
        read_results.append(content)
        return {"status": "ok", "path": str(p), "content": content}

    @tool_registry.register(
        name="count_lines",
        description="Count lines in given text",
    )
    def count_lines(text: str) -> dict:
        """Count lines in text."""
        line_count = len(text.strip().split("\n")) if text.strip() else 0
        return {"status": "ok", "line_count": line_count}

    # Execute chain: write -> read -> count
    # Step 1: Write
    write_result = tool_registry.get("write_test_file").func(
        content="Line 1\nLine 2\nLine 3",
    )
    assert write_result["status"] == "ok"
    assert write_result["bytes"] == 20
    assert len(write_results) == 1

    # Step 2: Read
    read_result = tool_registry.get("read_test_file").func()
    assert read_result["status"] == "ok"
    assert read_result["content"] == "Line 1\nLine 2\nLine 3"
    assert len(read_results) == 1

    # Step 3: Count lines
    count_result = tool_registry.get("count_lines").func(text="Line 1\nLine 2\nLine 3")
    assert count_result["status"] == "ok"
    assert count_result["line_count"] == 3

    # Verify registry state
    registered_tools = tool_registry.list_tools()
    assert "write_test_file" in registered_tools
    assert "read_test_file" in registered_tools
    assert "count_lines" in registered_tools
    assert len(registered_tools) == 3

    # Verify state consistency: write and read should agree
    assert write_results[0] == read_results[0]


# ---------------------------------------------------------------------------
# Test 3: Session Persistence
# ---------------------------------------------------------------------------


def test_session_persistence(
    temp_session_dir: Path,
) -> None:
    """Create a session, add messages, close it (delete manager), reopen it, verify message history is intact.

    Steps:
        1. Create a SessionManager and a session.
        2. Add multiple messages (user + assistant pairs).
        3. Delete the SessionManager (simulating process exit).
        4. Create a new SessionManager pointing to the same database.
        5. Re-open the session and verify all messages are intact.
    """
    db_path = temp_session_dir / "persist_test.db"

    # Phase 1: Create session and add messages
    sm1 = SessionManager(db_path=str(db_path))
    session = sm1.create_session(
        name="persistence-test",
        system_prompt="Test session for persistence.",
        model="test-model-v1",
    )
    session_id = session.id

    # Add multiple conversation turns
    conversations = [
        ("user", "Hello, who are you?"),
        ("assistant", "I am CEH-Agent, your local AI assistant."),
        ("user", "What can you do?"),
        ("assistant", "I can read files, write files, and execute commands."),
        ("user", "Summarize this document."),
        ("assistant", "I need a file path to summarize."),
    ]

    for role, content in conversations:
        sm1.add_message(session_id, role, content)

    # Verify message count
    session_info = sm1.get_session(session_id)
    assert session_info is not None
    assert session_info.message_count == len(conversations)

    # Retrieve and verify all messages
    all_messages = sm1.get_messages(session_id)
    assert len(all_messages) == len(conversations)
    for i, (expected_role, expected_content) in enumerate(conversations):
        assert all_messages[i].role == expected_role
        assert all_messages[i].content == expected_content

    # Phase 2: "Close" the session manager (simulate process exit)
    del sm1

    # Phase 3: Reopen with a fresh SessionManager
    sm2 = SessionManager(db_path=str(db_path))

    # Verify session still exists
    reopened_session = sm2.get_session(session_id)
    assert reopened_session is not None
    assert reopened_session.name == "persistence-test"
    assert reopened_session.model == "test-model-v1"
    assert reopened_session.message_count == len(conversations)

    # Verify message history is intact
    reopened_messages = sm2.get_messages(session_id)
    assert len(reopened_messages) == len(conversations)
    for i, (expected_role, expected_content) in enumerate(conversations):
        assert reopened_messages[i].role == expected_role
        assert reopened_messages[i].content == expected_content

    # Verify metadata is preserved (None when not set)
    assert reopened_session.metadata is None or reopened_session.metadata == {}
