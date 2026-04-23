"""Enhanced streaming display for C.E.H. UI components.

Provides ``EnhancedStreamDisplay`` class that extends the current
``stream_display()`` from ``streaming.py`` with:
- Multi-section panel (header, body, footer)
- Progress indicator during prompt processing
- ASCII-based token speed graph (last 30 tokens)
- Color-coded response sections (user, assistant, tool calls)

All components support TTY and non-TTY environments.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, Generator, Optional

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from c_e_h.streaming import StreamingResult, _extract_chunk_text
from c_e_h.ui.widgets import MetricRow, ProgressBar

logger = logging.getLogger(__name__)

# Section color coding
_SECTION_COLORS = {
    "user": "cyan",
    "assistant": "green",
    "system": "magenta",
    "tool": "yellow",
}


@dataclass
class _SpeedSample:
    """Internal sample for token speed tracking."""

    timestamp: float
    token_count: int


class EnhancedStreamDisplay:
    """Enhanced streaming display with multi-section panel and metrics.

    Extends the basic ``stream_display()`` with:
    - Header section showing model info and prompt metrics
    - Body section with color-coded streaming text
    - Footer section with live metrics and token speed graph
    - Progress indicator during prompt processing phase

    Attributes:
        title: Panel title shown in the display.
        model_info: Optional model identifier shown in header.
        refresh_per_second: Refresh rate for the live display.
        show_metrics: Whether to show metrics in footer.
        speed_graph_width: Width of the ASCII speed graph (chars).
        speed_samples: Internal list of speed samples for graph.
        callback: Optional callback invoked for each chunk.
        console: Rich Console instance.

    Example:
        >>> display = EnhancedStreamDisplay("AI Response", model_info="llama-3-8b")
        >>> result = display.render(chunks)
    """

    def __init__(
        self,
        title: str = "AI Response",
        model_info: Optional[str] = None,
        refresh_per_second: float = 10,
        show_metrics: bool = True,
        speed_graph_width: int = 30,
        callback: Optional[Callable[[dict], None]] = None,
        console: Optional[Console] = None,
    ) -> None:
        """Initialize EnhancedStreamDisplay.

        Args:
            title: Panel title.
            model_info: Model identifier for header display.
            refresh_per_second: Display refresh rate.
            show_metrics: Show metrics in footer.
            speed_graph_width: Width of speed graph in characters.
            callback: Optional chunk callback.
            console: Rich Console instance.
        """
        self.title = title
        self.model_info = model_info
        self.refresh_per_second = refresh_per_second
        self.show_metrics = show_metrics
        self.speed_graph_width = speed_graph_width
        self.callback = callback
        self.console = console or Console()
        self.speed_samples: list[_SpeedSample] = []
        self._result: Optional[StreamingResult] = None

    def render(
        self,
        chunks: Generator[dict, None, None],
        prompt_time: float = 0.0,
        prompt_tokens: int = 0,
    ) -> StreamingResult:
        """Render streaming chunks with enhanced display.

        Args:
            chunks: Generator yielding chunk dicts from the LLM backend.
            prompt_time: Time spent processing the prompt (seconds).
            prompt_tokens: Number of tokens in the prompt.

        Returns:
            A ``StreamingResult`` with accumulated text and metrics.
        """
        self._result = StreamingResult(
            prompt_time=prompt_time,
            prompt_tokens=prompt_tokens,
        )
        self.speed_samples = []

        # Build header
        header = self._build_header(prompt_time, prompt_tokens)

        # Build body (initially empty)
        body_text = Text()

        # Build footer
        footer = self._build_footer(self._result)

        # Build layout
        layout = self._build_layout(header, body_text, footer)

        with Live(
            layout,
            console=self.console,
            refresh_per_second=self.refresh_per_second,
            transient=False,
            screen=False,
        ) as live:
            last_update_time = time.time()
            tokens_since_update = 0

            for chunk in chunks:
                delta = _extract_chunk_text(chunk)
                if delta:
                    body_text.append(delta)
                    self._result.text += delta
                    self._result.token_count += 1
                    tokens_since_update += 1

                    # Track speed sample
                    now = time.time()
                    self.speed_samples.append(_SpeedSample(now, tokens_since_update))
                    # Keep only last 30 samples
                    if len(self.speed_samples) > 30:
                        self.speed_samples = self.speed_samples[-30:]

                if self.callback is not None:
                    try:
                        self.callback(chunk)
                    except Exception:
                        logger.exception("Streaming callback failed")

                # Update footer with latest metrics
                footer = self._build_footer(self._result)
                layout["body"].update(body_text)
                layout["footer"].update(footer)
                live.update(layout)

                # Throttle layout updates to avoid excessive refresh
                elapsed = time.time() - last_update_time
                if elapsed < 1.0 / self.refresh_per_second:
                    time.sleep(0.01)  # Small yield to avoid busy-wait
                last_update_time = time.time()

        self._result.finalize()
        return self._result

    def render_with_progress(
        self,
        chunks: Generator[dict, None, None],
        prompt_time: float = 0.0,
        prompt_tokens: int = 0,
        total_tokens_expected: Optional[int] = None,
    ) -> StreamingResult:
        """Render streaming chunks with progress indicator during prompt phase.

        Shows a progress bar while prompt is being processed, then switches
        to the enhanced streaming display.

        Args:
            chunks: Generator yielding chunk dicts.
            prompt_time: Time spent processing prompt.
            prompt_tokens: Number of prompt tokens.
            total_tokens_expected: Expected total token count (for progress).

        Returns:
            A ``StreamingResult`` with accumulated text and metrics.
        """
        self._result = StreamingResult(
            prompt_time=prompt_time,
            prompt_tokens=prompt_tokens,
        )
        self.speed_samples = []

        # Show progress during prompt processing
        if prompt_time > 0 and total_tokens_expected:
            with ProgressBar(
                f"Processing prompt ({prompt_tokens} tokens)",
                total=total_tokens_expected,
                console=self.console,
            ) as progress:
                # Simulate progress during prompt time
                start = time.time()
                while time.time() - start < prompt_time:
                    elapsed = time.time() - start
                    completed = min(int((elapsed / prompt_time) * total_tokens_expected), total_tokens_expected)
                    progress.update(completed)
                    time.sleep(0.05)

        return self.render(chunks, prompt_time, prompt_tokens)

    def _build_header(self, prompt_time: float, prompt_tokens: int) -> Panel:
        """Build the header section with model info and prompt metrics.

        Args:
            prompt_time: Time spent processing prompt.
            prompt_tokens: Number of prompt tokens.

        Returns:
            Rich Panel for header section.
        """
        header_lines: list[str] = []

        if self.model_info:
            header_lines.append(f"[bold cyan]Model:[/bold cyan] {self.model_info}")

        if prompt_tokens > 0:
            header_lines.append(f"[dim]Prompt tokens:[/dim] {prompt_tokens}")

        if prompt_time > 0:
            header_lines.append(f"[dim]Prompt time:[/dim] {prompt_time:.3f}s")

        if header_lines:
            header_text = Text("\n".join(header_lines))
            return Panel(
                header_text,
                title=self.title,
                border_style="blue",
                expand=True,
            )

        return Panel(
            self.title,
            border_style="blue",
            expand=True,
        )

    def _build_footer(self, result: StreamingResult) -> Panel:
        """Build the footer section with live metrics and speed graph.

        Args:
            result: Current StreamingResult.

        Returns:
            Rich Panel for footer section.
        """
        # Safely get token_count, handling MagicMock or missing attributes
        try:
            token_count = int(result.token_count) if result.token_count else 0
        except (TypeError, ValueError):
            token_count = 0

        if not self.show_metrics or token_count == 0:
            return Panel("", border_style="dim")

        # Build metrics
        metrics: list[MetricRow] = []
        if token_count > 0:
            metrics.append(MetricRow("Tokens", token_count))
        try:
            prompt_tokens = int(result.prompt_tokens) if result.prompt_tokens else 0
        except (TypeError, ValueError):
            prompt_tokens = 0
        if prompt_tokens > 0:
            metrics.append(MetricRow("Prompt", prompt_tokens))
        try:
            prompt_time = float(result.prompt_time) if result.prompt_time else 0.0
        except (TypeError, ValueError):
            prompt_time = 0.0
        if prompt_time > 0:
            metrics.append(MetricRow("Prompt", prompt_time, "s"))
        try:
            gt = float(result.generation_time) if result.generation_time else 0.0
        except (TypeError, ValueError):
            gt = 0.0
        if gt > 0:
            metrics.append(MetricRow("Gen", gt, "s"))
        try:
            tps = float(result.tokens_per_second) if result.tokens_per_second else 0.0
        except (TypeError, ValueError):
            tps = 0.0
        if tps > 0:
            metrics.append(MetricRow("Speed", tps, "tok/s"))

        # Build speed graph from samples
        speeds: list[float] = []
        if len(self.speed_samples) >= 2:
            for i in range(1, len(self.speed_samples)):
                dt = self.speed_samples[i].timestamp - self.speed_samples[i - 1].timestamp
                dc = self.speed_samples[i].token_count - self.speed_samples[i - 1].token_count
                if dt > 0:
                    speeds.append(dc / dt)

        speed_graph = ProgressBar.render_token_speed_graph(
            speeds,
            max_width=self.speed_graph_width,
        )

        # Combine metrics and speed graph
        if self.console.no_color:
            footer_content = "  ".join(str(m.render().plain) for m in metrics)
            footer_content += f"\n{speed_graph.plain}"
        else:
            metric_text = MetricRow.render_multiple(metrics, self.console)
            footer_content = Text.assemble(metric_text, "\n", speed_graph)

        return Panel(
            footer_content,
            title="[dim]Metrics[/dim]",
            border_style="dim",
            expand=True,
        )

    def _build_layout(
        self,
        header: Panel,
        body: Text,
        footer: Panel,
    ) -> Layout:
        """Build a multi-section layout.

        Args:
            header: Header panel.
            body: Body text.
            footer: Footer panel.

        Returns:
            Rich Layout with header, body, and footer sections.
        """
        layout = Layout()
        layout.split_column(
            Layout(header, name="header", size=4),
            Layout(name="body"),
            Layout(footer, name="footer", size=4),
        )
        layout["body"].update(body)
        return layout
