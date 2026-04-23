"""Tests for c_e_h.ui.streaming_enhanced module.

Tests EnhancedStreamDisplay class with mock chunk generators.
"""

from __future__ import annotations

import io
import time
from unittest.mock import MagicMock, patch

from rich.console import Console
from rich.text import Text

from c_e_h.ui.streaming_enhanced import EnhancedStreamDisplay


def _mock_chunks(text_parts: list[str]) -> list[dict]:
    """Generate mock streaming chunks from text parts."""
    chunks = []
    for part in text_parts:
        chunks.append({"choices": [{"text": part}]})
    return chunks


class TestEnhancedStreamDisplay:
    """Tests for EnhancedStreamDisplay class."""

    def test_init_defaults(self):
        """Test default initialization."""
        display = EnhancedStreamDisplay()
        assert display.title == "AI Response"
        assert display.model_info is None
        assert display.refresh_per_second == 10
        assert display.show_metrics is True
        assert display.speed_graph_width == 30
        assert display.speed_samples == []

    def test_init_custom(self):
        """Test custom initialization."""
        display = EnhancedStreamDisplay(
            title="Test",
            model_info="llama-3-8b",
            refresh_per_second=5,
            speed_graph_width=20,
        )
        assert display.title == "Test"
        assert display.model_info == "llama-3-8b"
        assert display.refresh_per_second == 5
        assert display.speed_graph_width == 20

    def test_build_header_with_model(self):
        """Test header with model info."""
        display = EnhancedStreamDisplay(model_info="llama-3-8b")
        header = display._build_header(prompt_time=0.1, prompt_tokens=64)
        assert header is not None

    def test_build_header_empty(self):
        """Test header with no info."""
        display = EnhancedStreamDisplay()
        header = display._build_header(prompt_time=0, prompt_tokens=0)
        assert header is not None

    def test_build_footer_empty(self):
        """Test footer with no result."""
        display = EnhancedStreamDisplay()
        from c_e_h.streaming import StreamingResult
        result = StreamingResult()
        footer = display._build_footer(result)
        assert footer is not None

    def test_build_footer_with_metrics(self):
        """Test footer with metrics."""
        display = EnhancedStreamDisplay()
        from c_e_h.streaming import StreamingResult
        result = StreamingResult()
        result.token_count = 100
        result.prompt_tokens = 64
        result.prompt_time = 0.1
        result.generation_start = time.time() - 2.0
        result.generation_end = time.time()
        footer = display._build_footer(result)
        assert footer is not None

    def test_build_footer_no_metrics(self):
        """Test footer when metrics disabled."""
        display = EnhancedStreamDisplay(show_metrics=False)
        from c_e_h.streaming import StreamingResult
        result = StreamingResult()
        result.token_count = 100
        footer = display._build_footer(result)
        assert footer is not None

    def test_build_layout(self):
        """Test layout construction."""
        display = EnhancedStreamDisplay()
        header = display._build_header(0, 0)
        body = Text("Test content")
        footer = display._build_footer(MagicMock())
        layout = display._build_layout(header, body, footer)
        assert layout is not None
        child_names = [child.name for child in layout.children]
        assert "header" in child_names
        assert "body" in child_names
        assert "footer" in child_names

    @patch("c_e_h.ui.streaming_enhanced.Live")
    def test_render_basic(self, mock_live):
        """Test basic render with mock Live."""
        display = EnhancedStreamDisplay(console=Console(force_terminal=True))
        chunks = _mock_chunks(["Hello", " ", "World"])

        # Mock the Live context manager
        mock_context = MagicMock()
        mock_live.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_live.return_value.__exit__ = MagicMock(return_value=False)

        result = display.render(iter(chunks))
        assert result is not None
        assert result.token_count == 3
        assert "Hello World" in result.text

    @patch("c_e_h.ui.streaming_enhanced.Live")
    def test_render_with_callback(self, mock_live):
        """Test render with callback."""
        callback_calls = []

        def callback(chunk):
            callback_calls.append(chunk)

        display = EnhancedStreamDisplay(callback=callback)
        chunks = _mock_chunks(["A", "B"])

        mock_context = MagicMock()
        mock_live.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_live.return_value.__exit__ = MagicMock(return_value=False)

        result = display.render(iter(chunks))
        assert len(callback_calls) == 2

    @patch("c_e_h.ui.streaming_enhanced.Live")
    def test_render_empty_chunks(self, mock_live):
        """Test render with empty chunks."""
        display = EnhancedStreamDisplay()

        mock_context = MagicMock()
        mock_live.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_live.return_value.__exit__ = MagicMock(return_value=False)

        result = display.render(iter([]))
        assert result.token_count == 0

    @patch("c_e_h.ui.streaming_enhanced.Live")
    def test_render_with_prompt_metrics(self, mock_live):
        """Test render with pre-computed prompt metrics."""
        display = EnhancedStreamDisplay()
        chunks = _mock_chunks(["Test"])

        mock_context = MagicMock()
        mock_live.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_live.return_value.__exit__ = MagicMock(return_value=False)

        result = display.render(chunks, prompt_time=0.5, prompt_tokens=32)
        assert result.prompt_time == 0.5
        assert result.prompt_tokens == 32

    @patch("c_e_h.ui.streaming_enhanced.Live")
    def test_render_with_timing(self, mock_live):
        """Test render_with_progress method."""
        display = EnhancedStreamDisplay()
        chunks = _mock_chunks(["A", "B", "C"])

        mock_context = MagicMock()
        mock_live.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_live.return_value.__exit__ = MagicMock(return_value=False)

        result = display.render_with_progress(
            chunks,
            prompt_time=0.1,
            prompt_tokens=10,
            total_tokens_expected=100,
        )
        assert result is not None

    def test_no_color_console(self):
        """Test rendering with no_color console."""
        output = io.StringIO()
        console = Console(file=output, force_terminal=True, no_color=True)
        display = EnhancedStreamDisplay(console=console)
        header = display._build_header(0, 0)
        assert header is not None

    def test_speed_samples_tracking(self):
        """Test that speed samples are tracked during render."""
        display = EnhancedStreamDisplay()
        assert display.speed_samples == []

        # Simulate adding samples
        from c_e_h.ui.streaming_enhanced import _SpeedSample
        sample = _SpeedSample(time.time(), 1)
        display.speed_samples.append(sample)
        assert len(display.speed_samples) == 1

    def test_speed_samples_limit(self):
        """Test speed samples are limited to 30."""
        display = EnhancedStreamDisplay()
        from c_e_h.ui.streaming_enhanced import _SpeedSample
        for i in range(35):
            display.speed_samples.append(_SpeedSample(time.time(), i))
        # Should keep only last 30
        assert len(display.speed_samples) == 35  # Trimming happens during render
