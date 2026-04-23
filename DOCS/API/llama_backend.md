# Llama Backend API

> llama.cpp integration layer for model loading, inference, and sampling.

## Overview

The [`LlamaBackend`](../../src/c_e_h/llama_backend.py) class wraps `llama-cpp-python` to provide a clean interface for GGUF model loading, text generation, streaming, and grammar-constrained sampling.

## Supporting Classes

### `ModelConfig`

```python
class ModelConfig:
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
    ) -> None: ...
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | `str` | Required | Path to GGUF model file |
| `n_gpu_layers` | `int` | `-1` | GPU layers (`-1` = all layers) |
| `n_ctx` | `int` | `8192` | Context window size |
| `temperature` | `float` | `0.7` | Sampling temperature |
| `max_tokens` | `int` | `512` | Maximum tokens to generate |
| `n_batch` | `int` | `512` | Batch size for processing |
| `top_p` | `float` | `0.95` | Nucleus sampling threshold |
| `repeat_penalty` | `float` | `1.1` | Repetition penalty |
| `seed` | `int` | `-1` | Random seed (`-1` = random) |

### `GenerationResult`

```python
@dataclass
class GenerationResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    total_time: float
    tokens_per_second: float
    has_context_overflow: bool = False
    grammar_valid: bool = True
```

| Field | Type | Description |
|-------|------|-------------|
| `text` | `str` | Generated text |
| `prompt_tokens` | `int` | Number of prompt tokens processed |
| `completion_tokens` | `int` | Number of completion tokens generated |
| `total_time` | `float` | Total generation time in seconds |
| `tokens_per_second` | `float` | Generation speed |
| `has_context_overflow` | `bool` | Whether context window overflowed |
| `grammar_valid` | `bool` | Whether output passed grammar validation |

### `TokenTracker`

```python
@dataclass
class TokenTracker:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
```

Helper class for tracking generation metrics. Used internally by `LlamaBackend`.

### `ModelRouter`

```python
class ModelRouter:
    ROUTES: dict[str, str] = {
        "low": "./models/llama-3-2b-Q4_K_M.gguf",
        "medium": "./models/llama-3-8b-Q4_K_M.gguf",
        "high": "./models/llama-3-70b-Q4_K_M.gguf",
    }

    @classmethod
    def select_model(cls, complexity: str) -> ModelConfig: ...

    @classmethod
    def select_model_from_task(cls, task_text: str) -> ModelConfig: ...
```

Adaptive model routing based on task complexity. `select_model_from_task()` uses heuristics (length, keywords) to select appropriate model.

## Class Definition

### `LlamaBackend`

```python
class LlamaBackend:
    def __init__(self, config: ModelConfig) -> None: ...
```

The backend takes a `ModelConfig` instance (not individual parameters).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `ModelConfig` | Required | Model configuration |

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `config` | `ModelConfig` | Model configuration |

## Methods

### Model Loading

```python
def load(self) -> None: ...
```

Load the GGUF model into memory. Raises [`BackendError`](#backenderror) on failure.

| Exception | Condition |
|-----------|-----------|
| `BackendError` | If `llama-cpp-python` not installed or model file not found |

### Inference

```python
def generate(
    self,
    prompt: str,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    grammar: Optional[str] = None,
) -> GenerationResult: ...

def chat(
    self,
    messages: List[Dict[str, str]],
    max_tokens: Optional[int] = None,
) -> GenerationResult: ...
```

| Method | Returns | Description |
|--------|---------|-------------|
| `generate(prompt, max_tokens, temperature, grammar)` | `GenerationResult` | Text generation from prompt |
| `chat(messages, max_tokens)` | `GenerationResult` | Chat completion with message history |

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | `str` | Required | Input prompt (generate mode) |
| `messages` | `List[Dict[str, str]]` | Required | Chat messages (chat mode) |
| `max_tokens` | `Optional[int]` | `None` | Override config max_tokens |
| `temperature` | `Optional[float]` | `None` | Override config temperature |
| `grammar` | `Optional[str]` | `None` | GBNF grammar for structured output |

**Returns:** [`GenerationResult`](#generationresult) with text and metrics.

### Streaming

```python
def complete(
    self,
    prompt: str,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    grammar: Optional[str] = None,
    stream: bool = False,
    callback: Optional[Callable[[dict], None]] = None,
) -> "GenerationResult | Generator[dict, None, None]": ...

def chat_stream(
    self,
    messages: List[Dict[str, str]],
    max_tokens: Optional[int] = None,
    callback: Optional[Callable[[dict], None]] = None,
) -> Generator[dict, None, None]: ...
```

| Method | Returns | Description |
|--------|---------|-------------|
| `complete(..., stream=True)` | `Generator[dict]` | Streaming text generation |
| `chat_stream(messages, ..., callback)` | `Generator[dict]` | Streaming chat completion |

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `stream` | `bool` | If True, return generator instead of result |
| `callback` | `Callable[[dict], None] \| None` | Optional callback for each chunk |

### OOM Fallback

Both `generate()` and `chat()` automatically retry on CPU if GPU OOM is detected.

| Method | Description |
|--------|-------------|
| `count_tokens(text)` | Count tokens in text |
| `tokenize(text)` | Convert text to token IDs |
| `detokenize(tokens)` | Convert token IDs to text |

### Context Management

```python
def reset_context(self) -> None: ...
def get_context_size(self) -> int: ...
def get_available_context(self) -> int: ...
```

| Method | Description |
|--------|-------------|
| `reset_context()` | Clear KV cache |
| `get_context_size()` | Total context window size |
| `get_available_context()` | Remaining tokens in context |

## Model Metadata

```python
@dataclass
class ModelMetadata:
    model_path: str
    filename: str
    size_bytes: int
    vocab_size: int
    n_ctx_train: int
    n_embd: int
    n_layers: int
    n_heads: int
    n_ff: int
    quantization: str
    backend: str
```

## Usage Example

```python
from c_e_h.llama_backend import LlamaBackend

# Initialize backend
backend = LlamaBackend(
    model_path="./models/llama-3-8b.Q4_K_M.gguf",
    n_gpu_layers=-1,
    n_ctx=8192,
    temperature=0.7,
)

# Load model
if backend.load_model():
    print(f"Model loaded: {backend.model_info['quantization']}")
    print(f"Backend: {backend.backend_type}")
    print(f"Context: {backend.get_available_context()} tokens available")

    # Generate text
    response = backend.generate(
        prompt="Explain quantum computing in simple terms",
        max_tokens=512,
    )
    print(response)

    # Chat mode
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is the capital of France?"},
    ]
    response = backend.chat(messages, max_tokens=128)
    print(response)

    # Grammar-constrained output
    json_grammar = """
    root ::= object
    object ::= [ ] | { members }
    members ::= string ":" value ( "," string ":" value )*
    string ::= "\"" chars "\""
    chars ::= [^"]+ | empty
    value ::= string | number | "true" | "false" | "null"
    number ::= [-]? [0-9]+
    empty ::=
    """
    structured = backend.generate_with_grammar(
        prompt='Return a JSON object with keys "name" and "version"',
        grammar=json_grammar,
    )
    print(structured)

    # Token counting
    token_count = backend.count_tokens("Hello, world!")
    print(f"Token count: {token_count}")

    # Unload when done
    backend.unload_model()
```
