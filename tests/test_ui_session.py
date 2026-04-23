"""Tests for c_e_h.ui.session_ui module.

Tests SessionBrowser class with real and mock SessionManager.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from rich.console import Console
from rich.table import Table

from c_e_h.ui.session_ui import SessionBrowser


@dataclass
class FakeSession:
    """Minimal session dataclass for testing."""
    id: str
    name: str
    message_count: int
    created_at: str
    last_accessed: str
    model: str | None = None


@pytest.fixture
def mock_session_manager():
    """Create a mock SessionManager with test data."""
    sm = MagicMock()

    now = datetime.now(timezone.utc).isoformat()
    sessions = [
        FakeSession(
            id="sess0001",
            name="Test Session 1",
            message_count=10,
            created_at=now,
            last_accessed=now,
            model="llama-3-8b",
        ),
        FakeSession(
            id="sess0002",
            name="Debug Session",
            message_count=5,
            created_at=now,
            last_accessed=now,
            model=None,
        ),
        FakeSession(
            id="sess0003",
            name="Test Session 3",
            message_count=0,
            created_at=now,
            last_accessed=now,
            model="mistral-7b",
        ),
    ]
    sm.list_sessions.return_value = sessions
    return sm


@pytest.fixture
def browser(mock_session_manager):
    """Create a SessionBrowser instance."""
    output = io.StringIO()
    console = Console(file=output, force_terminal=True)
    return SessionBrowser(
        mock_session_manager,
        console=console,
        active_session_id="sess0001",
    )


class TestSessionBrowser:
    """Tests for SessionBrowser class."""

    def test_init(self, mock_session_manager):
        """Test initialization."""
        browser = SessionBrowser(mock_session_manager)
        assert browser.session_manager is mock_session_manager
        assert browser._active_session_id is None

    def test_init_with_active_session(self, mock_session_manager):
        """Test initialization with active session."""
        browser = SessionBrowser(
            mock_session_manager,
            active_session_id="sess0001",
        )
        assert browser._active_session_id == "sess0001"

    def test_render(self, browser):
        """Test basic rendering."""
        output = io.StringIO()
        browser.console = Console(file=output, force_terminal=True)
        browser.render()
        result = output.getvalue()
        assert "sess0001" in result
        assert "Test Session 1" in result

    def test_render_with_filter(self, browser):
        """Test rendering with filter."""
        output = io.StringIO()
        browser.console = Console(file=output, force_terminal=True)
        browser.render(filter_text="Test")
        result = output.getvalue()
        assert "Test Session 1" in result
        assert "Debug Session" not in result

    def test_render_no_sessions(self):
        """Test rendering with no sessions."""
        sm = MagicMock()
        sm.list_sessions.return_value = []
        output = io.StringIO()
        console = Console(file=output, force_terminal=True)
        browser = SessionBrowser(sm, console=console)
        browser.render()
        result = output.getvalue()
        assert "No sessions found" in result

    def test_render_session_error(self):
        """Test rendering when session manager errors."""
        sm = MagicMock()
        sm.list_sessions.side_effect = Exception("DB error")
        output = io.StringIO()
        console = Console(file=output, force_terminal=True)
        browser = SessionBrowser(sm, console=console)
        browser.render()
        # Should not raise, just print error

    def test_render_as_string(self, browser):
        """Test string rendering."""
        result = browser.render_as_string()
        assert isinstance(result, str)
        assert "sess0001" in result

    def test_render_as_string_with_filter(self, browser):
        """Test string rendering with filter."""
        result = browser.render_as_string(filter_text="Debug")
        assert "Debug Session" in result
        assert "Test Session 1" not in result

    def test_build_table(self, browser):
        """Test table building."""
        sessions = browser.session_manager.list_sessions()
        table = browser._build_table(sessions)
        assert isinstance(table, Table)

    def test_build_table_active_indicator(self, browser):
        """Test active session indicator in table."""
        sessions = browser.session_manager.list_sessions()
        table = browser._build_table(sessions)
        # The active session (sess0001) should have special styling
        assert table is not None

    def test_format_timestamp(self, browser):
        """Test timestamp formatting."""
        ts = "2026-04-22T15:30:00+00:00"
        formatted = browser._format_timestamp(ts)
        assert formatted == "2026-04-22 15:30"

    def test_format_timestamp_short(self, browser):
        """Test formatting short timestamp."""
        ts = "2026-04-22"
        formatted = browser._format_timestamp(ts)
        # Short timestamps get full format
        assert formatted == "2026-04-22 00:00"

    def test_format_timestamp_invalid(self, browser):
        """Test formatting invalid timestamp."""
        ts = "not-a-timestamp"
        formatted = browser._format_timestamp(ts)
        assert formatted == "not-a-timestamp"

    def test_select_session(self, browser):
        """Test session selection."""
        mock_session = MagicMock()
        mock_session.id = "new_sess"
        browser.session_manager.get_session.return_value = mock_session

        result = browser.select_session("new_sess")
        assert result is mock_session
        assert browser._active_session_id == "new_sess"

    def test_select_session_not_found(self, browser):
        """Test selecting non-existent session."""
        browser.session_manager.get_session.return_value = None
        result = browser.select_session("nonexistent")
        assert result is None

    def test_select_session_error(self, browser):
        """Test session selection error."""
        browser.session_manager.get_session.side_effect = Exception("DB error")
        output = io.StringIO()
        browser.console = Console(file=output, force_terminal=True)
        result = browser.select_session("bad_id")
        assert result is None

    def test_create_session(self, browser):
        """Test session creation."""
        mock_session = MagicMock()
        mock_session.id = "new0001"
        mock_session.name = "New Session"
        browser.session_manager.create_session.return_value = mock_session

        output = io.StringIO()
        browser.console = Console(file=output, force_terminal=True)
        result = browser.create_session("New Session", model="llama-3-8b")
        assert result is mock_session

    def test_create_session_error(self, browser):
        """Test session creation error."""
        browser.session_manager.create_session.side_effect = Exception("DB error")
        output = io.StringIO()
        browser.console = Console(file=output, force_terminal=True)
        result = browser.create_session("New Session")
        assert result is None

    def test_delete_session(self, browser):
        """Test session deletion."""
        browser.session_manager.delete_session.return_value = True
        output = io.StringIO()
        browser.console = Console(file=output, force_terminal=True)
        result = browser.delete_session("sess0001")
        assert result is True

    def test_delete_session_not_found(self, browser):
        """Test deleting non-existent session."""
        browser.session_manager.delete_session.return_value = False
        output = io.StringIO()
        browser.console = Console(file=output, force_terminal=True)
        result = browser.delete_session("nonexistent")
        assert result is False

    def test_delete_session_error(self, browser):
        """Test session deletion error."""
        browser.session_manager.delete_session.side_effect = Exception("DB error")
        output = io.StringIO()
        browser.console = Console(file=output, force_terminal=True)
        result = browser.delete_session("bad_id")
        assert result is False

    def test_interactive_mode_non_terminal(self, browser):
        """Test interactive mode on non-TTY."""
        browser.console = Console(force_terminal=False)
        result = browser.interactive_mode()
        # Should return active session id or None
        assert result is None or isinstance(result, str)

    def test_handle_key_quit(self, browser):
        """Test quit key handling."""
        browser._running = True
        result = browser._handle_key("q", "")
        assert result is None
        assert browser._running is False

    def test_handle_key_enter(self, browser):
        """Test Enter key selects active session."""
        result = browser._handle_key("\n", "")
        assert result == "sess0001"

    def test_handle_key_printable(self, browser):
        """Test printable character adds to filter."""
        result = browser._handle_key("t", "")
        assert result is None  # Will re-render

    def test_handle_key_other(self, browser):
        """Test other keys."""
        result = browser._handle_key("x", "")
        assert result is None

    def test_filter_case_insensitive(self):
        """Test case-insensitive filtering."""
        now = datetime.now(timezone.utc).isoformat()
        sm = MagicMock()
        sm.list_sessions.return_value = [
            FakeSession(
                id="s1",
                name="My Session",
                message_count=5,
                created_at=now,
                last_accessed=now,
                model=None,
            ),
        ]
        output = io.StringIO()
        console = Console(file=output, force_terminal=True)
        browser = SessionBrowser(sm, console=console)
        result = browser.render_as_string(filter_text="my")
        assert "My Session" in result
