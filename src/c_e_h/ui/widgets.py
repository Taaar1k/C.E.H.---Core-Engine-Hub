"""Reusable Rich widgets for C.E.H. UI components.

Provides:
- StatusBadge: Colored badge for agent state (running, idle, error)
- MetricRow: Formatted key-value metric display
- MessageBubble: Styled message container with role indicator
- ProgressBar: Animated progress indicator

All widgets support monochrome fallback and 256-color terminals.
"""

from __future__ import annotations

import logging
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.text import Text

logger = logging.getLogger(__name__)

# Agent state colors for 256-color terminals
# Format: (bright_color_code, dim_color_code, label)
_STATE_COLORS: dict[str, tuple[str, str, str]] = {
    "running": ("green", "dim green", "RUNNING"),
    "idle": ("yellow", "dim yellow", "IDLE"),
    "error": ("red", "dim red", "ERROR"),
    "loading": ("cyan", "dim cyan", "LOADING"),
    "stopped": ("white", "dim white", "STOPPED"),
    "approval": ("magenta", "dim magenta", "APPROVAL"),
}

# Role colors for message bubbles
_ROLE_COLORS: dict[str, tuple[str, str]] = {
    "user": ("bold cyan", "cyan"),
    "assistant": ("bold green", "green"),
    "system": ("bold magenta", "magenta"),
    "tool": ("bold yellow", "yellow"),
}


class StatusBadge:
    """Colored badge for agent state display.

    Renders a compact status indicator with color-coded background
    and text. Falls back to text-only representation on monochrome
    terminals.

    Attributes:
        state: The agent state string (running, idle, error, loading, stopped, approval).
        console: Rich Console instance for rendering.

    Example:
        >>> badge = StatusBadge("running")
        >>> console.print(badge.render())
    """

    def __init__(self, state: str = "idle", console: Optional[Console] = None) -> None:
        """Initialize StatusBadge.

        Args:
            state: Agent state identifier.
            console: Rich Console instance. Uses default if None.
        """
        self.state = state.lower()
        self.console = console or Console()

    def render(self) -> Text:
        """Render the status badge as Rich Text.

        Returns:
            Text object with appropriate styling.
        """
        colors = _STATE_COLORS.get(self.state, ("white", "dim white", self.state.upper()))
        bright_color, dim_color, label = colors

        # Check if terminal supports color
        if self.console.no_color:
            return Text(f" [{label}] ", style="bold")

        return Text(f" ● {label} ", style=f"bold {bright_color} on black")

    def render_as_panel(self, title: Optional[str] = None) -> Panel:
        """Render the status badge as a Panel.

        Args:
            title: Optional panel title.

        Returns:
            Rich Panel with status badge.
        """
        badge_text = self.render()
        if title:
            return Panel(badge_text, title=title, border_style="green")
        return Panel(badge_text, border_style="green")

    def get_color(self) -> str:
        """Get the primary color for this state.

        Returns:
            Color name string for use in Rich styling.
        """
        colors = _STATE_COLORS.get(self.state, ("white", "dim white", self.state.upper()))
        return colors[0]


class MetricRow:
    """Formatted key-value metric display.

    Renders a single metric as a formatted row with label and value.
    Supports optional unit suffixes and color coding.

    Attributes:
        label: Metric label (e.g., "Tokens", "Speed").
        value: Metric value (number or string).
        unit: Optional unit suffix (e.g., "tok/s", "ms").
        console: Rich Console instance for rendering.

    Example:
        >>> row = MetricRow("Speed", 42.5, "tok/s")
        >>> console.print(row.render())
        # Output: Tokens: 128  Prompt: 64  Prompt: 0.032s  Gen: 1.234s  Speed: 42.5 tok/s
    """

    def __init__(
        self,
        label: str,
        value: float | int | str,
        unit: Optional[str] = None,
        console: Optional[Console] = None,
    ) -> None:
        """Initialize MetricRow.

        Args:
            label: Metric label.
            value: Metric value.
            unit: Optional unit suffix.
            console: Rich Console instance.
        """
        self.label = label
        self.value = value
        self.unit = unit
        self.console = console or Console()

    def render(self) -> Text:
        """Render the metric row as Rich Text.

        Returns:
            Text object with formatted metric.
        """
        value_str = str(self.value)
        if self.unit:
            value_str = f"{self.value} {self.unit}"

        if self.console.no_color:
            return Text(f"{self.label}: {value_str}", style="dim")

        return Text(f"{self.label}: ", style="dim") + Text(value_str, style="bold")

    @staticmethod
    def render_multiple(metrics: list["MetricRow"], console: Optional[Console] = None) -> Text:
        """Render multiple metric rows on a single line.

        Args:
            metrics: List of MetricRow instances.
            console: Rich Console instance.

        Returns:
            Combined Text object with all metrics separated by spaces.
        """
        console = console or Console()
        parts: list[str] = []
        for m in metrics:
            value_str = str(m.value)
            if m.unit:
                value_str = f"{m.value} {m.unit}"
            if console.no_color:
                parts.append(f"{m.label}: {value_str}")
            else:
                parts.append(f"[dim]{m.label}:[/dim] {value_str}")
        footer = "  ".join(parts)
        return Text(footer)


class MessageBubble:
    """Styled message container with role indicator.

    Renders a message in a Panel with role-specific styling.
    Supports truncation for long messages and color coding.

    Attributes:
        role: Message role (user, assistant, system, tool).
        content: Message content string.
        max_width: Maximum panel width.
        console: Rich Console instance for rendering.

    Example:
        >>> bubble = MessageBubble("user", "Hello, agent!")
        >>> console.print(bubble.render())
    """

    def __init__(
        self,
        role: str,
        content: str,
        max_width: int = 80,
        console: Optional[Console] = None,
    ) -> None:
        """Initialize MessageBubble.

        Args:
            role: Message role identifier.
            content: Message content.
            max_width: Maximum panel width in characters.
            console: Rich Console instance.
        """
        self.role = role.lower()
        self.content = content
        self.max_width = max_width
        self.console = console or Console()

    def render(self) -> Panel:
        """Render the message bubble as a Panel.

        Returns:
            Rich Panel with styled message content.
        """
        colors = _ROLE_COLORS.get(self.role, ("white", "dim white"))
        bright_color, _ = colors

        # Truncate long content
        content = self.content
        max_content = self.max_width - 10
        if len(content) > max_content:
            content = content[:max_content - 3] + "..."

        # Role label
        role_label = self.role.upper()
        if self.console.no_color:
            title = f"{role_label}"
        else:
            title = f"[{bright_color}]{role_label}[/{bright_color}]"

        return Panel(
            content,
            title=title,
            border_style=bright_color,
            expand=True,
            padding=(0, 1),
        )

    @staticmethod
    def render_conversation(
        messages: list[dict[str, str]],
        console: Optional[Console] = None,
        max_width: int = 80,
    ) -> None:
        """Render a list of messages in conversation order.

        Args:
            messages: List of dicts with 'role' and 'content' keys.
            console: Rich Console instance.
            max_width: Maximum panel width.
        """
        console = console or Console()
        for msg in messages:
            role = msg.get("role", "system")
            content = msg.get("content", "")
            bubble = MessageBubble(role, content, max_width=max_width, console=console)
            console.print(bubble.render())


class ProgressBar:
    """Animated progress indicator for Rich console.

    Provides a configurable progress bar with spinner, elapsed time,
    and completion percentage. Supports both numeric and indeterminate modes.

    Attributes:
        description: Progress bar description text.
        total: Total value for completion calculation (None = indeterminate).
        console: Rich Console instance for rendering.
        speed: Optional speed display (items per second).

    Example:
        >>> with ProgressBar("Processing", total=100) as progress:
        ...     for i in range(100):
        ...         progress.update(i + 1)
    """

    def __init__(
        self,
        description: str = "Processing",
        total: Optional[float] = None,
        console: Optional[Console] = None,
        speed: bool = False,
    ) -> None:
        """Initialize ProgressBar.

        Args:
            description: Progress bar description.
            total: Total value (None for indeterminate/spinner mode).
            console: Rich Console instance.
            speed: Whether to show items-per-second speed.
        """
        self.description = description
        self.total = total
        self.console = console or Console()
        self.speed = speed
        self._progress: Optional[Progress] = None

    def __enter__(self) -> "ProgressBar":
        """Enter context manager and start progress display."""
        columns = [
            SpinnerColumn() if self.total is None else TextColumn("{task.description}"),
            BarColumn() if self.total is not None else None,
            MofNCompleteColumn() if self.total is not None else None,
            TimeElapsedColumn(),
        ]
        if self.speed:
            columns.append(TextColumn("{task.fields[speed]:.1f}/s"))

        # Filter out None columns
        columns = [c for c in columns if c is not None]

        self._progress = Progress(
            *columns,
            console=self.console,
            transient=False,
        )
        self._progress.start()

        task_id = self._progress.add_task(
            self.description,
            total=self.total,
            speed=0,
            visible=not self.console.quiet,
        )
        self._task_id = task_id
        return self

    def __exit__(self, *args: object) -> None:
        """Exit context manager and stop progress display."""
        if self._progress is not None:
            self._progress.stop()
            self._progress = None

    def update(self, completed: float, speed: Optional[float] = None) -> None:
        """Update progress bar completion.

        Args:
            completed: Current completed value.
            speed: Optional items-per-second display value.
        """
        if self._progress is not None:
            extra_fields: dict[str, float] = {}
            if speed is not None:
                extra_fields["speed"] = speed
            self._progress.update(
                self._task_id,
                completed=completed,
                **extra_fields,
            )

    @staticmethod
    def render_loading(console: Optional[Console] = None, text: str = "Loading") -> Text:
        """Render a static loading indicator text.

        Args:
            console: Rich Console instance.
            text: Loading text to display.

        Returns:
            Text object with loading indicator.
        """
        console = console or Console()
        if console.no_color:
            return Text(f"[{text}...]")
        return Text(f" [cyan]{text}...[/cyan] ", style="bold")

    @staticmethod
    def render_token_speed_graph(speeds: list[float], max_width: int = 30) -> Text:
        """Render an ASCII-based token speed graph.

        Creates a simple bar chart from a list of token-per-second values,
        useful for visualizing generation speed over time.

        Args:
            speeds: List of tokens-per-second values (most recent last).
            max_width: Maximum graph width in characters.

        Returns:
            Text object with ASCII bar chart.
        """
        if not speeds:
            return Text("[dim]No speed data[/dim]")

        console = Console()
        if console.no_color:
            # Monochrome fallback
            max_val = max(speeds) if speeds else 1
            bars = ""
            for s in speeds[-max_width:]:
                bar_len = int((s / max_val) * max_width) if max_val > 0 else 0
                bars += "█" * max(bar_len, 1)
            return Text(f"Speed: {bars} (max: {max_val:.1f} tok/s)")

        # Color-coded graph
        max_val = max(speeds) if speeds else 1
        parts: list[str] = []
        for s in speeds[-max_width:]:
            bar_len = max(int((s / max_val) * max_width), 1) if max_val > 0 else 1
            # Color intensity based on speed
            ratio = s / max_val if max_val > 0 else 0
            if ratio > 0.7:
                color = "green"
            elif ratio > 0.4:
                color = "yellow"
            else:
                color = "red"
            parts.append(f"[{color}]" + "█" * bar_len + "[/]")

        avg_speed = sum(speeds) / len(speeds)
        return Text(f"Speed: {''.join(parts)} (avg: {avg_speed:.1f} tok/s)")
