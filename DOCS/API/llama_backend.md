# Llama Backend API

> llama.cpp integration layer for model loading, inference, and sampling.

## Overview

The [`LlamaBackend`](../../src/c_e_h/llama_backend.py) class wraps `llama-cpp-python` to provide a clean interface for GGUF model loading, text generation, and grammar-constrained sampling.

## Class Definition

```python
class LlamaBackend:
    def __init__(
        self,
        model_path: str,
        n_gpu_layers: int = -1,
        n_ctx: int = 8192,
        temperature: float = 0.7,
        top_p: float = 0.9,
        repeat_penalty: float = 1.1,
        seed: int = 42,
    ) -> None: ...
```

### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model_path` | `str` | Required | Path to GGUF model file |
| `n_gpu_layers` | `int` | `-1` | GPU layers (`-1` = all layers) |
| `n_ctx` | `int` | `8192` | Context window size |
| `temperature` | `float` | `0.7` | Sampling temperature |
| `top_p` | `float` | `0.9` | Nucleus sampling threshold |
| `repeat_penalty` | `float` | `1.1` | Repetition penalty |
| `seed` | `int` | `42` | Random seed for reproducibility |

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `model_path` | `str` | Path to loaded model |
| `n_gpu_layers` | `int` | GPU layer count |
| `n_ctx` | `int` | Context window size |
| `model_info` | `dict` | Model metadata (vocab size, dimensions, etc.) |
| `is_loaded` | `bool` | Whether model is successfully loaded |
| `backend_type` | `str` | Backend used (`metal`, `cuda`, `vulkan`, `cpu`) |

## Methods

### Model Loading

```python
def load_model(self) -> bool: ...
def unload_model(self) -> None: ...
def reload_model(self, model_path: str | None = None) -> bool: ...
```

| Method | Description |
|--------|-------------|
| `load_model()` | Load GGUF model into memory |
| `unload_model()` | Free model from memory |
| `reload_model(path)` | Reload model (optionally new path) |

### Inference

```python
def generate(
    self,
    prompt: str,
    max_tokens: int = 4096,
    temperature: float | None = None,
    stop: list[str] | None = None,
) -> str: ...

def chat(
    self,
    messages: list[dict],
    max_tokens: int = 4096,
    temperature: float | None = None,
    stop: list[str] | None = None,
) -> str: ...
```

| Method | Description |
|--------|-------------|
| `generate(prompt, max_tokens, temperature, stop)` | Text generation from prompt |
| `chat(messages, max_tokens, temperature, stop)` | Chat completion with message history |

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | `str` | Required | Input prompt (generate mode) |
| `messages` | `list[dict]` | Required | Chat messages (chat mode) |
| `max_tokens` | `int` | `4096` | Maximum tokens to generate |
| `temperature` | `float \| None` | `None` | Override instance temperature |
| `stop` | `list[str] \| None` | `None` | Stop sequences |

**Returns:** Generated text string.

### Grammar-Constrained Sampling

```python
def generate_with_grammar(
    self,
    prompt: str,
    grammar: str,
    max_tokens: int = 4096,
) -> str: ...
```

Generate text constrained by a GBNF grammar. Useful for structured output (JSON, tool calls).

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `prompt` | `str` | Input prompt |
| `grammar` | `str` | GBNF grammar string |
| `max_tokens` | `int` | Maximum tokens |

**Returns:** Grammar-constrained text.

### Token Management

```python
def count_tokens(self, text: str) -> int: ...
def tokenize(self, text: str) -> list[int]: ...
def detokenize(self, tokens: list[int]) -> str: ...
```

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
