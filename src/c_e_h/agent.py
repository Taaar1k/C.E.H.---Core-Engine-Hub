"""Agent engine for C.E.H.

Manages the main agent loop, decision-making, and state management.
Integrates with LlamaBackend for GGUF model inference.
"""

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Lazy import to avoid requiring llama-cpp-python at import time
_LlamaBackend = None
_ModelConfig = None


def _get_backend_classes():
    """Lazy-import LlamaBackend and ModelConfig to avoid import errors when llama-cpp-python is not installed."""
    global _LlamaBackend, _ModelConfig
    if _LlamaBackend is None:
        from c_e_h.llama_backend import LlamaBackend, ModelConfig
        _LlamaBackend = LlamaBackend
        _ModelConfig = ModelConfig
    return _LlamaBackend, _ModelConfig


class AgentConfig(BaseModel):
    """Agent configuration loaded from agent.md."""

    name: str = "CEH-Agent"
    version: str = "0.1.0"
    description: str = "Your local AI assistant"

    model_path: str = "./models/llama-3-8b.Q4_K_M.gguf"
    n_gpu_layers: int = -1
    n_ctx: int = 8192
    temperature: float = 0.7

    max_context_tokens: int = 8192
    compaction_strategy: str = "microcompact"

    permission_mode: str = "autonomous"
    max_auto_errors: int = 3
    success_reset: int = 5

    tools: Dict[str, bool] = field(default_factory=lambda: {
        "file_read": True,
        "file_write": True,
        "execute_command": True,
        "web_search": False,
    })

    log_level: str = "INFO"
    log_format: str = "json"


@dataclass
class AgentState:
    """Represents the current state of the agent."""

    step_count: int = 0
    mode: str = "autonomous"
    auto_errors: int = 0
    context: List[Dict[str, Any]] = field(default_factory=list)
    last_response: Optional[str] = None
    started_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize state to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentState":
        """Restore state from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class Agent:
    """Main agent engine.

    Orchestrates the agent loop: receive input, generate response,
    execute tools, update memory, and repeat until task completion.
    """

    MAX_RETRIES: int = 3
    BASE_RETRY_DELAY: float = 1.0  # seconds

    def __init__(self, config: Optional[AgentConfig] = None) -> None:
        self.config = config or AgentConfig()
        self.state = AgentState(started_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
        self._setup_logging()
        self._backend = None  # LlamaBackend instance (lazy-loaded)
        logger.info(
            "Agent initialized config=%s version=%s",
            self.config.name,
            self.config.version,
        )

    def _setup_logging(self) -> None:
        """Configure logging based on agent config."""
        level = getattr(logging, self.config.log_level.upper(), logging.INFO)
        logger.setLevel(level)
        # stdlib logging is already configured; just set the level

    @classmethod
    def from_agent_md(cls, path: str = "agent.md") -> "Agent":
        """Load configuration from agent.md YAML file.

        Args:
            path: Path to the agent.md YAML file.

        Returns:
            Initialized Agent instance.
        """
        p = Path(path)
        if yaml is None:  # pragma: no cover
            logger.warning("PyYAML not installed, using default config")
            config = AgentConfig()
        elif p.exists():
            with open(p, "r") as f:
                data = yaml.safe_load(f)
            config = cls._parse_config(data)
        else:
            logger.warning("agent.md not found, using defaults path=%s", path)
            config = AgentConfig()
        return cls(config=config)

    @staticmethod
    def _parse_config(data: Dict[str, Any]) -> AgentConfig:
        """Parse raw config dict into AgentConfig.

        Args:
            data: Parsed YAML dictionary.

        Returns:
            Validated AgentConfig instance.
        """
        model = data.get("model", {})
        memory = data.get("memory", {})
        permissions = data.get("permissions", {})
        tools_data = data.get("tools", {})
        logging_cfg = data.get("logging", {})

        # Normalize tools: YAML booleans may be True/False; ensure dict[str, bool]
        tools: Dict[str, bool] = {}
        if isinstance(tools_data, dict):
            for k, v in tools_data.items():
                tools[str(k)] = bool(v)

        return AgentConfig(
            name=data.get("name", "CEH-Agent"),
            version=data.get("version", "0.1.0"),
            description=data.get("description", "Your local AI assistant"),
            model_path=model.get("path", "./models/llama-3-8b.Q4_K_M.gguf"),
            n_gpu_layers=model.get("n_gpu_layers", -1),
            n_ctx=model.get("n_ctx", 8192),
            temperature=model.get("temperature", 0.7),
            max_context_tokens=memory.get("max_context_tokens", 8192),
            compaction_strategy=memory.get("compaction_strategy", "microcompact"),
            permission_mode=permissions.get("mode", "autonomous"),
            max_auto_errors=permissions.get("max_auto_errors", 3),
            success_reset=permissions.get("success_reset", 5),
            tools=tools if tools else AgentConfig().tools,
            log_level=logging_cfg.get("level", "INFO"),
            log_format=logging_cfg.get("format", "json"),
        )

    def run(self, prompt: str) -> str:
        """Execute one step of the agent loop with retry logic.

        Args:
            prompt: User input or task description.

        Returns:
            Agent response or error message.
        """
        self.state.step_count += 1
        self.state.context.append({"role": "user", "content": prompt})

        try:
            response = self._generate_response_with_retry(prompt)
            self.state.context.append({"role": "assistant", "content": response})
            self.state.last_response = response
            self.state.auto_errors = 0  # Reset on success
            logger.info("Step completed step=%d", self.state.step_count)
            return response
        except Exception as e:
            self.state.auto_errors += 1
            logger.error("Step failed step=%d error=%s", self.state.step_count, str(e))
            if self.state.auto_errors >= self.config.max_auto_errors:
                self.state.mode = "approval"
                logger.warning(
                    "Switched to approval mode errors=%d",
                    self.state.auto_errors,
                )
            return f"[Error] Step {self.state.step_count} failed: {e}"

    def _generate_response_with_retry(self, prompt: str) -> str:
        """Generate response with exponential backoff retry.

        Args:
            prompt: The prompt to send to the LLM.

        Returns:
            The generated response string.

        Raises:
            RuntimeError: If all retries are exhausted.
        """
        for attempt in range(self.MAX_RETRIES):
            try:
                return self._generate_response(prompt)
            except Exception as e:
                delay = self.BASE_RETRY_DELAY * (2 ** attempt)
                logger.warning(
                    "LLM call failed, retrying attempt=%d max_retries=%d delay=%.2f error=%s",
                    attempt + 1,
                    self.MAX_RETRIES,
                    delay,
                    str(e),
                )
                time.sleep(delay)
        raise RuntimeError(f"Failed after {self.MAX_RETRIES} retries")

    def _ensure_backend(self) -> None:
        """Lazy-load and initialize LlamaBackend if not already loaded.

        Raises:
            RuntimeError: If llama-cpp-python is not installed or model file is missing.
        """
        if self._backend is not None:
            return

        LlamaBackend, ModelConfig = _get_backend_classes()
        cfg = ModelConfig(
            path=self.config.model_path,
            n_gpu_layers=self.config.n_gpu_layers,
            n_ctx=self.config.n_ctx,
            temperature=self.config.temperature,
            max_tokens=512,
        )
        self._backend = LlamaBackend(cfg)
        try:
            self._backend.load()
            logger.info("LlamaBackend loaded model=%s", self.config.model_path)
        except Exception as exc:
            logger.warning("Failed to load model (will be retried): %s", exc)
            self._backend = None
            raise

    def _generate_response(self, prompt: str) -> str:
        """Generate response by calling LLM backend.

        Args:
            prompt: The prompt to send.

        Returns:
            The generated response.

        Raises:
            ValueError: If prompt exceeds context window.
            RuntimeError: If backend is unavailable.
        """
        # Token counting heuristic
        token_count = self._estimate_tokens(prompt)
        if token_count > self.config.n_ctx:
            raise ValueError(
                f"Prompt exceeds context window: {token_count} > {self.config.n_ctx}"
            )

        logger.debug("Generating response tokens=%d", token_count)

        # Try LlamaBackend
        if self._backend is None:
            try:
                self._ensure_backend()
            except Exception as exc:
                logger.warning("Backend unavailable, using fallback: %s", exc)
                return f"[Step {self.state.step_count}] (Backend unavailable: {exc}) Processed: {prompt}"

        try:
            result = self._backend.generate(prompt, max_tokens=512, temperature=self.config.temperature)
            logger.info(
                "Generation complete step=%d prompt_tokens=%d completion_tokens=%d tps=%.2f",
                self.state.step_count,
                result.prompt_tokens,
                result.completion_tokens,
                result.tokens_per_second,
            )
            return result.text
        except Exception as exc:
            logger.error("Backend generation failed: %s", exc)
            # OOM fallback: retry with CPU (LlamaBackend handles this internally)
            return f"[Step {self.state.step_count}] [Backend Error] {exc}"

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count using heuristic (1 token ~ 4 chars).

        Args:
            text: Input text to estimate.

        Returns:
            Estimated token count (minimum 1).
        """
        return max(1, len(text) // 4)

    def save_state(self) -> Dict[str, Any]:
        """Serialize agent state to dict.

        Returns:
            Dictionary containing config and state.
        """
        return {
            "config": self.config.model_dump(),
            "state": self.state.to_dict(),
        }

    def load_state(self, data: Dict[str, Any]) -> None:
        """Restore agent state from dict.

        Args:
            data: Serialized state dictionary.
        """
        self.config = AgentConfig(**data.get("config", {}))
        self.state = AgentState.from_dict(data.get("state", {}))
        # Re-apply logging after config restore
        self._setup_logging()

    def get_state_json(self) -> str:
        """Serialize state to JSON string.

        Returns:
            JSON-formatted state string.
        """
        return json.dumps(self.save_state(), indent=2)

    @classmethod
    def load_state_json(cls, json_str: str) -> "Agent":
        """Create Agent from JSON string.

        Args:
            json_str: JSON-formatted state string.

        Returns:
            New Agent instance with restored state.
        """
        data = json.loads(json_str)
        agent = cls(config=AgentConfig(**data.get("config", {})))
        agent.state = AgentState.from_dict(data.get("state", {}))
        return agent
