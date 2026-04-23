"""Interactive dashboard for C.E.H. — Real-time agent state monitoring.

Provides ``Dashboard`` class using ``rich.Live`` for real-time updates
with multi-panel layout:
- Agent status panel with state badge
- Active session panel with session info
- Recent messages panel with conversation history
- Metrics panel with performance indicators

Keyboard shortcuts:
- ``q``: Quit dashboard
- ``s``: Switch session (opens session browser)
- ``c``: Clear context
- ``?``: Show help overlay

Auto-refresh every 2 seconds (configurable).
Graceful fallback to text mode on non-TTY.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Optional

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

if TYPE_CHECKING:
    from c_e_h.agent import Agent
    from c_e_h.session_manager import SessionManager

from c_e_h.ui.widgets import MessageBubble, MetricRow, StatusBadge

logger = logging.getLogger(__name__)

# Help text displayed when user presses '?'
_HELP_TEXT = """
[bold]Dashboard Controls:[/bold]
  [cyan]q[/cyan]             Quit dashboard
  [cyan]s[/cyan]             Switch session
  [cyan]c[/cyan]             Clear context
  [cyan]?[/cyan]             Show this help
  [cyan]r[/cyan]             Refresh now
"""


class Dashboard:
    """Interactive real-time dashboard for CEH agent monitoring.

    Renders a multi-panel layout with agent status, session info,
    recent messages, and performance metrics. Updates automatically
    at configurable refresh rate.

    Attributes:
        agent: The Agent instance to monitor.
        session_manager: Optional SessionManager for session info.
        refresh_interval: Seconds between auto-refresh (default 2).
        console: Rich Console instance.
        _layout: Current dashboard layout.
        _help_visible: Whether help overlay is shown.
        _last_update: Timestamp of last dashboard update.
        _max_messages: Maximum recent messages to display.

    Example:
        >>> from c_e_h.agent import Agent
        >>> agent = Agent()
        >>> dashboard = Dashboard(agent)
        >>> dashboard.run()
    """

    def __init__(
        self,
        agent: "Agent",
        session_manager: Optional["SessionManager"] = None,
        refresh_interval: float = 2.0,
        console: Optional[Console] = None,
        max_messages: int = 5,
    ) -> None:
        """Initialize Dashboard.

        Args:
            agent: The Agent instance to monitor.
            session_manager: Optional SessionManager for session info.
            refresh_interval: Seconds between auto-refresh.
            console: Rich Console instance.
            max_messages: Maximum recent messages to display.
        """
        self.agent = agent
        self.session_manager = session_manager
        self.refresh_interval = refresh_interval
        self.console = console or Console()
        self._max_messages = max_messages
        self._layout: Optional[Layout] = None
        self._help_visible = False
        self._last_update = 0.0
        self._running = False

    def run(self) -> None:
        """Run the interactive dashboard.

        Starts the live dashboard display loop. Handles keyboard input
        for navigation and control. Exits on 'q' key or EOF.

        Raises:
            KeyboardInterrupt: If user presses Ctrl+C.
        """
        if self.console.is_terminal:
            self._run_interactive()
        else:
            self._run_text_mode()

    def _run_interactive(self) -> None:
        """Run the interactive TUI dashboard with Live display."""
        self._running = True
        self._layout = self._create_initial_layout()

        with Live(
            self._layout,
            console=self.console,
            refresh_per_second=max(1.0 / self.refresh_interval, 0.5),
            transient=False,
            screen=False,
        ) as live:
            while self._running:
                try:
                    # Check if we need to update
                    now = time.time()
                    if now - self._last_update >= self.refresh_interval or self._help_visible:
                        self._update_layout()
                        self._last_update = now
                        live.update(self._layout)

                    # Check for keyboard input (non-blocking)
                    import select
                    import sys

                    if sys.stdin.isatty():
                        ready, _, _ = select.select([sys.stdin], [], [], 0.1)
                        if ready:
                            key = sys.stdin.read(1)
                            self._handle_key(key)

                except (EOFError, KeyboardInterrupt):
                    self._running = False
                    break

    def _run_text_mode(self) -> None:
        """Run in text-only mode (non-TTY fallback).

        Prints the dashboard state once and exits.
        """
        self._print_text_dashboard()

    def _handle_key(self, key: str) -> None:
        """Handle keyboard input.

        Args:
            key: Single character key pressed.
        """
        if key in ("q", "Q"):
            self._running = False
            self.console.print("\n[dim]Dashboard stopped.[/dim]")
        elif key in ("s", "S"):
            self.console.print("\n[dim]Session switching not yet implemented.[/dim]")
        elif key in ("c", "C"):
            self.agent.state.context.clear()
            self.console.print("[dim]Context cleared.[/dim]")
            self._update_layout()
        elif key in ("?", "h", "H"):
            self._help_visible = not self._help_visible
            self._update_layout()
        elif key in ("r", "R"):
            self._last_update = 0  # Force immediate refresh

    def _create_initial_layout(self) -> Layout:
        """Create the initial dashboard layout.

        Returns:
            Rich Layout with all panels.
        """
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3),
        )
        layout["main"].split_row(
            Layout(name="left"),
            Layout(name="right"),
        )
        layout["left"].split_column(
            Layout(name="agent_status", size=4),
            Layout(name="session_info", size=6),
            Layout(name="recent_messages"),
        )
        layout["right"].split_column(
            Layout(name="metrics", size=8),
            Layout(name="help", size=10),
        )

        self._update_layout()
        return layout

    def _update_layout(self) -> None:
        """Update all panels in the dashboard layout."""
        if self._layout is None:
            return

        # Header
        self._layout["header"].update(self._build_header())

        # Agent status
        self._layout["agent_status"].update(self._build_agent_status())

        # Session info
        self._layout["session_info"].update(self._build_session_info())

        # Recent messages
        self._layout["recent_messages"].update(self._build_recent_messages())

        # Metrics
        self._layout["metrics"].update(self._build_metrics())

        # Help
        if self._help_visible:
            self._layout["help"].update(Panel(_HELP_TEXT, title="Help", border_style="cyan"))
        else:
            self._layout["help"].update(Panel("[dim]Press '?' for help[/dim]", border_style="dim"))

    def _build_header(self) -> Panel:
        """Build the dashboard header panel.

        Returns:
            Rich Panel with title and timestamp.
        """
        now = time.strftime("%H:%M:%S")
        header_text = Text(f" C.E.H. Dashboard — {now} ", style="bold blue")
        return Panel(
            header_text,
            title="[bold]CEH Monitor[/bold]",
            border_style="blue",
            expand=True,
        )

    def _build_agent_status(self) -> Panel:
        """Build the agent status panel.

        Returns:
            Rich Panel with agent state badge and info.
        """
        state = self.agent.state
        badge = StatusBadge(state.mode, console=self.console)

        status_lines: list[str] = []
        status_lines.append(f"  {badge.render().plain}")
        status_lines.append(f"  Steps: {state.step_count}")
        status_lines.append(f"  Errors: {state.auto_errors}")
        status_lines.append(f"  Context: {len(state.context)} messages")
        if state.last_response:
            last = state.last_response[:50]
            if len(state.last_response) > 50:
                last += "..."
            status_lines.append(f"  Last: {last}")

        content = Text("\n".join(status_lines))
        return Panel(content, title="[bold]Agent Status[/bold]", border_style=badge.get_color())

    def _build_session_info(self) -> Panel:
        """Build the session info panel.

        Returns:
            Rich Panel with current session information.
        """
        if self.session_manager is None:
            return Panel(
                "[dim]Session manager not configured[/dim]",
                title="[bold]Session[/bold]",
                border_style="dim",
            )

        # Try to get current session from context or list most recent
        session_info = self._get_current_session_info()

        content = Text(session_info)
        return Panel(content, title="[bold]Session[/bold]", border_style="green")

    def _get_current_session_info(self) -> str:
        """Get current session information string.

        Returns:
            Formatted session info text.
        """
        try:
            sessions = self.session_manager.list_sessions()
            if sessions:
                latest = sessions[0]
                lines = [
                    f"  ID: {latest.id}",
                    f"  Name: {latest.name}",
                    f"  Messages: {latest.message_count}",
                    f"  Created: {latest.created_at[:19]}",
                    f"  Last: {latest.last_accessed[:19]}",
                ]
                if latest.model:
                    lines.append(f"  Model: {latest.model}")
                return "\n".join(lines)
            return "  No sessions found"
        except Exception as e:
            return f"  Error: {e}"

    def _build_recent_messages(self) -> Panel:
        """Build the recent messages panel.

        Returns:
            Rich Panel with last N messages from agent context.
        """
        context = self.agent.state.context
        if not context:
            content = Text("  No messages yet", style="dim")
            return Panel(content, title="[bold]Recent Messages[/bold]", border_style="dim")

        # Get last N messages
        recent = context[-self._max_messages:]
        bubbles = []
        for msg in recent:
            role = msg.get("role", "system")
            content = msg.get("content", "")
            bubble = MessageBubble(role, content, console=self.console)
            bubbles.append(bubble.render())

        # If multiple bubbles, combine them
        if len(bubbles) == 1:
            return Panel(bubbles[0], title="[bold]Recent Messages[/bold]", border_style="cyan")

        # For multiple messages, show them in a combined panel
        lines: list[str] = []
        for msg in recent:
            role = msg.get("role", "system").upper()
            content = msg.get("content", "")[:60]
            if len(msg.get("content", "")) > 60:
                content += "..."
            lines.append(f"[{role}] {content}")

        content = Text("\n".join(lines))
        return Panel(content, title=f"[bold]Recent Messages ({len(recent)})[/bold]", border_style="cyan")

    def _build_metrics(self) -> Panel:
        """Build the metrics panel.

        Returns:
            Rich Panel with performance metrics.
        """
        state = self.agent.state
        metrics: list[MetricRow] = [
            MetricRow("Steps", state.step_count),
            MetricRow("Errors", state.auto_errors),
            MetricRow("Context", len(state.context)),
        ]

        # Estimate tokens from context
        total_chars = sum(len(m.get("content", "")) for m in state.context)
        estimated_tokens = max(total_chars // 4, 0)  # Rough estimate: 4 chars per token
        metrics.append(MetricRow("Est. Tokens", estimated_tokens))

        content = MetricRow.render_multiple(metrics, self.console)
        return Panel(content, title="[bold]Metrics[/bold]", border_style="yellow")

    def _print_text_dashboard(self) -> None:
        """Print a static text dashboard (non-TTY fallback)."""
        console = self.console
        console.print(Panel("C.E.H. Dashboard", title="CEH Monitor", border_style="blue"))
        console.print()

        # Agent status
        state = self.agent.state
        badge = StatusBadge(state.mode, console=console)
        console.print(f"Agent: {badge.render().plain}")
        console.print(f"  Steps: {state.step_count}")
        console.print(f"  Errors: {state.auto_errors}")
        console.print(f"  Context: {len(state.context)} messages")
        console.print()

        # Session info
        if self.session_manager:
            console.print("[bold]Sessions:[/bold]")
            try:
                sessions = self.session_manager.list_sessions()
                for s in sessions[:5]:
                    console.print(f"  {s.id} — {s.name} ({s.message_count} msgs)")
            except Exception as e:
                console.print(f"  [dim]Error: {e}[/dim]")
        console.print()

        # Recent messages
        if self.agent.state.context:
            console.print("[bold]Recent Messages:[/bold]")
            for msg in self.agent.state.context[-3:]:
                role = msg.get("role", "system").upper()
                content = msg.get("content", "")[:80]
                console.print(f"  [{role}] {content}")

    def stop(self) -> None:
        """Stop the dashboard."""
        self._running = False
