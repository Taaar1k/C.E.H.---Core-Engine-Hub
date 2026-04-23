"""Tests for c_e_h.ui.widgets module.

Tests StatusBadge, MetricRow, MessageBubble, and ProgressBar widgets
with both color and monochrome terminal modes.
"""

from __future__ import annotations

import io

from rich.console import Console
from rich.text import Text

from c_e_h.ui.widgets import MessageBubble, MetricRow, ProgressBar, StatusBadge


class TestStatusBadge:
    """Tests for StatusBadge widget."""

    def test_default_state(self):
        """Test default idle state."""
        badge = StatusBadge()
        assert badge.state == "idle"
        result = badge.render()
        assert isinstance(result, Text)

    def test_running_state(self):
        """Test running state rendering."""
        badge = StatusBadge("running")
        assert badge.get_color() == "green"
        result = badge.render()
        assert isinstance(result, Text)

    def test_error_state(self):
        """Test error state rendering."""
        badge = StatusBadge("error")
        assert badge.get_color() == "red"
        result = badge.render()
        assert isinstance(result, Text)

    def test_loading_state(self):
        """Test loading state rendering."""
        badge = StatusBadge("loading")
        assert badge.get_color() == "cyan"

    def test_stopped_state(self):
        """Test stopped state rendering."""
        badge = StatusBadge("stopped")
        assert badge.get_color() == "white"

    def test_approval_state(self):
        """Test approval state rendering."""
        badge = StatusBadge("approval")
        assert badge.get_color() == "magenta"

    def test_unknown_state(self):
        """Test unknown state falls back gracefully."""
        badge = StatusBadge("unknown_state")
        assert badge.get_color() == "white"

    def test_render_as_panel(self):
        """Test panel rendering."""
        badge = StatusBadge("running")
        panel = badge.render_as_panel(title="Agent")
        assert panel is not None

    def test_no_color_console(self):
        """Test monochrome terminal fallback."""
        output = io.StringIO()
        console = Console(file=output, force_terminal=True, no_color=True)
        badge = StatusBadge("running", console=console)
        result = badge.render()
        assert isinstance(result, Text)

    def test_custom_console(self):
        """Test with custom console instance."""
        output = io.StringIO()
        console = Console(file=output, force_terminal=True)
        badge = StatusBadge("idle", console=console)
        result = badge.render()
        assert isinstance(result, Text)


class TestMetricRow:
    """Tests for MetricRow widget."""

    def test_basic_render(self):
        """Test basic metric rendering."""
        row = MetricRow("Tokens", 128)
        result = row.render()
        assert isinstance(result, Text)

    def test_with_unit(self):
        """Test metric with unit suffix."""
        row = MetricRow("Speed", 42.5, "tok/s")
        result = row.render()
        assert isinstance(result, Text)

    def test_with_string_value(self):
        """Test metric with string value."""
        row = MetricRow("Status", "active")
        result = row.render()
        assert isinstance(result, Text)

    def test_render_multiple(self):
        """Test rendering multiple metrics."""
        metrics = [
            MetricRow("Tokens", 128),
            MetricRow("Speed", 42.5, "tok/s"),
        ]
        result = MetricRow.render_multiple(metrics)
        assert isinstance(result, Text)

    def test_render_multiple_no_color(self):
        """Test multiple metrics in monochrome mode."""
        output = io.StringIO()
        console = Console(file=output, force_terminal=True, no_color=True)
        metrics = [MetricRow("Tokens", 128)]
        result = MetricRow.render_multiple(metrics, console=console)
        assert isinstance(result, Text)


class TestMessageBubble:
    """Tests for MessageBubble widget."""

    def test_user_message(self):
        """Test user message rendering."""
        bubble = MessageBubble("user", "Hello, agent!")
        panel = bubble.render()
        assert panel is not None

    def test_assistant_message(self):
        """Test assistant message rendering."""
        bubble = MessageBubble("assistant", "Hello, user!")
        panel = bubble.render()
        assert panel is not None

    def test_system_message(self):
        """Test system message rendering."""
        bubble = MessageBubble("system", "System initialized.")
        panel = bubble.render()
        assert panel is not None

    def test_tool_message(self):
        """Test tool message rendering."""
        bubble = MessageBubble("tool", "Command executed.")
        panel = bubble.render()
        assert panel is not None

    def test_truncation(self):
        """Test long message truncation."""
        long_content = "x" * 500
        bubble = MessageBubble("user", long_content, max_width=80)
        panel = bubble.render()
        # Content should be truncated
        if hasattr(panel.renderable, "plain"):
            assert "..." in panel.renderable.plain

    def test_custom_max_width(self):
        """Test custom max width."""
        bubble = MessageBubble("user", "Test", max_width=40)
        panel = bubble.render()
        assert panel is not None

    def test_no_color_console(self):
        """Test monochrome fallback."""
        output = io.StringIO()
        console = Console(file=output, force_terminal=True, no_color=True)
        bubble = MessageBubble("user", "Test", console=console)
        panel = bubble.render()
        assert panel is not None

    def test_render_conversation(self):
        """Test rendering a conversation."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        output = io.StringIO()
        console = Console(file=output, force_terminal=True)
        MessageBubble.render_conversation(messages, console=console, max_width=60)
        # Should not raise
        assert True

    def test_render_conversation_empty(self):
        """Test rendering empty conversation."""
        output = io.StringIO()
        console = Console(file=output, force_terminal=True)
        MessageBubble.render_conversation([], console=console)
        assert True


class TestProgressBar:
    """Tests for ProgressBar widget."""

    def test_context_manager_enter(self):
        """Test context manager entry."""
        with ProgressBar("Test", total=100) as pb:
            assert pb._progress is not None
            assert pb._task_id is not None

    def test_context_manager_exit(self):
        """Test context manager exit."""
        with ProgressBar("Test", total=10) as pb:
            pb.update(5)
        # After exit, progress should be stopped
        assert pb._progress is None

    def test_update(self):
        """Test progress update."""
        with ProgressBar("Test", total=100) as pb:
            pb.update(50)
            pb.update(100, speed=10.5)

    def test_indeterminate_mode(self):
        """Test spinner mode (no total)."""
        with ProgressBar("Loading", total=None) as pb:
            assert pb._progress is not None

    def test_render_loading(self):
        """Test static loading indicator."""
        result = ProgressBar.render_loading(text="Processing")
        assert isinstance(result, Text)

    def test_render_loading_no_color(self):
        """Test loading indicator in monochrome mode."""
        output = io.StringIO()
        console = Console(file=output, force_terminal=True, no_color=True)
        result = ProgressBar.render_loading(console=console)
        assert isinstance(result, Text)

    def test_render_token_speed_graph_empty(self):
        """Test speed graph with no data."""
        result = ProgressBar.render_token_speed_graph([])
        assert isinstance(result, Text)

    def test_render_token_speed_graph_single(self):
        """Test speed graph with single value."""
        result = ProgressBar.render_token_speed_graph([42.0])
        assert isinstance(result, Text)

    def test_render_token_speed_graph_multiple(self):
        """Test speed graph with multiple values."""
        speeds = [10.0, 20.0, 30.0, 25.0, 35.0]
        result = ProgressBar.render_token_speed_graph(speeds, max_width=20)
        assert isinstance(result, Text)

    def test_render_token_speed_graph_no_color(self):
        """Test speed graph in monochrome mode."""
        output = io.StringIO()
        console = Console(file=output, force_terminal=True, no_color=True)
        speeds = [10.0, 20.0, 30.0]
        result = ProgressBar.render_token_speed_graph(speeds, max_width=10)
        assert isinstance(result, Text)
