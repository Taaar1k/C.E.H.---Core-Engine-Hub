# Contributing Guide

> How to contribute to C.E.H. (Core Engine Hub)

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Submitting Changes](#submitting-changes)
- [Documentation Contributions](#documentation-contributions)
- [Testing Guidelines](#testing-guidelines)
- [Style Guide](#style-guide)
- [Architecture Decisions](#architecture-decisions)
- [Common Tasks](#common-tasks)

## Code of Conduct

This project adheres to the following principles:

- **Be respectful**: Treat all contributors with respect
- **Be collaborative**: Help others learn and grow
- **be constructive**: Provide actionable feedback
- **Be inclusive**: Welcome contributors of all backgrounds and skill levels

## Getting Started

### Prerequisites

See [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md#prerequisites) for full setup instructions.

### Quick Start

```bash
# 1. Fork the repository
# 2. Clone your fork
git clone https://github.com/YOUR-USERNAME/ceh.git
cd ceh

# 3. Set up development environment
uv venv
source .venv/bin/activate
uv sync --all-extras

# 4. Verify setup
ceh doctor
uv run pytest tests/ -v
```

### Finding Issues to Work On

Look for issues labeled with:

| Label | Description |
|-------|-------------|
| `good-first-issue` | Suitable for new contributors |
| `help-wanted` | Looking for contributors |
| `bug` | Bugs to fix |
| `enhancement` | Feature requests |
| `documentation` | Documentation improvements |

## Development Workflow

### Branch Naming Convention

```
type/description
├── feature/add-tool-registry
├── bugfix/fix-permission-degradation
├── docs/update-readme
├── refactor/simplify-agent-loop
└── release/v0.2.0
```

### Commit Message Format

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
type(scope): description

[optional body]

[optional footer(s)]
```

**Types**:

| Type | Description |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation changes |
| `style` | Code style (formatting, semicolons) |
| `refactor` | Code refactoring |
| `test` | Adding or updating tests |
| `chore` | Maintenance tasks |

**Examples**:

```bash
feat(tools): add web_search tool with Brave API

fix(agent): resolve permission degradation loop

docs: update API reference for MemorySystem
```

### Pull Request Process

1. **Create a feature branch**: `git checkout -b feature/my-feature`
2. **Make your changes**: Write code, update docs, add tests
3. **Run tests**: `uv run pytest tests/ -v`
4. **Run linter**: `uv run ruff check src/ tests/`
5. **Run type checker**: `uv run mypy src/`
6. **Commit your changes**: Follow conventional commits
7. **Push to your fork**: `git push origin feature/my-feature`
8. **Open a Pull Request**: Fill out the PR template

### PR Checklist

- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] Code follows style guide
- [ ] No new warnings from linter
- [ ] Type checking passes
- [ ] CHANGELOG.md updated (if user-visible change)
- [ ] All CI checks pass

## Documentation Contributions

### What to Contribute

| Document | Purpose |
|----------|---------|
| [`README.md`](../README.md) | Quick-start overview |
| [`DOCS/API/*.md`](API/) | API reference |
| [`DOCS/DEVELOPER_GUIDE.md`](DEVELOPER_GUIDE.md) | Developer setup |
| [`DOCS/ARCHITECTURE.md`](ARCHITECTURE.md) | System architecture |
| [`DOCS/SECURITY.md`](SECURITY.md) | Security documentation |
| [`DOCS/CONTRIBUTING.md`](CONTRIBUTING.md) | This file |
| [`CHANGELOG.md`](../CHANGELOG.md) | Version history |
| [`RELEASE_NOTES.md`](../RELEASE_NOTES.md) | Release summaries |

### Documentation Standards

| Standard | Rule |
|----------|------|
| Tone | Technical, clear, concise |
| Code examples | Must be runnable as-is |
| Links | Use relative paths, verify they work |
| Images | Include alt text, optimize file size |
| Tables | Keep columns aligned, limit width |

### Reviewing Documentation

When reviewing documentation PRs:

1. **Accuracy**: Is the information correct?
2. **Completeness**: Does it cover all necessary points?
3. **Clarity**: Is it easy to understand?
4. **Consistency**: Does it match existing style?
5. **Links**: Do all links work?

## Testing Guidelines

### Writing Tests

```python
# tests/test_example.py
import pytest
from c_e_h.example import example_function

class TestExampleFunction:
    """Tests for example_function."""

    def test_returns_expected_value(self):
        """Function returns correct value for valid input."""
        result = example_function("test")
        assert result == "expected"

    def test_raises_on_invalid_input(self):
        """Function raises ValueError on empty string."""
        with pytest.raises(ValueError, match="Input cannot be empty"):
            example_function("")

    @pytest.mark.slow
    def test_performance(self):
        """Function completes within time budget."""
        import time
        start = time.perf_counter()
        example_function("large_input" * 1000)
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0  # 1 second budget
```

### Test Categories

| Category | Marker | When to Use |
|----------|--------|-------------|
| Unit | (default) | Fast, isolated tests |
| Integration | `@pytest.mark.integration` | Multi-component tests |
| Slow | `@pytest.mark.slow` | Tests >1 second |
| Model | `@pytest.mark.model` | Tests requiring model file |

### Current Test Suite

The project has **22 test files** covering all major modules:

| Test File | Module Under Test |
|-----------|-------------------|
| [`tests/test_agent.py`](../tests/test_agent.py) | Agent engine |
| [`tests/test_clean_display.py`](../tests/test_clean_display.py) | CleanChatDisplay UI |
| [`tests/test_cli.py`](../tests/test_cli.py) | CLI commands |
| [`tests/test_db_migrate.py`](../tests/test_db_migrate.py) | Database migrations |
| [`tests/test_debug.py`](../tests/test_debug.py) | Debug utilities |
| [`tests/test_integration_config_expansion.py`](../tests/test_integration_config_expansion.py) | Config expansion integration |
| [`tests/test_integration.py`](../tests/test_integration.py) | End-to-end integration |
| [`tests/test_launcher.py`](../tests/test_launcher.py) | InteractiveLauncher |
| [`tests/test_llama_backend.py`](../tests/test_llama_backend.py) | Llama backend |
| [`tests/test_logging_config.py`](../tests/test_logging_config.py) | Logging configuration |
| [`tests/test_memory.py`](../tests/test_memory.py) | Memory system |
| [`tests/test_model_registry.py`](../tests/test_model_registry.py) | Model registry |
| [`tests/test_model_scanner.py`](../tests/test_model_scanner.py) | Model scanner |
| [`tests/test_plugin.py`](../tests/test_plugin.py) | Plugin system |
| [`tests/test_profile_manager.py`](../tests/test_profile_manager.py) | Profile manager |
| [`tests/test_security.py`](../tests/test_security.py) | Security policy |
| [`tests/test_session_manager.py`](../tests/test_session_manager.py) | Session manager |
| [`tests/test_shutdown.py`](../tests/test_shutdown.py) | Shutdown handler |
| [`tests/test_streaming.py`](../tests/test_streaming.py) | Streaming utilities |
| [`tests/test_tools.py`](../tests/test_tools.py) | Tool framework |
| [`tests/test_ui_dashboard.py`](../tests/test_ui_dashboard.py) | Dashboard UI |
| [`tests/test_ui_session.py`](../tests/test_ui_session.py) | Session UI |
| [`tests/test_ui_streaming.py`](../tests/test_ui_streaming.py) | UI streaming |
| [`tests/test_ui_widgets.py`](../tests/test_ui_widgets.py) | UI widgets |

### Running Tests

```bash
# All tests
uv run pytest tests/ -v

# Only slow tests
uv run pytest tests/ -v -m "slow"

# With coverage
uv run pytest tests/ -v --cov=src/c_e_h --cov-report=term-missing

# Skip model tests (no model file)
uv run pytest tests/ -v -m "not model"
```

## Style Guide

### Python Style

C.E.H. uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting.

```bash
# Check style
uv run ruff check src/ tests/

# Auto-fix
uv run ruff check --fix src/ tests/

# Format
uv run ruff format src/ tests/
```

### Type Hints

Type hints are **required** for all public functions:

```python
def process_data(data: list[str], config: dict[str, Any]) -> dict[str, Any]:
    """Process input data.

    Args:
        data: Input data list.
        config: Configuration dictionary.

    Returns:
        Processed data.
    """
    ...
```

### Docstrings

Use Google-style docstrings:

```python
def example_function(arg1: str, arg2: int = 10) -> bool:
    """Short one-line description.

    Longer description if needed. Explain the purpose and behavior.

    Args:
        arg1: Description of arg1.
        arg2: Description of arg2. Default is 10.

    Returns:
        Description of return value.

    Raises:
        ValueError: When arg1 is empty.
        TypeError: When arg2 is not an integer.

    Example:
        >>> example_function("test", 5)
        True
    """
```

### Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Module | `snake_case` | `my_tool.py` |
| Class | `PascalCase` | `PermissionManager` |
| Function | `snake_case` | `validate_path()` |
| Constant | `UPPER_SNAKE_CASE` | `MAX_RETRIES` |
| Private | `_leading_underscore` | `_internal_helper()` |

## Architecture Decisions

When making architectural changes, document them in [`DOCS/ARCHITECTURE.md`](ARCHITECTURE.md) and consider creating an Architecture Decision Record (ADR):

```markdown
# ADR-XXX: Decision Topic

- **Status**: Proposed | Accepted | Deprecated | Superseded
- **Date**: YYYY-MM-DD
- **Context**: What is the issue being addressed?
- **Decision**: What did we decide?
- **Consequences**: What are the trade-offs?
```

## Common Tasks

### Adding a New Tool

See [DEVELOPER_GUIDE.md#adding-a-new-tool](DEVELOPER_GUIDE.md#adding-a-new-tool) for step-by-step instructions.

### Adding a New CLI Command

See [DEVELOPER_GUIDE.md#adding-a-new-cli-command](DEVELOPER_GUIDE.md#adding-a-new-cli-command) for step-by-step instructions.

### Updating Dependencies

```bash
# Update all dependencies
uv sync --upgrade

# Update specific package
uv add pydantic --upgrade

# Audit dependencies
./scripts/audit_deps.sh

# Commit lock file
git add uv.lock
```

### Creating a Release

See [DEVELOPER_GUIDE.md#release-process](DEVELOPER_GUIDE.md#release-process) for the full release checklist.

### Writing CHANGELOG Entry

```markdown
## [Unreleased]

### Added
- New `weather` tool for fetching current conditions (PR #XXX)

### Fixed
- Permission degradation loop when errors alternate with successes (PR #XXX)

### Changed
- Context compaction now preserves system messages (PR #XXX)
```

## Getting Help

| Channel | Purpose |
|---------|---------|
| [GitHub Issues](https://github.com/your-org/ceh/issues) | Bug reports, feature requests |
| [GitHub Discussions](https://github.com/your-org/ceh/discussions) | Questions, ideas |
| [`DOCS/`](DOCS/) | Documentation |
| [`MEMORY/TASKS/`](../MEMORY/TASKS/) | Current task tracking |

## Recognition

Contributors are recognized in:

1. [`CHANGELOG.md`](../CHANGELOG.md) — in each release
2. [`README.md`](../README.md#acknowledgments) — in Acknowledgments
3. Release notes — in Highlights section

Thank you for contributing to C.E.H.!
