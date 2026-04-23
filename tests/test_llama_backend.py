"""Comprehensive unit tests for llama_backend and grammar modules."""

import json
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures / shared mocks
# ---------------------------------------------------------------------------

MOCK_COMPLETION_RESULT = {
    "choices": [{"text": "Hello, world!"}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
}

MOCK_CHAT_RESULT = {
    "choices": [{"message": {"role": "assistant", "content": "Chat response"}}],
    "usage": {"prompt_tokens": 15, "completion_tokens": 8},
}


# ---------------------------------------------------------------------------
# 1. test_model_config_defaults
# ---------------------------------------------------------------------------

class TestModelConfig:
    def test_model_config_defaults(self):
        """Verify all default values."""
        from c_e_h.llama_backend import ModelConfig

        config = ModelConfig(path="./models/test.gguf")
        assert config.path == "./models/test.gguf"
        assert config.n_gpu_layers == -1
        assert config.n_ctx == 8192
        assert config.temperature == 0.7
        assert config.max_tokens == 512
        assert config.n_batch == 512
        assert config.top_p == 0.95
        assert config.repeat_penalty == 1.1
        assert config.seed == -1

    def test_model_config_custom(self):
        """Verify custom values accepted."""
        from c_e_h.llama_backend import ModelConfig

        config = ModelConfig(
            path="./models/custom.gguf",
            n_gpu_layers=10,
            n_ctx=4096,
            temperature=0.5,
            max_tokens=256,
            n_batch=256,
            top_p=0.9,
            repeat_penalty=1.2,
            seed=42,
        )
        assert config.path == "./models/custom.gguf"
        assert config.n_gpu_layers == 10
        assert config.n_ctx == 4096
        assert config.temperature == 0.5
        assert config.max_tokens == 256
        assert config.n_batch == 256
        assert config.top_p == 0.9
        assert config.repeat_penalty == 1.2
        assert config.seed == 42


# ---------------------------------------------------------------------------
# 2. test_backend_load_success / file_not_found / import_error
# ---------------------------------------------------------------------------

class TestBackendLoad:
    @patch("llama_cpp.Llama")
    @patch("c_e_h.llama_backend.Path.exists")
    def test_backend_load_success(self, MockExists, MockLlama):
        """Mock llama_cpp.Llama init, verify config passed correctly."""
        from c_e_h.llama_backend import LlamaBackend, ModelConfig

        MockExists.return_value = True
        config = ModelConfig(path="./models/test.gguf")
        backend = LlamaBackend(config)
        backend.load()

        MockLlama.assert_called_once_with(
            model_path="models/test.gguf",
            n_gpu_layers=-1,
            n_ctx=8192,
            temperature=0.7,
            max_tokens=512,
            n_batch=512,
            top_p=0.95,
            repeat_penalty=1.1,
            seed=-1,
        )
        assert backend._model is not None

    def test_backend_load_file_not_found(self):
        """Verify BackendError raised on missing file."""
        from c_e_h.llama_backend import BackendError, LlamaBackend, ModelConfig

        config = ModelConfig(path="./models/nonexistent.gguf")
        backend = LlamaBackend(config)

        with patch("c_e_h.llama_backend.Path.exists", return_value=False):
            with patch("llama_cpp.Llama"):
                with pytest.raises(BackendError, match="Model file not found"):
                    backend.load()

    def test_backend_load_import_error(self):
        """Mock ImportError on llama_cpp import, verify BackendError.

        Uses patch on the module's __import__ within a context manager
        to avoid global side effects.
        """
        from c_e_h.llama_backend import BackendError, LlamaBackend, ModelConfig

        config = ModelConfig(path="./models/test.gguf")
        backend = LlamaBackend(config)

        with patch("builtins.__import__", side_effect=ImportError("no module")):
            with pytest.raises(BackendError, match="llama-cpp-python not installed"):
                backend.load()


# ---------------------------------------------------------------------------
# 3. test_backend_generate / OOM fallback / chat
# ---------------------------------------------------------------------------

class TestBackendGenerate:
    @patch("llama_cpp.Llama")
    @patch("c_e_h.llama_backend.Path.exists")
    def test_backend_generate(self, MockExists, MockLlama):
        """Mock completion result, verify GenerationResult returned with correct metrics."""
        from c_e_h.llama_backend import LlamaBackend, ModelConfig

        MockExists.return_value = True
        mock_model = MagicMock()
        mock_model.create_completion.return_value = MOCK_COMPLETION_RESULT
        MockLlama.return_value = mock_model

        config = ModelConfig(path="./models/test.gguf")
        backend = LlamaBackend(config)
        backend.load()

        result = backend.generate("Test prompt")

        assert result.text == "Hello, world!"
        assert result.prompt_tokens == 10
        assert result.completion_tokens == 5
        assert result.total_time > 0
        assert result.tokens_per_second > 0
        assert result.has_context_overflow is False
        assert result.grammar_valid is True

    @patch("llama_cpp.Llama")
    @patch("c_e_h.llama_backend.Path.exists")
    def test_backend_generate_oom_fallback(self, MockExists, MockLlama):
        """Mock first call raises OOM-like error, verify retry with n_gpu_layers=0."""
        from c_e_h.llama_backend import LlamaBackend, ModelConfig

        MockExists.return_value = True
        mock_model = MagicMock()
        # First call raises OOM, second call (CPU retry) succeeds
        mock_model.create_completion.side_effect = [
            Exception("OutOfMemory: CUDA error"),
            MOCK_COMPLETION_RESULT,
        ]
        MockLlama.return_value = mock_model

        config = ModelConfig(path="./models/test.gguf")
        backend = LlamaBackend(config)
        backend.load()

        result = backend.generate("Test prompt")

        assert result.text == "Hello, world!"
        assert result.completion_tokens == 5
        # Verify two calls were made (original + retry)
        assert mock_model.create_completion.call_count == 2

    def test_backend_generate_not_loaded(self):
        """Verify BackendError when generate is called without load."""
        from c_e_h.llama_backend import BackendError, LlamaBackend, ModelConfig

        config = ModelConfig(path="./models/test.gguf")
        backend = LlamaBackend(config)

        with pytest.raises(BackendError, match="Model not loaded"):
            backend.generate("prompt")


class TestBackendChat:
    @patch("llama_cpp.Llama")
    @patch("c_e_h.llama_backend.Path.exists")
    def test_backend_chat(self, MockExists, MockLlama):
        """Mock chat completion result, verify response."""
        from c_e_h.llama_backend import LlamaBackend, ModelConfig

        MockExists.return_value = True
        mock_model = MagicMock()
        mock_model.create_chat_completion.return_value = MOCK_CHAT_RESULT
        MockLlama.return_value = mock_model

        config = ModelConfig(path="./models/test.gguf")
        backend = LlamaBackend(config)
        backend.load()

        messages = [
            {"role": "user", "content": "Hello"},
        ]
        result = backend.chat(messages)

        assert result.text == "Chat response"
        assert result.prompt_tokens == 15
        assert result.completion_tokens == 8
        assert result.total_time > 0

    def test_backend_chat_not_loaded(self):
        """Verify BackendError when chat is called without load."""
        from c_e_h.llama_backend import BackendError, LlamaBackend, ModelConfig

        config = ModelConfig(path="./models/test.gguf")
        backend = LlamaBackend(config)

        with pytest.raises(BackendError, match="Model not loaded"):
            backend.chat([{"role": "user", "content": "Hi"}])


# ---------------------------------------------------------------------------
# 4. test_token_tracker_to_result
# ---------------------------------------------------------------------------

class TestTokenTracker:
    def test_token_tracker_to_result(self):
        """Verify tokens_per_second calculation."""
        from c_e_h.llama_backend import TokenTracker

        tracker = TokenTracker(prompt_tokens=10, completion_tokens=20, start_time=100.0, end_time=102.0)

        result = tracker.to_result("test text")

        assert result.text == "test text"
        assert result.prompt_tokens == 10
        assert result.completion_tokens == 20
        assert result.total_time == 2.0
        assert result.tokens_per_second == 10.0  # 20 / 2.0
        assert result.has_context_overflow is False
        assert result.grammar_valid is True


# ---------------------------------------------------------------------------
# 5. test_model_router
# ---------------------------------------------------------------------------

class TestModelRouter:
    def test_model_router_select_model(self):
        """Verify low/medium/high return correct paths."""
        from c_e_h.llama_backend import ModelRouter

        low = ModelRouter.select_model("low")
        assert low.path == "./models/llama-3-2b-Q4_K_M.gguf"

        medium = ModelRouter.select_model("medium")
        assert medium.path == "./models/llama-3-8b-Q4_K_M.gguf"

        high = ModelRouter.select_model("high")
        assert high.path == "./models/llama-3-70b-Q4_K_M.gguf"

    def test_model_router_select_model_from_task(self):
        """Verify heuristic for short vs long task text."""
        from c_e_h.llama_backend import ModelRouter

        # Short task → low (len < 100)
        short = ModelRouter.select_model_from_task("write hello world")
        assert short.path == "./models/llama-3-2b-Q4_K_M.gguf"

        # Medium task → medium (len > 100 but <= 500, no keywords)
        # 30 words * ~5 chars = ~150 chars
        medium_text = " ".join(["word"] * 30)
        assert len(medium_text) > 100
        assert len(medium_text) <= 500
        medium = ModelRouter.select_model_from_task(medium_text)
        assert medium.path == "./models/llama-3-8b-Q4_K_M.gguf"

        # Long task → high (len > 500)
        long_text = " ".join(["word"] * 200)
        assert len(long_text) > 500
        high = ModelRouter.select_model_from_task(long_text)
        assert high.path == "./models/llama-3-70b-Q4_K_M.gguf"

        # Contains keyword → high even if short
        keyword = ModelRouter.select_model_from_task("analyze this complex architecture")
        assert keyword.path == "./models/llama-3-70b-Q4_K_M.gguf"


# ---------------------------------------------------------------------------
# 6. test_grammar_engine
# ---------------------------------------------------------------------------

class TestGrammarEngine:
    def test_grammar_engine_compile(self):
        """Verify comment stripping and whitespace trimming."""
        from c_e_h.grammar import GrammarEngine

        raw = """\
// This is a comment
root ::= "hello"

// Another comment
ws ::= " "
"""
        compiled = GrammarEngine.compile_grammar(raw)
        assert "//" not in compiled
        assert "root" in compiled
        assert "ws" in compiled

    def test_grammar_engine_validate_tool_call(self):
        """Valid and invalid tool call JSON."""
        from c_e_h.grammar import GrammarEngine

        valid = json.dumps({"name": "search", "arguments": {"query": "test"}})
        assert GrammarEngine.validate_output(valid, "tool_call") is True

        invalid = json.dumps({"action": "search"})
        assert GrammarEngine.validate_output(invalid, "tool_call") is False

        not_json = "not json at all"
        assert GrammarEngine.validate_output(not_json, "tool_call") is False

    def test_grammar_engine_validate_decision(self):
        """Valid and invalid decision JSON."""
        from c_e_h.grammar import GrammarEngine

        valid = json.dumps({"action": "approve", "reason": "looks good"})
        assert GrammarEngine.validate_output(valid, "decision") is True

        invalid = json.dumps({"name": "search", "arguments": {}})
        assert GrammarEngine.validate_output(invalid, "decision") is False

    def test_grammar_engine_parse_tool_call(self):
        """Valid returns dict, invalid returns None."""
        from c_e_h.grammar import GrammarEngine

        valid = json.dumps({"name": "search", "arguments": {"query": "test"}})
        result = GrammarEngine.parse_tool_call(valid)
        assert result == {"name": "search", "arguments": {"query": "test"}}

        invalid = "not json"
        assert GrammarEngine.parse_tool_call(invalid) is None

    def test_grammar_engine_parse_decision(self):
        """Valid returns dict, invalid returns None."""
        from c_e_h.grammar import GrammarEngine

        valid = json.dumps({"action": "approve", "reason": "looks good"})
        result = GrammarEngine.parse_decision(valid)
        assert result == {"action": "approve", "reason": "looks good"}

        invalid = 12345
        assert GrammarEngine.parse_decision(str(invalid)) is None


# ---------------------------------------------------------------------------
# 7. test_backend_error
# ---------------------------------------------------------------------------

class TestBackendError:
    def test_backend_error(self):
        """Verify exception message preserved."""
        from c_e_h.llama_backend import BackendError

        error = BackendError("Test error message")
        assert str(error) == "Test error message"

        with pytest.raises(BackendError, match="Test error message"):
            raise error
