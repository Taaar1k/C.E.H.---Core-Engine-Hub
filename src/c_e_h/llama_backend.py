"""LLM backend for C.E.H.

Wraps llama.cpp via llama-cpp-python for GGUF model inference.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class ModelConfig:
    """Configuration for a GGUF model."""

    def __init__(
        self,
        path: str,
        n_gpu_layers: int = -1,
        n_ctx: int = 8192,
        temperature: float = 0.7,
        max_tokens: int = 512,
        n_batch: int = 512,
        top_p: float = 0.95,
        repeat_penalty: float = 1.1,
        seed: int = -1,
    ) -> None:
        self.path = path
        self.n_gpu_layers = n_gpu_layers
        self.n_ctx = n_ctx
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.n_batch = n_batch
        self.top_p = top_p
        self.repeat_penalty = repeat_penalty
        self.seed = seed


@dataclass
class TokenTracker:
    """Helper for tracking generation metrics."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    start_time: float = 0.0
    end_time: float = 0.0

    def to_result(
        self,
        text: str,
        has_overflow: bool = False,
        grammar_valid: bool = True,
    ) -> "GenerationResult":
        """Build a GenerationResult from tracked metrics."""
        if self.end_time == 0.0:
            self.end_time = time.time()
        total_time = self.end_time - self.start_time
        if total_time <= 0:
            total_time = 0.001  # avoid division by zero
        tokens_per_second = (self.completion_tokens / total_time) if self.completion_tokens > 0 else 0.0
        return GenerationResult(
            text=text,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            total_time=total_time,
            tokens_per_second=tokens_per_second,
            has_context_overflow=has_overflow,
            grammar_valid=grammar_valid,
        )


@dataclass
class GenerationResult:
    """Result of a text generation call."""

    text: str
    prompt_tokens: int
    completion_tokens: int
    total_time: float  # seconds
    tokens_per_second: float
    has_context_overflow: bool = False
    grammar_valid: bool = True


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class BackendError(Exception):
    """Custom exception for backend failures."""


# ---------------------------------------------------------------------------
# Model Router
# ---------------------------------------------------------------------------

class ModelRouter:
    """Adaptive model routing based on task complexity."""

    ROUTES: dict[str, str] = {
        "low": "./models/llama-3-2b-Q4_K_M.gguf",
        "medium": "./models/llama-3-8b-Q4_K_M.gguf",
        "high": "./models/llama-3-70b-Q4_K_M.gguf",
    }

    @classmethod
    def select_model(cls, complexity: str) -> ModelConfig:
        """Return a ModelConfig for the given complexity level."""
        path = cls.ROUTES.get(complexity, cls.ROUTES["low"])
        return ModelConfig(path=path)

    @classmethod
    def select_model_from_task(cls, task_text: str) -> ModelConfig:
        """Heuristic routing based on task text content.

        - len(task_text) > 500 or contains 'complex'/'analyze'/'architecture' → high
        - len(task_text) > 100 → medium
        - else → low
        """
        lower = task_text.lower()
        if len(task_text) > 500 or any(word in lower for word in ("complex", "analyze", "architecture")):
            return cls.select_model("high")
        if len(task_text) > 100:
            return cls.select_model("medium")
        return cls.select_model("low")


# ---------------------------------------------------------------------------
# Llama Backend
# ---------------------------------------------------------------------------

class LlamaBackend:
    """Backend for llama.cpp inference.

    Loads GGUF models and provides text generation capabilities.
    """

    def __init__(self, config: ModelConfig) -> None:
        self.config = config
        self._model: Any = None
        self._tracker = TokenTracker()

    def load(self) -> None:
        """Load the GGUF model into memory.

        Raises BackendError on import failure or file not found.
        """
        try:
            from llama_cpp import Llama
        except ImportError:
            raise BackendError("llama-cpp-python not installed")

        model_path = Path(self.config.path)
        if not model_path.exists():
            raise BackendError(f"Model file not found: {self.config.path}")

        try:
            self._model = Llama(
                model_path=str(model_path),
                n_gpu_layers=self.config.n_gpu_layers,
                n_ctx=self.config.n_ctx,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                n_batch=self.config.n_batch,
                top_p=self.config.top_p,
                repeat_penalty=self.config.repeat_penalty,
                seed=self.config.seed,
            )
            logger.info("Model loaded path=%s", self.config.path)
        except Exception as exc:
            raise BackendError(f"Failed to load model: {exc}") from exc

    def generate(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        grammar: Optional[str] = None,
    ) -> GenerationResult:
        """Generate text from a prompt.

        Args:
            prompt: Input text prompt.
            max_tokens: Maximum tokens to generate (overrides config).
            temperature: Sampling temperature (overrides config).
            grammar: GBNF grammar string for structured output.

        Returns:
            GenerationResult with text and metrics.

        Raises:
            BackendError: If model is not loaded.
        """
        if self._model is None:
            raise BackendError("Model not loaded. Call load() first.")

        effective_max_tokens = max_tokens if max_tokens is not None else self.config.max_tokens
        effective_temperature = temperature if temperature is not None else self.config.temperature

        self._tracker = TokenTracker()
        self._tracker.start_time = time.time()

        try:
            result_dict = self._model.create_completion(
                prompt=prompt,
                max_tokens=effective_max_tokens,
                temperature=effective_temperature,
                grammar=grammar,
            )
            return self._measure(result_dict)
        except Exception as exc:
            error_str = str(exc).lower()
            # OOM fallback: retry with CPU
            if "out of memory" in error_str or "cuda" in error_str:
                logger.warning("OOM detected, retrying with CPU")
                return self._retry_cpu(prompt, effective_max_tokens, effective_temperature, grammar)
            # Context overflow
            if "context overflow" in error_str:
                result_dict = self._model.create_completion(
                    prompt=prompt,
                    max_tokens=effective_max_tokens,
                    temperature=effective_temperature,
                    grammar=grammar,
                )
                return self._measure(result_dict, has_overflow=True)
            raise BackendError(f"Generation failed: {exc}") from exc

    def chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
    ) -> GenerationResult:
        """Generate a chat response from a message history.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.
            max_tokens: Maximum tokens to generate (overrides config).

        Returns:
            GenerationResult with text and metrics.

        Raises:
            BackendError: If model is not loaded.
        """
        if self._model is None:
            raise BackendError("Model not loaded. Call load() first.")

        effective_max_tokens = max_tokens if max_tokens is not None else self.config.max_tokens

        self._tracker = TokenTracker()
        self._tracker.start_time = time.time()

        try:
            result_dict = self._model.create_chat_completion(
                messages=messages,
                max_tokens=effective_max_tokens,
            )
            return self._measure(result_dict)
        except Exception as exc:
            error_str = str(exc).lower()
            if "out of memory" in error_str or "cuda" in error_str:
                logger.warning("OOM detected in chat, retrying with CPU")
                return self._retry_cpu_chat(messages, effective_max_tokens)
            if "context overflow" in error_str:
                result_dict = self._model.create_chat_completion(
                    messages=messages,
                    max_tokens=effective_max_tokens,
                )
                return self._measure(result_dict, has_overflow=True)
            raise BackendError(f"Chat failed: {exc}") from exc

    def complete(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        grammar: Optional[str] = None,
        stream: bool = False,
        callback: Optional[Callable[[dict], None]] = None,
    ) -> "GenerationResult | Generator[dict, None, None]":
        """Generate text from a prompt, with optional streaming.

        Args:
            prompt: Input text prompt.
            max_tokens: Maximum tokens to generate (overrides config).
            temperature: Sampling temperature (overrides config).
            grammar: GBNF grammar string for structured output.
            stream: If True, return a generator yielding chunks.
            callback: Optional callback invoked for each streaming chunk.

        Returns:
            GenerationResult (non-streaming) or Generator yielding chunk dicts.

        Raises:
            BackendError: If model is not loaded.
        """
        if self._model is None:
            raise BackendError("Model not loaded. Call load() first.")

        if stream:
            return self._complete_stream(prompt, max_tokens, temperature, grammar, callback)
        # Non-streaming path: reuse existing generate() logic
        return self.generate(prompt, max_tokens, temperature, grammar)

    def _complete_stream(
        self,
        prompt: str,
        max_tokens: Optional[int],
        temperature: Optional[float],
        grammar: Optional[str],
        callback: Optional[Callable[[dict], None]],
    ) -> Generator[dict, None, None]:
        """Internal: streaming completion path.

        Args:
            prompt: Input text prompt.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            grammar: GBNF grammar string.
            callback: Optional callback for each chunk.

        Yields:
            Chunk dicts from the llama.cpp completion API.
        """
        effective_max_tokens = max_tokens if max_tokens is not None else self.config.max_tokens
        effective_temperature = temperature if temperature is not None else self.config.temperature

        self._tracker = TokenTracker()
        self._tracker.start_time = time.time()

        try:
            response = self._model.create_completion(
                prompt=prompt,
                max_tokens=effective_max_tokens,
                temperature=effective_temperature,
                grammar=grammar,
                stream=True,
            )
            prompt_tokens_collected = False
            for chunk in response:
                if callback is not None:
                    try:
                        callback(chunk)
                    except Exception:
                        logger.exception("Streaming callback failed")
                usage = chunk.get("usage", {})
                if usage:
                    self._tracker.prompt_tokens = usage.get("prompt_tokens", 0)
                    self._tracker.completion_tokens = usage.get("completion_tokens", 0)
                    prompt_tokens_collected = True
                yield chunk
            if prompt_tokens_collected:
                self._tracker.end_time = time.time()
        except Exception as exc:
            error_str = str(exc).lower()
            if "out of memory" in error_str or "cuda" in error_str:
                logger.warning("OOM detected in complete(stream), retrying with CPU")
                yield from self._retry_cpu_stream(
                    prompt, effective_max_tokens, effective_temperature, grammar, callback
                )
                return
            raise BackendError(f"Streaming generation failed: {exc}") from exc

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        callback: Optional[Callable[[dict], None]] = None,
    ) -> Generator[dict, None, None]:
        """Generate a streaming chat response from a message history.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.
            max_tokens: Maximum tokens to generate (overrides config).
            callback: Optional callback invoked for each streaming chunk.

        Yields:
            Chunk dicts from the llama.cpp chat completion API.

        Raises:
            BackendError: If model is not loaded.
        """
        if self._model is None:
            raise BackendError("Model not loaded. Call load() first.")

        effective_max_tokens = max_tokens if max_tokens is not None else self.config.max_tokens

        self._tracker = TokenTracker()
        self._tracker.start_time = time.time()

        try:
            response = self._model.create_chat_completion(
                messages=messages,
                max_tokens=effective_max_tokens,
                stream=True,
            )
            for chunk in response:
                if callback is not None:
                    try:
                        callback(chunk)
                    except Exception:
                        logger.exception("Streaming callback failed")
                usage = chunk.get("usage", {})
                if usage:
                    self._tracker.prompt_tokens = usage.get("prompt_tokens", 0)
                    self._tracker.completion_tokens = usage.get("completion_tokens", 0)
                yield chunk
            self._tracker.end_time = time.time()
        except Exception as exc:
            error_str = str(exc).lower()
            if "out of memory" in error_str or "cuda" in error_str:
                logger.warning("OOM detected in chat_stream(), retrying with CPU")
                yield from self._retry_cpu_chat_stream(messages, effective_max_tokens, callback)
                return
            raise BackendError(f"Streaming chat failed: {exc}") from exc

    def close(self) -> None:
        """Release model resources."""
        if self._model is not None:
            self._model.close()
            self._model = None
            logger.info("Model resources released")

    # ---- Private helpers ----

    def _measure(
        self,
        result_dict: dict,
        has_overflow: bool = False,
        grammar_valid: bool = True,
    ) -> GenerationResult:
        """Build a GenerationResult from llama_cpp response dict."""
        choices = result_dict.get("choices", [])
        if choices:
            first = choices[0]
            # Completion: {"choices": [{"text": "..."}]}
            # Chat: {"choices": [{"message": {"content": "..."}}]}
            text = first.get("text", "") or first.get("message", {}).get("content", "")
        else:
            text = ""
        usage = result_dict.get("usage", {})
        self._tracker.prompt_tokens = usage.get("prompt_tokens", 0)
        self._tracker.completion_tokens = usage.get("completion_tokens", 0)
        return self._tracker.to_result(
            text=text,
            has_overflow=has_overflow,
            grammar_valid=grammar_valid,
        )

    def _retry_cpu(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        grammar: Optional[str],
    ) -> GenerationResult:
        """Retry generation with n_gpu_layers=0 (CPU fallback)."""
        old_gpu_layers = self.config.n_gpu_layers
        self.config.n_gpu_layers = 0
        try:
            # Reload model with CPU-only config
            from llama_cpp import Llama
            model_path = Path(self.config.path)
            self._model = Llama(
                model_path=str(model_path),
                n_gpu_layers=0,
                n_ctx=self.config.n_ctx,
                temperature=temperature,
                max_tokens=max_tokens,
                n_batch=self.config.n_batch,
                top_p=self.config.top_p,
                repeat_penalty=self.config.repeat_penalty,
                seed=self.config.seed,
            )
            result_dict = self._model.create_completion(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                grammar=grammar,
            )
            return self._measure(result_dict)
        except Exception as exc:
            self.config.n_gpu_layers = old_gpu_layers
            raise BackendError(f"CPU fallback failed: {exc}") from exc
        finally:
            self.config.n_gpu_layers = old_gpu_layers

    def _retry_cpu_chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
    ) -> GenerationResult:
        """Retry chat with n_gpu_layers=0 (CPU fallback)."""
        old_gpu_layers = self.config.n_gpu_layers
        self.config.n_gpu_layers = 0
        try:
            from llama_cpp import Llama
            model_path = Path(self.config.path)
            self._model = Llama(
                model_path=str(model_path),
                n_gpu_layers=0,
                n_ctx=self.config.n_ctx,
                temperature=self.config.temperature,
                max_tokens=max_tokens,
                n_batch=self.config.n_batch,
                top_p=self.config.top_p,
                repeat_penalty=self.config.repeat_penalty,
                seed=self.config.seed,
            )
            result_dict = self._model.create_chat_completion(
                messages=messages,
                max_tokens=max_tokens,
            )
            return self._measure(result_dict)
        except Exception as exc:
            self.config.n_gpu_layers = old_gpu_layers
            raise BackendError(f"CPU fallback failed: {exc}") from exc
        finally:
            self.config.n_gpu_layers = old_gpu_layers

    def _retry_cpu_stream(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        grammar: Optional[str],
        callback: Optional[Callable[[dict], None]],
    ) -> Generator[dict, None, None]:
        """Retry streaming generation with n_gpu_layers=0 (CPU fallback)."""
        old_gpu_layers = self.config.n_gpu_layers
        self.config.n_gpu_layers = 0
        try:
            from llama_cpp import Llama
            model_path = Path(self.config.path)
            self._model = Llama(
                model_path=str(model_path),
                n_gpu_layers=0,
                n_ctx=self.config.n_ctx,
                temperature=temperature,
                max_tokens=max_tokens,
                n_batch=self.config.n_batch,
                top_p=self.config.top_p,
                repeat_penalty=self.config.repeat_penalty,
                seed=self.config.seed,
            )
            response = self._model.create_completion(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                grammar=grammar,
                stream=True,
            )
            for chunk in response:
                if callback is not None:
                    try:
                        callback(chunk)
                    except Exception:
                        logger.exception("Streaming callback failed")
                yield chunk
        except Exception as exc:
            self.config.n_gpu_layers = old_gpu_layers
            raise BackendError(f"CPU fallback streaming failed: {exc}") from exc
        finally:
            self.config.n_gpu_layers = old_gpu_layers

    def _retry_cpu_chat_stream(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        callback: Optional[Callable[[dict], None]],
    ) -> Generator[dict, None, None]:
        """Retry streaming chat with n_gpu_layers=0 (CPU fallback)."""
        old_gpu_layers = self.config.n_gpu_layers
        self.config.n_gpu_layers = 0
        try:
            from llama_cpp import Llama
            model_path = Path(self.config.path)
            self._model = Llama(
                model_path=str(model_path),
                n_gpu_layers=0,
                n_ctx=self.config.n_ctx,
                temperature=self.config.temperature,
                max_tokens=max_tokens,
                n_batch=self.config.n_batch,
                top_p=self.config.top_p,
                repeat_penalty=self.config.repeat_penalty,
                seed=self.config.seed,
            )
            response = self._model.create_chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                stream=True,
            )
            for chunk in response:
                if callback is not None:
                    try:
                        callback(chunk)
                    except Exception:
                        logger.exception("Streaming callback failed")
                yield chunk
        except Exception as exc:
            self.config.n_gpu_layers = old_gpu_layers
            raise BackendError(f"CPU fallback chat streaming failed: {exc}") from exc
        finally:
            self.config.n_gpu_layers = old_gpu_layers
