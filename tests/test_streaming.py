"""Unit tests for streaming module (streaming.py).

Tests cover:
- StreamingResult dataclass (token counting, timing, tokens/sec)
- stream_display() iteration and chunk extraction
- rich.Live display (mocked)
- Callback invocation
- Both direct API and OpenAI-compatible streaming formats
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures / shared data
# ---------------------------------------------------------------------------

DIRECT_API_CHUNKS = [
    {"choices": [{"text": "Hello"}], "usage": {}},
    {"choices": [{"text": ", "}], "usage": {}},
    {"choices": [{"text": "world!"}], "usage": {"completion_tokens": 4, "prompt_tokens": 2}},
]

OPENAI_COMPATIBLE_CHUNKS = [
    {"choices": [{"delta": {"content": "Hello"}}], "usage": {}},
    {"choices": [{"delta": {"content": ", "}}], "usage": {}},
    {"choices": [{"delta": {"content": "world!"}}], "usage": {"completion_tokens": 4, "prompt_tokens": 2}},
]


# ---------------------------------------------------------------------------
# 1. StreamingResult dataclass tests
# ---------------------------------------------------------------------------

class TestStreamingResult:
    """Tests for the StreamingResult dataclass."""

    def test_default_values(self):
        """Verify default values for StreamingResult fields."""
        from c_e_h.streaming import StreamingResult

        result = StreamingResult()
        assert result.text == ""
        assert result.token_count == 0
        assert result.prompt_tokens == 0
        assert result.prompt_time == 0.0
        assert result.generation_start is None
        assert result.generation_end is None

    def test_generation_time_zero_when_no_start(self):
        """generation_time should be 0.0 when generation_start is None."""
        from c_e_h.streaming import StreamingResult

        result = StreamingResult()
        assert result.generation_time == 0.0

    def test_generation_time_computed(self):
        """generation_time should be end - start when both are set."""
        from c_e_h.streaming import StreamingResult

        start = 1000.0
        end = 1001.5
        result = StreamingResult(generation_start=start, generation_end=end)
        assert result.generation_time == pytest.approx(1.5, abs=0.01)

    def test_tokens_per_second_zero_when_no_generation(self):
        """tokens_per_second should be 0.0 when generation_time is 0."""
        from c_e_h.streaming import StreamingResult

        result = StreamingResult(token_count=10)
        assert result.tokens_per_second == 0.0

    def test_tokens_per_second_computed(self):
        """tokens_per_second should be token_count / generation_time."""
        from c_e_h.streaming import StreamingResult

        result = StreamingResult(
            token_count=10,
            generation_start=1000.0,
            generation_end=1002.0,
        )
        assert result.tokens_per_second == pytest.approx(5.0, abs=0.1)

    def test_finalize_sets_end_time(self):
        """finalize() should set generation_end to current time."""
        from c_e_h.streaming import StreamingResult

        result = StreamingResult(generation_start=1000.0)
        with patch("c_e_h.streaming.time.time") as mock_time:
            mock_time.return_value = 1001.0
            finalized = result.finalize()
        assert finalized.generation_end == 1001.0

    def test_finalize_returns_self(self):
        """finalize() should return self for chaining."""
        from c_e_h.streaming import StreamingResult

        result = StreamingResult()
        with patch("c_e_h.streaming.time.time"):
            assert result.finalize() is result


# ---------------------------------------------------------------------------
# 2. _extract_chunk_text tests
# ---------------------------------------------------------------------------

class TestExtractChunkText:
    """Tests for the _extract_chunk_text helper."""

    def test_direct_api_format(self):
        """Extract text from direct API format chunk."""
        from c_e_h.streaming import _extract_chunk_text

        chunk = {"choices": [{"text": "Hello, world!"}]}
        assert _extract_chunk_text(chunk) == "Hello, world!"

    def test_openai_compatible_format(self):
        """Extract content from OpenAI-compatible format chunk."""
        from c_e_h.streaming import _extract_chunk_text

        chunk = {"choices": [{"delta": {"content": "Hello"}}]}
        assert _extract_chunk_text(chunk) == "Hello"

    def test_empty_choices(self):
        """Return empty string when choices is empty."""
        from c_e_h.streaming import _extract_chunk_text

        chunk = {"choices": []}
        assert _extract_chunk_text(chunk) == ""

    def test_no_choices_key(self):
        """Return empty string when choices key is missing."""
        from c_e_h.streaming import _extract_chunk_text

        chunk = {}
        assert _extract_chunk_text(chunk) == ""

    def test_delta_is_string(self):
        """Handle delta as a string (non-dict)."""
        from c_e_h.streaming import _extract_chunk_text

        chunk = {"choices": [{"delta": "raw text"}]}
        assert _extract_chunk_text(chunk) == "raw text"


# ---------------------------------------------------------------------------
# 3. stream_display tests (mocked rich.Live)
# ---------------------------------------------------------------------------

class TestStreamDisplay:
    """Tests for stream_display() with mocked rich components."""

    @patch("c_e_h.streaming.Live")
    @patch("c_e_h.streaming.Console")
    @patch("c_e_h.streaming.Text")
    @patch("c_e_h.streaming.time.time")
    def test_stream_display_accumulates_text(
        self, mock_time, mock_text, mock_console, mock_live
    ):
        """stream_display should accumulate text from chunks."""
        from c_e_h.streaming import stream_display

        mock_time.side_effect = [1000.0, 1001.0]  # start + finalize
        mock_text_instance = MagicMock()
        mock_text_instance.copy.return_value = mock_text_instance
        mock_text.return_value = mock_text_instance

        chunks = iter([
            {"choices": [{"text": "A"}]},
            {"choices": [{"text": "B"}]},
            {"choices": [{"text": "C"}], "usage": {"completion_tokens": 3, "prompt_tokens": 1}},
        ])

        result = stream_display(chunks, title="Test")

        assert result.text == "ABC"
        assert result.token_count == 3
        # stream_display counts chunks, not prompt_tokens (backend sets those)
        assert result.prompt_tokens == 0

    @patch("c_e_h.streaming.Live")
    @patch("c_e_h.streaming.Console")
    @patch("c_e_h.streaming.Text")
    @patch("c_e_h.streaming.time.time")
    def test_stream_display_calls_callback(
        self, mock_time, mock_text, mock_console, mock_live
    ):
        """stream_display should invoke callback for each chunk."""
        from c_e_h.streaming import stream_display

        mock_time.side_effect = [1000.0, 1001.0]
        mock_text_instance = MagicMock()
        mock_text_instance.copy.return_value = mock_text_instance
        mock_text.return_value = mock_text_instance

        chunks = iter([
            {"choices": [{"text": "X"}]},
            {"choices": [{"text": "Y"}], "usage": {"completion_tokens": 2, "prompt_tokens": 1}},
        ])

        received_chunks = []
        def callback(chunk):
            received_chunks.append(chunk)

        stream_display(chunks, title="Test", callback=callback)

        assert len(received_chunks) == 2
        assert received_chunks[0] == {"choices": [{"text": "X"}]}
        assert received_chunks[1] == {"choices": [{"text": "Y"}], "usage": {"completion_tokens": 2, "prompt_tokens": 1}}

    @patch("c_e_h.streaming.Live")
    @patch("c_e_h.streaming.Console")
    @patch("c_e_h.streaming.Text")
    @patch("c_e_h.streaming.time.time")
    def test_stream_display_openai_format(
        self, mock_time, mock_text, mock_console, mock_live
    ):
        """stream_display should handle OpenAI-compatible format."""
        from c_e_h.streaming import stream_display

        mock_time.side_effect = [1000.0, 1001.0]
        mock_text_instance = MagicMock()
        mock_text_instance.copy.return_value = mock_text_instance
        mock_text.return_value = mock_text_instance

        chunks = iter([
            {"choices": [{"delta": {"content": "Hello"}}]},
            {"choices": [{"delta": {"content": " World"}}], "usage": {"completion_tokens": 2, "prompt_tokens": 1}},
        ])

        result = stream_display(chunks, title="Test")

        assert result.text == "Hello World"
        assert result.token_count == 2

    @patch("c_e_h.streaming.Live")
    @patch("c_e_h.streaming.Console")
    @patch("c_e_h.streaming.Text")
    @patch("c_e_h.streaming.time.time")
    def test_stream_display_empty_chunks(
        self, mock_time, mock_text, mock_console, mock_live
    ):
        """stream_display should handle empty chunk list."""
        from c_e_h.streaming import stream_display

        mock_time.side_effect = [1000.0, 1000.0]
        mock_text_instance = MagicMock()
        mock_text_instance.copy.return_value = mock_text_instance
        mock_text.return_value = mock_text_instance

        chunks = iter([])
        result = stream_display(chunks, title="Test")

        assert result.text == ""
        assert result.token_count == 0

    @patch("c_e_h.streaming.Live")
    @patch("c_e_h.streaming.Console")
    @patch("c_e_h.streaming.Text")
    @patch("c_e_h.streaming.time.time")
    def test_stream_display_callback_exception_handled(
        self, mock_time, mock_text, mock_console, mock_live
    ):
        """stream_display should not crash if callback raises."""
        from c_e_h.streaming import stream_display

        mock_time.return_value = 1000.0
        mock_text_instance = MagicMock()
        mock_text_instance.copy.return_value = mock_text_instance
        mock_text.return_value = mock_text_instance

        def bad_callback(chunk):
            raise ValueError("callback error")

        chunks = iter([
            {"choices": [{"text": "A"}]},
            {"choices": [{"text": "B"}], "usage": {"completion_tokens": 2, "prompt_tokens": 1}},
        ])

        # Should not raise
        result = stream_display(chunks, title="Test", callback=bad_callback)

        assert result.text == "AB"
        assert result.token_count == 2


# ---------------------------------------------------------------------------
# 4. stream_display_with_timing tests
# ---------------------------------------------------------------------------

class TestStreamDisplayWithTiming:
    """Tests for stream_display_with_timing()."""

    @patch("c_e_h.streaming.stream_display")
    @patch("c_e_h.streaming.time.time")
    def test_stream_display_with_timing_sets_metrics(
        self, mock_time, mock_stream_display
    ):
        """stream_display_with_timing should set prompt_time and prompt_tokens."""
        from c_e_h.streaming import stream_display_with_timing

        mock_result = MagicMock()
        mock_stream_display.return_value = mock_result

        chunks = iter([{"choices": [{"text": "test"}]}])
        result = stream_display_with_timing(
            chunks,
            prompt_time=0.05,
            prompt_tokens=10,
        )

        assert result.prompt_time == 0.05
        assert result.prompt_tokens == 10
        mock_stream_display.assert_called_once()


# ---------------------------------------------------------------------------
# 5. LlamaBackend streaming tests
# ---------------------------------------------------------------------------

class TestLlamaBackendStreaming:
    """Tests for LlamaBackend streaming methods."""

    @patch("llama_cpp.Llama")
    @patch("c_e_h.llama_backend.Path.exists")
    def test_complete_stream_yields_chunks(self, MockExists, MockLlama):
        """complete(stream=True) should yield chunks from the model."""
        from c_e_h.llama_backend import LlamaBackend, ModelConfig

        MockExists.return_value = True
        mock_model = MagicMock()
        MockLlama.return_value = mock_model
        mock_model.create_completion.return_value = iter([
            {"choices": [{"text": "A"}]},
            {"choices": [{"text": "B"}], "usage": {"completion_tokens": 2, "prompt_tokens": 1}},
        ])

        config = ModelConfig(path="./models/test.gguf")
        backend = LlamaBackend(config)
        backend.load()

        chunks = list(backend.complete("test prompt", stream=True))

        assert len(chunks) == 2
        assert chunks[0] == {"choices": [{"text": "A"}]}
        assert chunks[1] == {"choices": [{"text": "B"}], "usage": {"completion_tokens": 2, "prompt_tokens": 1}}

    @patch("llama_cpp.Llama")
    @patch("c_e_h.llama_backend.Path.exists")
    def test_complete_stream_with_callback(self, MockExists, MockLlama):
        """complete(stream=True) should invoke callback for each chunk."""
        from c_e_h.llama_backend import LlamaBackend, ModelConfig

        MockExists.return_value = True
        mock_model = MagicMock()
        MockLlama.return_value = mock_model
        mock_model.create_completion.return_value = iter([
            {"choices": [{"text": "X"}]},
            {"choices": [{"text": "Y"}], "usage": {"completion_tokens": 2, "prompt_tokens": 1}},
        ])

        config = ModelConfig(path="./models/test.gguf")
        backend = LlamaBackend(config)
        backend.load()

        received = []
        def callback(chunk):
            received.append(chunk)

        list(backend.complete("test", stream=True, callback=callback))

        assert len(received) == 2

    @patch("llama_cpp.Llama")
    @patch("c_e_h.llama_backend.Path.exists")
    def test_complete_non_stream_returns_generation_result(self, MockExists, MockLlama):
        """complete(stream=False) should return GenerationResult."""
        from c_e_h.llama_backend import LlamaBackend, ModelConfig

        MockExists.return_value = True
        mock_model = MagicMock()
        MockLlama.return_value = mock_model
        mock_model.create_completion.return_value = {
            "choices": [{"text": "Hello"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
        }

        config = ModelConfig(path="./models/test.gguf")
        backend = LlamaBackend(config)
        backend.load()

        result = backend.complete("test prompt", stream=False)

        assert result.text == "Hello"
        assert result.prompt_tokens == 5
        assert result.completion_tokens == 3

    @patch("llama_cpp.Llama")
    @patch("c_e_h.llama_backend.Path.exists")
    def test_chat_stream_yields_chunks(self, MockExists, MockLlama):
        """chat_stream() should yield chunks from the model."""
        from c_e_h.llama_backend import LlamaBackend, ModelConfig

        MockExists.return_value = True
        mock_model = MagicMock()
        MockLlama.return_value = mock_model
        mock_model.create_chat_completion.return_value = iter([
            {"choices": [{"delta": {"content": "Hi"}}]},
            {"choices": [{"delta": {"content": " there"}}], "usage": {"completion_tokens": 2, "prompt_tokens": 3}},
        ])

        config = ModelConfig(path="./models/test.gguf")
        backend = LlamaBackend(config)
        backend.load()

        chunks = list(backend.chat_stream([{"role": "user", "content": "hello"}]))

        assert len(chunks) == 2

    def test_complete_raises_when_model_not_loaded(self):
        """complete() should raise BackendError if model not loaded."""
        from c_e_h.llama_backend import BackendError, LlamaBackend, ModelConfig

        config = ModelConfig(path="./models/test.gguf")
        backend = LlamaBackend(config)

        with pytest.raises(BackendError, match="Model not loaded"):
            list(backend.complete("test", stream=True))

    def test_chat_stream_raises_when_model_not_loaded(self):
        """chat_stream() should raise BackendError if model not loaded."""
        from c_e_h.llama_backend import BackendError, LlamaBackend, ModelConfig

        config = ModelConfig(path="./models/test.gguf")
        backend = LlamaBackend(config)

        with pytest.raises(BackendError, match="Model not loaded"):
            list(backend.chat_stream([{"role": "user", "content": "hello"}]))
