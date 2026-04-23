# Developer Guide

> Setting up your development environment and contributing to C.E.H.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Running Tests](#running-tests)
- [Code Style](#code-style)
- [Adding a New Tool](#adding-a-new-tool)
- [Adding a New CLI Command](#adding-a-new-cli-command)
- [Extending the Memory System](#extending-the-memory-system)
- [Custom Backend Integration](#custom-backend-integration)
- [Debugging Tips](#debugging-tips)
- [Release Process](#release-process)

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11 or 3.12 (LTS) | Runtime and development |
| [uv](https://docs.astral.sh/uv/) | Latest | Package manager and virtual environment |
| [git](https://git-scm.com/) | Latest | Version control |
| [llama.cpp](https://github.com/ggerganov/llama.cpp) | Latest | C++ inference engine (via `llama-cpp-python`) |

### Optional Tools

| Tool | Purpose |
|------|---------|
| [ruff](https://docs.astral.sh/ruff/) | Linting and formatting |
| [mypy](https://mypy.readthedocs.io/) | Static type checking |
| [pytest](https://pytest.org/) | Testing framework |
| [pytest-cov](https://pytest-cov.readthedocs.io/) | Coverage reporting |

## Development Setup

```bash
# 1. Clone the repository
git clone https://github.com/your-org/ceh.git
cd ceh

# 2. Create and activate virtual environment
uv venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# 3. Install development dependencies
uv sync --all-extras

# 4. Install pre-commit hooks (if configured)
pip install pre-commit
pre-commit install

# 5. Verify setup
python -c "import c_e_h; print('C.E.H. ready')"
ceh doctor
```

### GPU Acceleration Setup

#### Apple Silicon (Metal)

```bash
# Works out of the box with Xcode Command Line Tools
xcode-select --install
# No additional configuration needed
```

#### Linux (CUDA)

```bash
# Install CUDA toolkit
sudo apt install nvidia-cuda-toolkit  # Debian/Ubuntu

# Build llama-cpp-python with CUDA support
CMAKE_ARGS="-DGGML_CUDA=1" uv sync

# Verify
python -c "from llama_cpp import Llama; print(Llama.from_pretrained(repo_id='')"  # Should show CUDA backend
```

#### Linux (Vulkan)

```bash
# Install Vulkan drivers
sudo apt install libvulkan-dev mesa-vulkan-drivers

# Build with Vulkan support
CMAKE_ARGS="-DGGML_VULKAN=1" uv sync

# Add user to GPU groups
sudo usermod -aG render,$USER
sudo usermod -aG video,$USER
# Log out and back in
```

## Project Structure

```
ceh/
├── pyproject.toml              # Project metadata, dependencies, entry points
├── uv.lock                     # Deterministic dependency lock file
├── README.md                   # Quick-start overview
├── SECURITY.md                 # Security policy
├── DEPENDENCY_POLICY.md        # Dependency management rules
├── CHANGELOG.md                # Version history
├── LICENSE                     # MIT License
│
├── src/
│   └── c_e_h/
│       ├── __init__.py         # Package version and exports
│       ├── cli.py              # CLI interface (Typer)
│       ├── agent.py            # Core Agent class and task loop
│       ├── memory.py           # Three-tier memory system
│       ├── tools.py            # Tool registry and execution
│       └── llama_backend.py    # llama.cpp integration
│
├── tests/
│   ├── __init__.py
│   ├── test_cli.py             # CLI command tests
│   ├── test_agent.py           # Agent lifecycle tests
│   ├── test_memory.py          # Memory system tests
│   ├── test_tools.py           # Tool registry tests
│   └── test_llama_backend.py   # Backend tests
│
├── models/                     # GGUF model storage (gitignored)
├── scripts/
│   ├── setup.sh                # One-line setup script
│   └── audit_deps.sh           # Dependency audit script
│
├── DOCS/                       # Documentation
│   ├── API/                    # API reference
│   ├── DEVELOPER_GUIDE.md      # This file
│   ├── ARCHITECTURE.md         # System architecture
│   ├── SECURITY.md             # Security documentation
│   └── CONTRIBUTING.md         # Contribution guidelines
│
├── MEMORY/                     # Project state tracking
│   ├── PROJECT_STATE.md
│   ├── TASK_BOARD.md
│   └── TASKS/
│
└── .github/
    └── workflows/              # CI/CD pipelines
```

## Running Tests

```bash
# Run all tests
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ -v --cov=src/c_e_h --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_tools.py -v

# Run with specific marker
uv run pytest tests/ -v -m "slow"

# Watch mode (auto-rerun on changes)
uv run pytest-watch tests/
```

### Test Structure

```python
# tests/test_agent.py
import pytest
from c_e_h.agent import Agent

class TestAgent:
    def test_agent_initialization(self):
        """Agent initializes with default config."""
        agent = Agent(model_path="./models/test.gguf")
        assert agent is not None
        assert agent.state.name == "IDLE"

    @pytest.mark.skip(reason="Requires model file")
    def test_agent_run(self):
        """Agent processes a prompt and returns response."""
        agent = Agent(model_path="./models/test.gguf")
        response = agent.run("Hello")
        assert response.text is not None
```

## Code Style

C.E.H. uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting.

```bash
# Lint
uv run ruff check src/ tests/

# Format
uv run ruff format src/ tests/

# Type checking
uv run mypy src/
```

### Style Guidelines

| Rule | Standard |
|------|----------|
| Line length | 100 characters |
| Indentation | 4 spaces |
| Quotes | Single quotes (prefer `'` over `"`) |
| Imports | Sorted by `ruff` isort |
| Type hints | Required for all function signatures |
| Docstrings | Google style |

### Example

```python
"""Example module for style reference."""

from pydantic import BaseModel, Field
from typing import Any


class ExampleConfig(BaseModel):
    """Configuration for the example feature."""

    enabled: bool = Field(default=True, description="Whether the feature is enabled")
    max_retries: int = Field(default=3, ge=0, description="Maximum retry attempts")


def process_data(data: list[str], config: ExampleConfig) -> dict[str, Any]:
    """Process input data according to configuration.

    Args:
        data: List of string data items.
        config: Configuration object.

    Returns:
        Processed data as dictionary.

    Raises:
        ValueError: If data is empty.
    """
    if not data:
        raise ValueError("Data cannot be empty")

    return {"items": data, "count": len(data), "enabled": config.enabled}
```

## Adding a New Tool

### Step 1: Define the Tool Schema

```python
# src/c_e_h/tools/my_tool.py
from pydantic import BaseModel, Field

class MyToolSchema(BaseModel):
    """Schema for my_tool."""

    query: str = Field(..., description="Search query", min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=20, description="Number of results")
```

### Step 2: Implement the Tool

```python
# src/c_e_h/tools/my_tool.py (continued)
from c_e_h.tools import tool, ToolResult

@tool(
    name="my_tool",
    description="Perform a custom operation",
    requires_permission=True,
    schema=MyToolSchema,
)
def my_tool(query: str, limit: int = 5) -> ToolResult:
    """Implement the tool logic.

    Args:
        query: The search query.
        limit: Number of results to return.

    Returns:
        ToolResult with success/failure status.
    """
    try:
        # Tool implementation
        results = perform_operation(query)
        return ToolResult(success=True, data={"results": results})
    except Exception as e:
        return ToolResult(success=False, error=str(e))
```

### Step 3: Register the Tool

```python
# src/c_e_h/tools/__init__.py
from .my_tool import my_tool  # noqa: F401

# Ensure it's in the registry
__all__ = ["my_tool", ...]
```

### Step 4: Write Tests

```python
# tests/test_my_tool.py
import pytest
from c_e_h.tools.my_tool import my_tool
from c_e_h.tools import ToolResult

def test_my_tool_success():
    result = my_tool(query="test", limit=3)
    assert result.success is True
    assert "results" in result.data

def test_my_tool_empty_query():
    with pytest.raises(Exception):
        my_tool(query="", limit=3)
```

## Adding a New CLI Command

### Step 1: Define the Command

```python
# src/c_e_h/cli.py (add to existing app)
@app.command("mycommand")
def my_command(
    argument: str = typer.Option("default", "--argument", "-a", help="Description"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
):
    """Description of what the command does."""
    if verbose:
        typer.echo(f"Running with argument: {argument}")

    # Command logic
    result = perform_action(argument)
    typer.echo(result)
```

### Step 2: Test the Command

```python
# tests/test_cli.py
from typer.testing import CliRunner
from c_e_h.cli import app

runner = CliRunner()

def test_my_command():
    result = runner.invoke(app, ["mycommand", "--argument", "test", "--verbose"])
    assert result.exit_code == 0
    assert "Running with argument: test" in result.output
```

## Extending the Memory System

### Adding a New Storage Backend

```python
# src/c_e_h/memory.py (extend)
class VectorStoreBackend(ABC):
    """Abstract base for vector store backends."""

    @abstractmethod
    def add(self, documents: list[str], embeddings: list[list[float]]) -> list[str]: ...

    @abstractmethod
    def search(self, query_embedding: list[float], top_k: int) -> list[MemoryResult]: ...
    ...

class FAISSBackend(VectorStoreBackend):
    """FAISS-based vector store."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.index = self._load_or_create_index()

    def add(self, documents: list[str], embeddings: list[list[float]]) -> list[str]:
        # Implementation
        ...
```

### Adding a New Compaction Strategy

```python
# In MemorySystem.compact_context()
def compact_context(self) -> str | None:
    if self._strategy == "snip":
        return self._compact_snip()
    elif self._strategy == "microcompact":
        return self._compact_microcompact()
    elif self._strategy == "summarize":
        return self._compact_summarize()  # New strategy
    else:
        raise ValueError(f"Unknown strategy: {self._strategy}")
```

## Custom Backend Integration

### Implementing a New LLM Backend

```python
# src/c_e_h/new_backend.py
from c_e_h.llama_backend import LlamaBackend

class NewBackend(LlamaBackend):
    """Custom LLM backend implementation."""

    def __init__(self, model_path: str, **kwargs) -> None:
        super().__init__(model_path, **kwargs)
        self._custom_client = self._init_custom_client()

    def generate(self, prompt: str, **kwargs) -> str:
        # Custom generation logic
        response = self._custom_client.generate(prompt, **kwargs)
        return response.text
```

## Debugging Tips

### Enable Verbose Logging

```bash
ceh run -m ./models/model.gguf --verbose "Your prompt"
```

### Check Agent State

```python
from c_e_h.agent import Agent

agent = Agent(model_path="./models/model.gguf")
print(f"State: {agent.state}")
print(f"Permissions: {agent.permissions.mode}")
print(f"Context: {agent.context_window.current_tokens}/{agent.context_window.max_tokens}")
print(f"Error count: {agent._error_count}")
```

### SQLite Database Inspection

```bash
# View sessions
sqlite3 .ceh_state.db "SELECT * FROM sessions ORDER BY started_at DESC LIMIT 10;"

# View context chunks
sqlite3 .ceh_state.db "SELECT role, substr(content, 1, 100) FROM context_chunks LIMIT 20;"

# View agent state
sqlite3 .ceh_state.db "SELECT * FROM agent_state;"
```

### Debug Tool Execution

```python
from c_e_h.tools import ToolRegistry

registry = ToolRegistry()
result = registry.execute("read_file", {"path": "./README.md"})
print(f"Success: {result.success}")
print(f"Error: {result.error}")
print(f"Execution time: {result.execution_time_ms}ms")
```

## Release Process

### Pre-Release Checklist

- [ ] All tests pass (`uv run pytest tests/ -v`)
- [ ] Type checking passes (`uv run mypy src/`)
- [ ] Linting passes (`uv run ruff check src/ tests/`)
- [ ] CHANGELOG.md updated with all changes
- [ ] Version bumped in `pyproject.toml`
- [ ] README.md verified for accuracy
- [ ] API documentation reviewed
- [ ] Security policy reviewed

### Creating a Release

```bash
# 1. Update CHANGELOG.md
# Move [Unreleased] to [vX.Y.Z - YYYY-MM-DD]

# 2. Update version in pyproject.toml
# version = "X.Y.Z"

# 3. Create release branch
git checkout -b release/vX.Y.Z

# 4. Commit changes
git add .
git commit -m "Release vX.Y.Z"

# 5. Create tag
git tag -a vX.Y.Z -m "Version X.Y.Z"

# 6. Push
git push origin release/vX.Y.Z --tags

# 7. Create GitHub Release
# Use RELEASE_NOTES.md for release description
```

### Lesson Tracking

After each release, update the "Lessons Learned" section in [`CHANGELOG.md`](../CHANGELOG.md):

```markdown
### Lessons Learned

**What worked:**
- New CI pipeline caught 3 regressions before merge
- Type checking prevented 2 runtime errors

**What failed:**
- Integration tests flaky on macOS — need to investigate timeout
- Documentation outdated for new CLI commands
```
