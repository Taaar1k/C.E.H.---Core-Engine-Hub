"""Tests for c_e_h.ui.dashboard module.

Tests Dashboard class rendering and text mode fallback.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from rich.console import Console
from rich.layout import Layout

from c_e_h.agent import Agent, AgentConfig
from c_e_h.ui.dashboard import Dashboard


@pytest.fixture
def agent():
    """Create a test agent."""
    return Agent(AgentConfig())


@pytest.fixture
def mock_session_manager():
    """Create a mock SessionManager."""
    sm = MagicMock()
    session = MagicMock()
    session.id = "test1234"
    session.name = "Test Session"
    session.message_count = 5
    session.created_at = datetime.now(timezone.utc).isoformat()
    session.last_accessed = datetime.now(timezone.utc).isoformat()
    session.model = "llama-3-8b"
    sm.list_sessions.return_value = [session]
    return sm


class TestDashboard:
    """Tests for Dashboard class."""

    def test_init(self, agent):
        """Test dashboard initialization."""
        dashboard = Dashboard(agent)
        assert dashboard.agent is agent
        assert dashboard.session_manager is None
        assert dashboard.refresh_interval == 2.0

    def test_init_with_session_manager(self, agent, mock_session_manager):
        """Test dashboard with session manager."""
        dashboard = Dashboard(agent, session_manager=mock_session_manager)
        assert dashboard.session_manager is mock_session_manager

    def test_create_initial_layout(self, agent):
        """Test layout creation."""
        dashboard = Dashboard(agent)
        layout = dashboard._create_initial_layout()
        assert isinstance(layout, Layout)
        # Check that layout has the expected child names
        child_names = [child.name for child in layout.children]
        assert "header" in child_names
        assert "main" in child_names
        assert "footer" in child_names

    def test_build_header(self, agent):
        """Test header panel building."""
        dashboard = Dashboard(agent)
        header = dashboard._build_header()
        assert header is not None

    def test_build_agent_status(self, agent):
        """Test agent status panel building."""
        dashboard = Dashboard(agent)
        status = dashboard._build_agent_status()
        assert status is not None

    def test_build_agent_status_with_errors(self, agent):
        """Test agent status with errors."""
        agent.state.auto_errors = 3
        agent.state.mode = "approval"
        dashboard = Dashboard(agent)
        status = dashboard._build_agent_status()
        assert status is not None

    def test_build_session_info_no_manager(self, agent):
        """Test session info without session manager."""
        dashboard = Dashboard(agent)
        info = dashboard._build_session_info()
        assert info is not None

    def test_build_session_info_with_manager(self, agent, mock_session_manager):
        """Test session info with session manager."""
        dashboard = Dashboard(agent, session_manager=mock_session_manager)
        info = dashboard._build_session_info()
        assert info is not None

    def test_build_recent_messages_empty(self, agent):
        """Test recent messages with empty context."""
        dashboard = Dashboard(agent)
        messages = dashboard._build_recent_messages()
        assert messages is not None

    def test_build_recent_messages_with_content(self, agent):
        """Test recent messages with content."""
        agent.state.context.append({"role": "user", "content": "Hello"})
        agent.state.context.append({"role": "assistant", "content": "Hi there!"})
        dashboard = Dashboard(agent)
        messages = dashboard._build_recent_messages()
        assert messages is not None

    def test_build_metrics(self, agent):
        """Test metrics panel building."""
        dashboard = Dashboard(agent)
        metrics = dashboard._build_metrics()
        assert metrics is not None

    def test_update_layout(self, agent):
        """Test layout update."""
        dashboard = Dashboard(agent)
        dashboard._layout = dashboard._create_initial_layout()
        dashboard._update_layout()
        assert dashboard._layout is not None

    def test_print_text_dashboard(self, agent):
        """Test text mode dashboard printing."""
        output = io.StringIO()
        console = Console(file=output, force_terminal=True)
        dashboard = Dashboard(agent, console=console)
        dashboard._print_text_dashboard()
        result = output.getvalue()
        assert "C.E.H. Dashboard" in result

    def test_print_text_dashboard_with_sessions(self, agent, mock_session_manager):
        """Test text mode with sessions."""
        output = io.StringIO()
        console = Console(file=output, force_terminal=True)
        dashboard = Dashboard(agent, session_manager=mock_session_manager, console=console)
        dashboard._print_text_dashboard()
        result = output.getvalue()
        assert "Test Session" in result

    def test_stop(self, agent):
        """Test dashboard stop."""
        dashboard = Dashboard(agent)
        dashboard._running = True
        dashboard.stop()
        assert dashboard._running is False

    def test_handle_key_quit(self, agent):
        """Test quit key handling."""
        dashboard = Dashboard(agent)
        dashboard._running = True
        dashboard._handle_key("q")
        assert dashboard._running is False

    def test_handle_key_clear(self, agent):
        """Test clear key handling."""
        agent.state.context.append({"role": "user", "content": "test"})
        dashboard = Dashboard(agent)
        dashboard._layout = dashboard._create_initial_layout()
        dashboard._handle_key("c")
        assert len(agent.state.context) == 0

    def test_handle_key_help(self, agent):
        """Test help key toggle."""
        dashboard = Dashboard(agent)
        dashboard._help_visible = False
        dashboard._handle_key("?")
        assert dashboard._help_visible is True
        dashboard._handle_key("h")
        assert dashboard._help_visible is False

    def test_handle_key_refresh(self, agent):
        """Test refresh key."""
        dashboard = Dashboard(agent)
        dashboard._last_update = 100
        dashboard._handle_key("r")
        assert dashboard._last_update == 0

    def test_max_messages_limit(self, agent):
        """Test max messages limit."""
        for i in range(10):
            agent.state.context.append({"role": "user", "content": f"Message {i}"})
        dashboard = Dashboard(agent, max_messages=5)
        messages = dashboard._build_recent_messages()
        assert messages is not None
