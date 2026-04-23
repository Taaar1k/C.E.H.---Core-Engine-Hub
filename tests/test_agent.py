"""Tests for the C.E.H. Agent module."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from c_e_h.agent import Agent, AgentConfig, AgentState

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def valid_config() -> AgentConfig:
    """Return a default AgentConfig for testing."""
    return AgentConfig()


@pytest.fixture()
def agent_md_tmp(tmp_path: Path) -> Path:
    """Create a temporary agent.md YAML file.

    Returns:
        Path to the temporary file.
    """
    data = {
        "name": "Test-Agent",
        "version": "1.0.0",
        "description": "Test agent for unit tests",
        "model": {
            "path": "./models/test.gguf",
            "n_gpu_layers": 10,
            "n_ctx": 4096,
            "temperature": 0.5,
        },
        "memory": {
            "max_context_tokens": 4096,
            "compaction_strategy": "snip",
        },
        "permissions": {
            "mode": "approval",
            "max_auto_errors": 5,
            "success_reset": 10,
        },
        "tools": {
            "file_read": False,
            "file_write": False,
            "execute_command": False,
            "web_search": True,
        },
        "logging": {
            "level": "DEBUG",
            "format": "text",
        },
    }
    agent_md = tmp_path / "agent.md"
    with open(agent_md, "w") as f:
        yaml.dump(data, f)
    return agent_md


# ---------------------------------------------------------------------------
# AgentConfig tests
# ---------------------------------------------------------------------------

class TestAgentConfig:
    """Tests for AgentConfig pydantic model."""

    def test_default_values(self) -> None:
        """Test that AgentConfig has sensible defaults."""
        config = AgentConfig()
        assert config.name == "CEH-Agent"
        assert config.version == "0.1.0"
        assert config.description == "Your local AI assistant"
        assert config.model_path == "./models/llama-3-8b.Q4_K_M.gguf"
        assert config.n_gpu_layers == -1
        assert config.n_ctx == 8192
        assert config.temperature == 0.7
        assert config.max_context_tokens == 8192
        assert config.compaction_strategy == "microcompact"
        assert config.permission_mode == "autonomous"
        assert config.max_auto_errors == 3
        assert config.success_reset == 5
        assert config.log_level == "INFO"
        assert config.log_format == "json"

    def test_custom_values(self) -> None:
        """Test that AgentConfig accepts custom values."""
        config = AgentConfig(
            name="Custom-Agent",
            n_ctx=16384,
            temperature=0.9,
            permission_mode="approval",
        )
        assert config.name == "Custom-Agent"
        assert config.n_ctx == 16384
        assert config.temperature == 0.9
        assert config.permission_mode == "approval"


# ---------------------------------------------------------------------------
# AgentState tests
# ---------------------------------------------------------------------------

class TestAgentState:
    """Tests for AgentState dataclass serialization."""

    def test_default_state(self) -> None:
        """Test default AgentState values."""
        state = AgentState()
        assert state.step_count == 0
        assert state.mode == "autonomous"
        assert state.auto_errors == 0
        assert state.context == []
        assert state.last_response is None
        assert state.started_at is None

    def test_state_to_dict(self) -> None:
        """Test AgentState.to_dict() serialization."""
        state = AgentState(
            step_count=5,
            mode="approval",
            auto_errors=2,
            context=[{"role": "user", "content": "hello"}],
            last_response="hi there",
            started_at="2026-01-01T00:00:00",
        )
        d = state.to_dict()
        assert d["step_count"] == 5
        assert d["mode"] == "approval"
        assert d["auto_errors"] == 2
        assert d["context"] == [{"role": "user", "content": "hello"}]
        assert d["last_response"] == "hi there"
        assert d["started_at"] == "2026-01-01T00:00:00"

    def test_state_from_dict(self) -> None:
        """Test AgentState.from_dict() deserialization."""
        data = {
            "step_count": 10,
            "mode": "autonomous",
            "auto_errors": 0,
            "context": [],
            "last_response": None,
            "started_at": "2026-06-15T12:00:00",
        }
        state = AgentState.from_dict(data)
        assert state.step_count == 10
        assert state.mode == "autonomous"
        assert state.auto_errors == 0
        assert state.context == []
        assert state.last_response is None
        assert state.started_at == "2026-06-15T12:00:00"

    def test_state_from_dict_ignores_extra_keys(self) -> None:
        """Test that extra keys in dict are ignored."""
        data = {
            "step_count": 3,
            "mode": "autonomous",
            "extra_key": "should_be_ignored",
        }
        state = AgentState.from_dict(data)
        assert state.step_count == 3
        assert state.mode == "autonomous"
        assert not hasattr(state, "extra_key")


# ---------------------------------------------------------------------------
# Agent initialization tests
# ---------------------------------------------------------------------------

class TestAgentInitialization:
    """Tests for Agent initialization."""

    def test_agent_initialization_defaults(self) -> None:
        """Test Agent initializes with default config."""
        agent = Agent()
        assert agent.config.name == "CEH-Agent"
        assert agent.state.step_count == 0
        assert agent.state.mode == "autonomous"
        assert agent.state.auto_errors == 0

    def test_agent_initialization_with_config(self) -> None:
        """Test Agent initializes with custom config."""
        config = AgentConfig(name="TestAgent", n_ctx=4096)
        agent = Agent(config=config)
        assert agent.config.name == "TestAgent"
        assert agent.config.n_ctx == 4096

    def test_agent_from_agent_md_existing(self, agent_md_tmp: Path) -> None:
        """Test Agent.from_agent_md() with existing file."""
        agent = Agent.from_agent_md(str(agent_md_tmp))
        assert agent.config.name == "Test-Agent"
        assert agent.config.version == "1.0.0"
        assert agent.config.model_path == "./models/test.gguf"
        assert agent.config.n_gpu_layers == 10
        assert agent.config.n_ctx == 4096
        assert agent.config.temperature == 0.5
        assert agent.config.max_context_tokens == 4096
        assert agent.config.compaction_strategy == "snip"
        assert agent.config.permission_mode == "approval"
        assert agent.config.max_auto_errors == 5
        assert agent.config.success_reset == 10
        assert agent.config.tools["file_read"] is False
        assert agent.config.tools["web_search"] is True
        assert agent.config.log_level == "DEBUG"
        assert agent.config.log_format == "text"

    def test_agent_from_agent_md_missing(self, tmp_path: Path) -> None:
        """Test Agent.from_agent_md() with non-existing file uses defaults."""
        missing = tmp_path / "nonexistent.md"
        agent = Agent.from_agent_md(str(missing))
        assert agent.config.name == "CEH-Agent"


# ---------------------------------------------------------------------------
# Agent run tests
# ---------------------------------------------------------------------------

class TestAgentRun:
    """Tests for Agent.run() method."""

    def test_agent_run_step(self) -> None:
        """Test Agent.run() increments step count and appends context."""
        agent = Agent()
        response = agent.run("Hello, world!")
        assert agent.state.step_count == 1
        assert len(agent.state.context) == 2  # user + assistant
        assert agent.state.context[0] == {"role": "user", "content": "Hello, world!"}
        assert agent.state.context[1]["role"] == "assistant"
        assert agent.state.last_response == response

    def test_agent_run_multiple_steps(self) -> None:
        """Test multiple run calls increment step count."""
        agent = Agent()
        agent.run("First prompt")
        agent.run("Second prompt")
        assert agent.state.step_count == 2
        assert len(agent.state.context) == 4


# ---------------------------------------------------------------------------
# Token estimation tests
# ---------------------------------------------------------------------------

class TestTokenEstimation:
    """Tests for token estimation."""

    def test_agent_token_estimation(self) -> None:
        """Test _estimate_tokens heuristic."""
        agent = Agent()
        # 40 chars => ~10 tokens
        text = "a" * 40
        assert agent._estimate_tokens(text) == 10

    def test_agent_token_estimation_empty(self) -> None:
        """Test that empty string returns minimum 1 token."""
        agent = Agent()
        assert agent._estimate_tokens("") == 1

    def test_agent_token_estimation_short(self) -> None:
        """Test short text returns at least 1 token."""
        agent = Agent()
        assert agent._estimate_tokens("hi") == 1


# ---------------------------------------------------------------------------
# State serialization tests
# ---------------------------------------------------------------------------

class TestStateSerialization:
    """Tests for state save/load."""

    def test_agent_state_serialization(self) -> None:
        """Test Agent.save_state() produces valid dict."""
        agent = Agent()
        agent.run("test prompt")
        state = agent.save_state()
        assert "config" in state
        assert "state" in state
        assert state["state"]["step_count"] == 1
        assert state["state"]["last_response"] is not None

    def test_agent_state_deserialization(self) -> None:
        """Test Agent.load_state() restores state."""
        agent = Agent()
        agent.run("test prompt")
        saved = agent.save_state()

        agent2 = Agent()
        agent2.load_state(saved)
        assert agent2.config.name == agent.config.name
        assert agent2.state.step_count == agent.state.step_count
        assert agent2.state.last_response == agent.state.last_response

    def test_agent_get_state_json(self) -> None:
        """Test Agent.get_state_json() returns valid JSON."""
        agent = Agent()
        json_str = agent.get_state_json()
        data = json.loads(json_str)
        assert "config" in data
        assert "state" in data

    def test_agent_load_state_json(self) -> None:
        """Test Agent.load_state_json() creates valid Agent."""
        agent = Agent()
        agent.run("test")
        json_str = agent.get_state_json()

        agent2 = Agent.load_state_json(json_str)
        assert agent2.state.step_count == agent.state.step_count
        assert agent2.state.last_response == agent.state.last_response


# ---------------------------------------------------------------------------
# Error handling and retry tests
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Tests for error handling and retry logic."""

    def test_agent_error_handling_retry(self) -> None:
        """Test that Agent retries on LLM failure."""
        agent = Agent()
        call_count = 0

        def failing_response(prompt: str) -> str:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("LLM unavailable")

        with patch.object(
            agent, "_generate_response", side_effect=failing_response
        ):
            with patch.object(agent, "BASE_RETRY_DELAY", 0.01):  # Fast retries
                response = agent.run("test")

        assert call_count == agent.MAX_RETRIES
        assert "failed" in response
        assert agent.state.auto_errors == 1

    def test_agent_mode_switch_on_max_errors(self) -> None:
        """Test that agent switches to approval mode after max_auto_errors."""
        config = AgentConfig(max_auto_errors=3)
        agent = Agent(config=config)
        assert agent.state.mode == "autonomous"

        call_count = 0

        def failing_response(prompt: str) -> str:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("LLM unavailable")

        with patch.object(
            agent, "_generate_response", side_effect=failing_response
        ):
            with patch.object(agent, "BASE_RETRY_DELAY", 0.01):
                agent.run("test 1")
                agent.run("test 2")
                agent.run("test 3")

        assert agent.state.auto_errors == 3
        assert agent.state.mode == "approval"

    def test_agent_success_resets_errors(self) -> None:
        """Test that a successful run resets auto_errors."""
        agent = Agent()
        # Simulate errors
        with patch.object(agent, "_generate_response", side_effect=RuntimeError("fail")):
            with patch.object(agent, "BASE_RETRY_DELAY", 0.01):
                agent.run("error prompt")
        assert agent.state.auto_errors == 1

        # Now succeed
        agent._generate_response = lambda p: "success response"
        response = agent.run("success prompt")
        assert agent.state.auto_errors == 0
        assert response == "success response"
