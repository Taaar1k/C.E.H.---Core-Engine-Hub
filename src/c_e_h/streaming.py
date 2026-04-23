"""Streaming output utilities for real-time token display.

Provides ``stream_display()`` for terminal rendering of streaming
LLM responses, plus a ``StreamingResult`` dataclass for tracking
generation metrics during streaming.

This module uses only stdlib — no Rich or other UI dependencies.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Generator, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class StreamingResult:
    """Accumulated result from a streaming generation.

    Attributes:
        text: The full accumulated response text.
        token_count: Number of tokens generated.
        prompt_tokens: Number of tokens in the prompt.
        prompt_time: Time spent processing the prompt (seconds).
        generation_time: Time spent generating tokens (seconds).
        tokens_per_second: Effective generation speed.
    """

    text: str = ""
    token_count: int = 0
    prompt_tokens: int = 0
    prompt_time: float = 0.0
    generation_start: Optional[float] = field(default=None, repr=False)
    generation_end: Optional[float] = field(default=None, repr=False)

    @property
    def generation_time(self) -> float:
        """Elapsed generation time in seconds."""
        if self.generation_start is None:
            return 0.0
        end = self.generation_end if self.generation_end is not None else time.time()
        return end - self.generation_start

    @property
    def tokens_per_second(self) -> float:
        """Tokens per second during generation."""
        gt = self.generation_time
        if gt <= 0 or self.token_count == 0:
            return 0.0
        return self.token_count / gt

    def finalize(self) -> "StreamingResult":
        """Mark generation as complete and compute final metrics."""
        self.generation_end = time.time()
        logger.info(
            "Streaming complete tokens=%d prompt_tokens=%d prompt_time=%.3f generation_time=%.3f tokens_per_second=%.1f",
            self.token_count,
            self.prompt_tokens,
            self.prompt_time,
            self.generation_time,
            self.tokens_per_second,
        )
        return self


# ---------------------------------------------------------------------------
# Streaming Display
# ---------------------------------------------------------------------------

def _extract_chunk_text(chunk: dict) -> str:
    """Extract text delta from a streaming chunk.

    Handles both direct llama.cpp format (``{"choices": [{"text": "..."}]}``) and
    OpenAI-compatible format (``{"choices": [{"delta": {"content": "..."}}]}``).

    Args:
        chunk: A single streaming chunk dict.

    Returns:
        The text delta string.
    """
    choices = chunk.get("choices")
    if not choices:
        return ""
    first = choices[0]
    # Direct API format: {"choices": [{"text": "..."}]}
    if "text" in first:
        return first["text"]
    # OpenAI-compatible format: {"choices": [{"delta": {"content": "..."}}]}
    delta = first.get("delta", {})
    if isinstance(delta, dict):
        return delta.get("content", "")
    return str(delta)


def stream_display(
    chunks: Generator[dict, None, None],
    title: str = "AI Response",
    refresh_per_second: float = 10,
    show_metrics: bool = True,
    callback: Optional[Callable[[dict], None]] = None,
) -> StreamingResult:
    """Display streaming tokens in the terminal (plain text, no Rich).

    Iterates over streaming chunks, accumulates text, and prints
    it to stdout with optional metrics overlay.

    Args:
        chunks: Generator yielding chunk dicts from the LLM backend.
        title: Panel title shown in the output.
        refresh_per_second: Refresh rate for the live display (unused in plain mode).
        show_metrics: Whether to show token count and speed metrics.
        callback: Optional callback invoked for each chunk.

    Returns:
        A ``StreamingResult`` with accumulated text and metrics.
    """
    result = StreamingResult()
    accumulated = []

    for chunk in chunks:
        delta = _extract_chunk_text(chunk)
        if delta:
            accumulated.append(delta)
            result.text += delta
            result.token_count += 1
        if callback is not None:
            try:
                callback(chunk)
            except Exception:
                logger.exception("Streaming callback failed")

    result.finalize()

    # Print final result
    print(f"\n=== {title} ===")
    print(result.text)
    if show_metrics and result.token_count > 0:
        metrics = [f"Tokens: {result.token_count}"]
        if result.prompt_tokens > 0:
            metrics.append(f"Prompt: {result.prompt_tokens}")
        if result.prompt_time > 0:
            metrics.append(f"Prompt: {result.prompt_time:.3f}s")
        gt = result.generation_time
        if gt > 0:
            metrics.append(f"Gen: {gt:.3f}s")
        tps = result.tokens_per_second
        if tps > 0:
            metrics.append(f"Speed: {tps:.1f} tok/s")
        print(f"\n{'  '.join(metrics)}")

    return result


def stream_display_with_timing(
    chunks: Generator[dict, None, None],
    title: str = "AI Response",
    refresh_per_second: float = 10,
    show_metrics: bool = True,
    callback: Optional[Callable[[dict], None]] = None,
    prompt_time: float = 0.0,
    prompt_tokens: int = 0,
) -> StreamingResult:
    """Display streaming tokens with pre-computed prompt metrics.

    Args:
        chunks: Generator yielding chunk dicts from the LLM backend.
        title: Panel title shown in the output.
        refresh_per_second: Refresh rate for the live display (unused in plain mode).
        show_metrics: Whether to show token count and speed metrics.
        callback: Optional callback invoked for each chunk.
        prompt_time: Time spent processing the prompt (seconds).
        prompt_tokens: Number of tokens in the prompt.

    Returns:
        A ``StreamingResult`` with accumulated text and metrics.
    """
    result = stream_display(
        chunks=chunks,
        title=title,
        refresh_per_second=refresh_per_second,
        show_metrics=show_metrics,
        callback=callback,
    )
    result.prompt_time = prompt_time
    result.prompt_tokens = prompt_tokens
    return result
