# C.E.H. — Core Engine Hub

> **Minimalist, secure, and cross-platform local agent framework based on `llama.cpp`**, inspired by Claude Code's architecture.

[![Python 3.11 | 3.12 | 3.13 | 3.14](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status: Feature-Complete v0.1.0](https://img.shields.io/badge/status-feature--complete%20v0.1.0-success.svg)]()
[![Tests](https://img.shields.io/badge/tests-654%20collected%2F625%20passed-informational.svg)](tests/)

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Installation](#installation)
- [Model Setup](#model-setup)
- [Configuration](#configuration)
- [Usage](#usage)
- [Features](#features)
- [Testing](#testing)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgments](#acknowledgments)

---

## Overview

C.E.H. is a **fully local** agent framework that runs powerful large language models (LLMs) on your machine using **GGUF quantized models** via [`llama.cpp`](https://github.com/ggerganov/llama.cpp). It is designed for users who want:

- **Exclusive locality** — no cloud services, no API keys, no data leaves your machine
- **Maximum simplicity** — one command to start, intuitive configuration
- **Real power** — from basic code generation to complex multi-step business processes
- **Cross-platform** — works on Linux, macOS (including Apple Silicon), and Windows

### Key Principles

| Principle | Description |
|-----------|-------------|
| **100% Local** | All inference, memory, and tool execution happen on your machine |
| **GGUF Native** | Uses quantized GGUF models for efficient CPU/GPU inference |
| **Minimal Dependencies** | <30 direct packages, no AI "all-in-one" frameworks |
| **Secure by Default** | Permission system with graceful degradation, sandboxed execution |
| **Extensible** | Plugin-based tool system with MCP adapter support |

---

## Architecture

C.E.H. follows a **sequential scaling** approach: single-agent first, multi-agent swarm on demand.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            C.E.H. Core Engine                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌───────────────┐  │
│  │   CLI     │    │  Agent    │    │  Memory   │    │    Tools      │  │
│  │  (Typer)  │◄──►│  Engine   │◄──►│  System   │◄──►│  Framework    │  │
│  └───────────┘    └─────┬─────┘    └───────────┘    └───────┬───────┘  │
│                         │                                    │           │
│                         ▼                                    ▼           │
│              ┌─────────────────┐                  ┌─────────────────┐   │
│              │  Context Window │                  │  Tool Registry  │   │
│              │  + Compaction   │                  │  + Sandbox      │   │
│              └─────────────────┘                  └─────────────────┘   │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                     LLM Backend Layer                             │  │
│  │  ┌─────────────────────────────────────────────────────────────┐  │  │
│  │  │              llama-cpp-python (GGUF)                        │  │  │
│  │  │  • Model loading  • Inference  • Grammar sampling           │  │  │
│  │  └─────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Scaling Strategy

```
Single Agent Mode (default)
    │
    ├── Understands user intent
    ├── Manages context window
    ├── Executes tools safely
    └── Learns from experience
    │
    ▼ (on complex tasks)
Multi-Agent Swarm Mode (optional)
    │
    ├── Planner: decomposes goals into subtasks
    ├── Executors: specialized agents per domain
    └── Orchestrator: manages dependencies & parallelism
```

For detailed architecture documentation, see [`DOCS/ARCHITECTURE.md`](DOCS/ARCHITECTURE.md).

---

## Installation

### Prerequisites

- **Python 3.11, 3.12, 3.13, or 3.14**
- **uv** package manager: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **llama.cpp** — provided automatically via [`llama-cpp-python`](https://github.com/abetlen/llama-cpp-python)

### Quick Start

```bash
# Clone the repository
git clone https://github.com/your-org/c-e-h.git
cd "C.E.H. - Core Engine Hub"

# Create virtual environment with uv
uv venv .venv

# Activate the environment
# macOS / Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# Install dependencies
uv sync

# Verify installation
ceh version
# Expected: C.E.H. v0.1.0
```

### Optional Dev Dependencies

```bash
uv sync --extra dev
```

For complete installation instructions including GPU setup (CUDA, Vulkan, Metal), see [`DOCS/INSTALLATION.md`](DOCS/INSTALLATION.md).

---

## Model Setup

### Download via Registry

C.E.H. includes a model registry for secure downloads with SHA256 verification:

```bash
# List registered models
ceh model list

# Download a model
ceh model download --name <model-id>

# Verify model integrity
ceh model verify --id <model-id>
```

**Download Features:**
- HTTPS-only enforcement
- SHA256 checksum verification after download
- Atomic writes (downloads to `.tmp`, renames after verification)
- Resume support via HTTP `Range` headers
- Retry with exponential backoff (max 5 retries)

### Manual Model Placement

1. Download a GGUF model from a trusted source (e.g., Hugging Face)
2. Place the `.gguf` file in any directory (e.g., `models/`)

```bash
mkdir -p models
wget "https://huggingface.co/.../model.gguf" -O models/model.gguf
```

### Scan for Models

```bash
# Scan a specific directory
ceh run --scan-dir ./models

# Scan the default directory
ceh run
```

---

## Configuration

### Agent Configuration (`agent.md`)

Create or edit `agent.md` in the project root:

```markdown
# Agent Configuration

## Identity
name: CEH-Agent
version: 0.1.0
description: Your local AI assistant

## Model Settings
model:
  path: ./models/model.gguf
  n_gpu_layers: -1        # Offload all layers to GPU
  n_ctx: 8192              # Context window size
  temperature: 0.7         # Sampling temperature

## Memory Settings
memory:
  max_context_tokens: 8192
  compaction_strategy: microcompact  # snip | microcompact

## Permission Settings
permissions:
  mode: autonomous         # autonomous | approval
  max_auto_errors: 3       # Switch to approval mode after N errors
  success_reset: 5         # Reset to autonomous after N successful steps
```

### Configuration Profiles (`profiles.yaml`)

C.E.H. supports **configuration profiles** for saving and switching model parameters without editing `agent.md` manually.

**Easy Mode** — 9 common llama.cpp parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | *(required)* | Unique profile name |
| `model` | `str` | *(required)* | Path to GGUF model file |
| `n_gpu_layers` | `int` | `-1` | GPU offload layers (`-1` = all) |
| `threads` | `int \| None` | `None` | CPU threads (`None` = auto) |
| `ctx_size` | `int` | `8192` | Context window in tokens |
| `flash_attn` | `str` | `"auto"` | Flash attention mode |
| `cache_type_k` | `str` | `"q8_0"` | Key cache quantization |
| `cache_type_v` | `str` | `"q8_0"` | Value cache quantization |
| `temperature` | `float` | `0.7` | Sampling temperature |

**Advanced Mode** — 120+ llama.cpp flags including `top_k`, `top_p`, `seed`, `repeat_penalty`, `lora`, `rope_scaling`, and more.

See [`DOCS/CONFIG/PROFILES.md`](DOCS/CONFIG/PROFILES.md) for complete profile documentation.

---

## Usage

### CLI Command Reference

| Command | Description |
|---------|-------------|
| `ceh run` | Interactive launcher with model/profile selection |
| `ceh interactive` | REPL-style agent interaction |
| `ceh stream` | Streaming text generation |
| `ceh dashboard` | Real-time TUI dashboard |
| `ceh sessions` | Session management UI |
| `ceh cleanup` | TTL-based session cleanup |
| `ceh version` | Show version info |

### Model Commands

| Command | Description |
|---------|-------------|
| `ceh model download --name <id>` | Download model from registry |
| `ceh model list` | List registered models |
| `ceh model show --id <id>` | Show model details |
| `ceh model remove --id <id>` | Remove model from registry |
| `ceh model verify --id <id>` | Verify model SHA256 checksum |

### Session Commands

| Command | Description |
|---------|-------------|
| `ceh sessions new --name <name>` | Create new session |
| `ceh sessions list` | List all sessions |
| `ceh sessions switch --id <id>` | Switch active session |
| `ceh sessions delete --id <id>` | Delete session |

### Plugin Commands

| Command | Description |
|---------|-------------|
| `ceh plugin list` | List discovered plugins |

### Key Flags

| Flag | Description |
|------|-------------|
| `--model/-m <path>` | Path to GGUF model file |
| `--scan-dir/-S <dir>` | Directory to scan for `.gguf` models |
| `--gpu-layers/-g <n>` | Number of layers to offload to GPU (`-1` = all) |
| `--ctx-size/-c <n>` | Context window size in tokens |
| `--config/-C <path>` | Path to `agent.md` config file |
| `--display-mode/-D <mode>` | Display mode: `clean` or `streaming` |
| `--log-level/-l <level>` | Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `--debug/-d` | Enable debug mode |
| `--verbose/-v` | Enable verbose output |

### Examples

```bash
# Start interactive agent with model auto-selection
ceh run

# Start with specific model and GPU offload
ceh run --model ./models/llama-3-8b.Q4_K_M.gguf --gpu-layers -1

# Streaming generation with custom prompt
ceh stream --model ./models/model.gguf --prompt "Write a Python function" --max-tokens 256

# Launch real-time dashboard
ceh dashboard

# Clean up sessions older than 7 days
ceh cleanup --max-age-days 7

# Dry run cleanup (preview only)
ceh cleanup --dry-run
```

---

## Features

### Agent Engine

- [`AgentConfig`](src/c_e_h/agent.py) — Pydantic-based configuration with full model, memory, and permission settings
- [`AgentState`](src/c_e_h/agent.py) — Runtime state with step counting, mode tracking, context management
- Display modes: `clean` (spinner + final response) and `streaming` (token-by-token)
- Permission modes: `autonomous` and `approval` with automatic error-based degradation
- Lazy backend loading (avoids import errors when llama-cpp-python not installed)

### 3-Tier Memory System

| Tier | Storage | Purpose | Lifetime |
|------|---------|---------|----------|
| **Persistent** | `agent.md` + SQLite | Identity, config, long-term instructions | Permanent |
| **Short-term** | Context window + SQLite | Current session conversation with compaction | Session |
| **Long-term** | FAISS / ChromaDB vector store | Semantic memory across sessions | Permanent |

- Compaction strategies: `snip` (trim oldest) and `microcompact` (LLM summarize)
- System prompt protection: instruction chunks never trimmed
- Atomic transactions via sqlite3

### Tools Framework (10 Built-in Tools)

| Tool | Description |
|------|-------------|
| `read_file` | Read file with line limit |
| `write_file` | Write/append file |
| `execute_command` | Sandboxed subprocess (shell=False) |
| `web_search` | Brave Search API |
| `list_directory` | List directory contents |
| `create_directory` | Create directory |
| `delete_file` | Safe file deletion |
| `import_module` | Whitelist-based import (stdlib only) |
| `search_files` | Glob pattern search |
| `github` | GitHub API operations |

- Permission management with autonomous/approval modes
- Sandboxed execution: `shell=False`, restricted environment, 30s timeout
- MCP adapter for Model Context Protocol integration

### Security

- Path traversal prevention via `os.path.realpath()`
- Command whitelist: `ls`, `cat`, `grep`, `find`, `git`, `cp`, `mv`, `rm`, `mkdir`, `echo`
- Input sanitization: 10K character limit, type checking
- Security event logging
- HTTPS-only model downloads with SHA256 verification

### UI Modules

| Module | Description |
|--------|-------------|
| **Clean Display** | Spinner + final response rendering |
| **Dashboard** | Real-time multi-panel TUI (agent status, sessions, metrics) |
| **Streaming** | Token-by-token display with Rich Live |
| **Session UI** | Session browser with filter, create, delete |
| **Launcher** | Interactive model/profile selection |
| **Widgets** | Reusable Rich UI components |

### Grammar Engine

- GBNF structured output via [`grammar.py`](src/c_e_h/grammar.py)
- Enables deterministic JSON and structured responses

### Prompt Templates

- ChatML, Llama 3, and Mistral template formats
- Configurable via [`prompt_template.py`](src/c_e_h/prompt_template.py)

### Plugin System

- Entry points discovery via [`plugin.py`](src/c_e_h/plugin.py)
- `ceh plugin list` to discover installed plugins

### Model Registry

- SHA256 verification for model integrity
- Atomic writes (downloads to `.tmp`, renames after verification)
- Registry metadata in `~/.ceh/models.json`

### Database Migrations

- Versioned SQLite schema via [`db_migrate.py`](src/c_e_h/db_migrate.py)
- Automatic migration on startup

---

## Testing

C.E.H. maintains comprehensive test coverage:

```bash
# Run all tests
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ --cov=c_e_h --cov-report=html
```

| Metric | Count |
|--------|-------|
| Tests collected | 654 |
| Tests passed | 625 |
| Pre-existing failures | 2 |

Test files are located in [`tests/`](tests/), covering all core modules including agent, CLI, memory, tools, security, streaming, model registry, profile manager, and UI components.

---

## Documentation

Comprehensive documentation is available in the [`DOCS/`](DOCS/) directory:

| Document | Path |
|----------|------|
| **Installation Guide** | [`DOCS/INSTALLATION.md`](DOCS/INSTALLATION.md) |
| **Architecture** | [`DOCS/ARCHITECTURE.md`](DOCS/ARCHITECTURE.md) |
| **Profile Management** | [`DOCS/CONFIG/PROFILES.md`](DOCS/CONFIG/PROFILES.md) |
| **UI Documentation** | [`DOCS/UI/README.md`](DOCS/UI/README.md) |
| **API Reference** | [`DOCS/API/README.md`](DOCS/API/README.md) |
| **Security Policy** | [`DOCS/SECURITY.md`](DOCS/SECURITY.md) |
| **Contributing Guidelines** | [`DOCS/CONTRIBUTING.md`](DOCS/CONTRIBUTING.md) |
| **Developer Guide** | [`DOCS/DEVELOPER_GUIDE.md`](DOCS/DEVELOPER_GUIDE.md) |

**Quick links:** [`CHANGELOG.md`](CHANGELOG.md) · [`RELEASE_NOTES.md`](RELEASE_NOTES.md) · [`SECURITY.md`](SECURITY.md) · [`DEPENDENCY_POLICY.md`](DEPENDENCY_POLICY.md)

---

## Contributing

Contributions are welcome! Please read [`DOCS/CONTRIBUTING.md`](DOCS/CONTRIBUTING.md) before submitting PRs.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`uv run pytest`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

---

## License

This project is licensed under the MIT License — see the [`LICENSE`](LICENSE) file for details.

---

## Acknowledgments

- **[llama.cpp](https://github.com/ggerganov/llama.cpp)** by Georgi Gerganov — the foundation of local LLM inference
- **[Claude Code](https://www.anthropic.com/claude-code)** — architectural inspiration for agent design
- **[llama-cpp-python](https://github.com/abetlen/llama-cpp-python)** — Python bindings for llama.cpp
- **[uv](https://github.com/astral-sh/uv)** — the fast Python package installer and resolver
- **TheBloke** — GGUF model quantizations on HuggingFace

---

<div align="center">

**C.E.H.** — *Your AI, Your Machine, Your Control.*

</div>
