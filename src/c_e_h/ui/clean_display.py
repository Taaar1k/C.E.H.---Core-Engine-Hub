"""Clean chat display module for C.E.H.

Provides ``CleanChatDisplay`` — a minimal, user-friendly display that shows
only the final assistant response while an animated spinner indicates
processing status.  Tool calls, tool results, and model reasoning tags are
silently filtered from the user-facing output and logged at DEBUG level
instead.
"""

from __future__ import annotations

import logging
import re
import sys
from contextlib import contextmanager
from typing import Generator, Optional

from rich.console import Console
from rich.live import Live
from rich.spinner import SpinnerColumn
from rich.text import Text
from rich.tree import Tree

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns for stripping internal model output
# ---------------------------------------------------------------------------

_THINKING_TAG_RE = re.compile(r"<thinking>.*?</thinking>", re.DOTALL)
_INTERNAL_PROMPT_TAG_RE = re.compile(
    r"<internal_prompt>.*?</internal_prompt>", re.DOTALL
)
_TOOL_CALL_TAG_RE = re.compile(r"<tool_call>.*?</tool_call>", re.DOTALL)
_TOOL_RESULT_TAG_RE = re.compile(r"<tool_result>.*?</tool_result>", re.DOTALL)


def strip_internal_tags(text: str) -> str:
    """Remove model reasoning and tool-call tags from output text.

    Strips the following XML-like tags and their content:
    - ``<thinking>...</thinking>``
    - ``<internal_prompt>...</internal_prompt>``
    - ``<tool_call>...</tool_call>``
    - ``<tool_result>...</tool_result>``

    Args:
        text: Raw model output that may contain internal tags.

    Returns:
        Cleaned text with all internal tags removed.
    """
    text = _THINKING_TAG_RE.sub("", text)
    text = _INTERNAL_PROMPT_TAG_RE.sub("", text)
    text = _TOOL_CALL_TAG_RE.sub("", text)
    text = _TOOL_RESULT_TAG_RE.sub("", text)
    # Collapse excessive whitespace left by tag removal
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def log_tool_activity(text: str) -> None:
    """Log any tool-call or tool-result content found in raw text at DEBUG level.

    This is a no-op if no tool-related tags are present.

    Args:
        text: Raw model output to scan for tool activity.
    """
    for tag_name, pattern in [
        ("tool_call", _TOOL_CALL_TAG_RE),
        ("tool_result", _TOOL_RESULT_TAG_RE),
    ]:
        matches = pattern.findall(text)
        for match in matches:
            logger.debug("Silent %s: %s", tag_name, match[:200])


# ---------------------------------------------------------------------------
# CleanChatDisplay
# ---------------------------------------------------------------------------

_STATUS_LABELS = [
    "Thinking...",
    "Processing...",
    "Complete",
]


class CleanChatDisplay:
    """Minimal chat display with animated spinner.

    Shows only the final assistant response to the user.  During
    processing a spinner with a status label is displayed via
    ``rich.Live``.

    Tool calls, tool results, and model reasoning tags are stripped
    from the user-facing output and logged at DEBUG level.

    Attributes:
        console: The Rich Console instance used for output.
        _live: The active ``rich.Live`` context (None when spinner is stopped).
        _spinner: The spinner object controlling the animation.
    """

    def __init__(self, console: Optional[Console] = None) -> None:
        """Initialize the clean chat display.

        Args:
            console: Optional Rich Console.  Defaults to a new Console.
        """
        self.console = console or Console()
        self._live: Optional[Live] = None
        self._spinner: Optional[SpinnerColumn] = None

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    @contextmanager
    def live_spinner(
        self,
        status: str = "Thinking...",
    ) -> Generator[None, None, None]:
        """Context manager that shows a spinner while processing.

        Starts the spinner on entry and stops it on exit, leaving
        ``_live`` in a clean state.

        Args:
            status: Initial status label (default ``"Thinking..."``).

        Yields:
            None — use this block for processing that should show the spinner.
        """
        self.start(status=status)
        try:
            yield
        finally:
            self.stop()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, status: str = "Thinking...") -> None:
        """Start the animated spinner with a status label.

        Creates a ``rich.Live`` instance with a ``SpinnerColumn("dots")``
        and a ``TextColumn`` showing the status description.

        Args:
            status: Status label to display next to the spinner.
        """
        if self.console.is_terminal:
            self._spinner = SpinnerColumn("dots")
            from rich.text import Text as RichText
            from rich.console import TextColumn

            task_desc = Text(status)
            text_col = TextColumn("{task.description}")
            self._live = Live(
                self._spinner.render_task(
                    self._live.console,
                    self._live.add_task("", description=task_desc) if self._live else None,
                )
                if self._live
                else None,
                console=self.console,
                refresh_per_second=8,
                transient=False,
            )
            # Simpler approach: create Live with a placeholder and update
            if self._live is None:
                from rich.live import Live as RichLive
                from rich.spinner import SpinnerColumn as SC
                from rich.text import Text as RichText
                from rich.console import TextColumn as TC

                placeholder = Text(status)
                self._live = RichLive(
                    placeholder,
                    console=self.console,
                    refresh_per_second=8,
                    transient=False,
                )
                self._live.start()
                # Replace with spinner
                spinner_col = SC("dots")
                task = self._live.add_task("", description=Text(status))
                self._live.update(
                    spinner_col.render(self._live.console, task),
                )
        else:
            # Non-TTY: print status line
            self.console.print(f"[dim]{status}[/dim]")

    def update_status(self, status: str) -> None:
        """Update the spinner status label without stopping the spinner.

        Uses ``rich.Live.update()`` for non-blocking status changes.

        Args:
            status: New status label to display.
        """
        if self._live is not None and self.console.is_terminal:
            from rich.text import Text as RichText
            from rich.spinner import SpinnerColumn as SC

            if self._spinner is not None:
                # Find the first task and update its description
                tasks = list(self._live.tasks)
                if tasks:
                    task = tasks[0]
                    self._live.update(
                        self._spinner.render(self._live.console, task),
                    )
            # Fallback: just update the display text
            self._live.update(Text(status))
        else:
            self.console.print(f"[dim]{status}[/dim]")

    def stop(self, final_text: str = "") -> None:
        """Stop the spinner and optionally display final text.

        Clears the live display and prints the final response text
        if provided.

        Args:
            final_text: Optional final text to display after spinner stops.
        """
        if self._live is not None:
            self._live.stop()
            self._live = None
            self._spinner = None
        if final_text:
            self.console.print(final_text)

    def display_error(self, message: str) -> None:
        """Display an error state with red spinner and exception message.

        Stops the spinner, shows "Error" in red, and prints the
        exception message.

        Args:
            message: The exception or error message to display.
        """
        if self._live is not None:
            from rich.text import Text

            self._live.update(Text("[red]Error[/red]"))
            self._live.stop()
            self._live = None
            self._spinner = None
        self.console.print(f"[red]Error: {message}[/red]")

    def display_response(self, text: str) -> None:
        """Display the final cleaned response to the user.

        Strips internal tags from *text* before printing.  Tool-call
        and reasoning content is logged at DEBUG level.

        Args:
            text: Raw model output (may contain internal tags).
        """
        log_tool_activity(text)
        cleaned = strip_internal_tags(text)
        self.console.print(cleaned)

    def process_with_spinner(
        self,
        work_fn: callable,
        status_updates: list[tuple[int, str]] | None = None,
    ) -> str:
        """Run a work function with spinner and optional status updates.

        Starts spinner, runs *work_fn*, strips internal tags from the
        result, and returns the cleaned response.

        Args:
            work_fn: Callable that returns a string (raw model output).
            status_updates: List of ``(step_index, status_label)`` tuples
                for updating the spinner status during execution.

        Returns:
            Cleaned response text with internal tags removed.
        """
        self.start("Thinking...")
        try:
            status_updates = status_updates or []
            raw_output = work_fn()

            # Apply status updates at specified steps
            for step_idx, status in status_updates:
                if step_idx == 0:  # Simplified: just apply first update
                    self.update_status(status)

            # Log any tool activity found
            log_tool_activity(raw_output)

            # Strip internal tags
            cleaned = strip_internal_tags(raw_output)
            return cleaned
        except Exception as e:
            self.display_error(str(e))
            raise
        finally:
            if self._live is not None:
                self.update_status("Complete")
                self.stop()
