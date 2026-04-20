# C.E.H. — Core Engine Hub

> **Minimalist, secure, and cross-platform local agent framework based on `llama.cpp`**, inspired by Claude Code's architecture.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status: Planning](https://img.shields.io/badge/status-planning-orange.svg)]()

---

## 📋 Overview

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

## 🏗️ Architecture

C.E.H. follows a **sequential scaling** approach:

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

### System Components

```
┌─────────────────────────────────────────────────────────┐
│                      C.E.H. Core                        │
├─────────────┬──────────────┬──────────────┬─────────────┤
│  Agent      │  Memory      │  Tools       │  LLM        │
│  Engine     │  System      │  Framework   │  Backend    │
├─────────────┼──────────────┼──────────────┼─────────────┤
│ • Task loop │ • Persistent │ • Registry   │ • llama.cpp │
│ • Decision  │ • Short-term │ • Validation │ • GGUF load │
│ • Error mgmt│ • Long-term  │ • Sandbox    │ • Grammar   │
│ • State mgmt│ • sqlite3    │ • MCP adapter│ • Token mgmt│
└─────────────┴──────────────┴──────────────┴─────────────┘
```

---

## 📦 Installation

### Prerequisites

- **Python 3.11** or **3.12** (LTS recommended)
- **uv** package manager: `pip install uv`
- **llama.cpp** compiled binaries (auto-configured via `llama-cpp-python`)

### Quick Start

```bash
# Clone the repository
git clone https://github.com/your-org/c-e-h.git
cd c-e-h

# Create virtual environment with uv
uv venv

# Activate the virtual environment
# Linux/macOS:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# Install dependencies
uv sync

# Verify installation
python -c "import llama_cpp; import pydantic; import typer; print('OK')"
```

### Download a Model

Place a GGUF model in the `models/` directory:

```bash
mkdir -p models
# Example: Download Llama 3 8B (Q4_K_M quantization)
# Visit https://huggingface.co/TheBloke to find GGUF models
```

### ❓ Troubleshooting Installation

#### Windows

```bash
# Install Build Tools for Visual Studio (required to compile llama-cpp-python)
winget install Microsoft.VisualStudio.2022.BuildTools --quiet --wait

# Then retry installation
uv sync
```

#### Linux + AMD GPU (Vulkan)

```bash
# Install Vulkan drivers
sudo apt install libvulkan-dev mesa-vulkan-drivers  # Debian/Ubuntu
# OR
sudo dnf install vulkan-loader vulkan-icd-loader     # Fedora/RHEL

# Build llama-cpp-python with Vulkan support
CMAKE_ARGS="-DGGML_VULKAN=1" uv sync

# Add your user to render/video groups for GPU access
sudo usermod -aG render,$USER
sudo usermod -aG video,$USER
# Log out and back in for group changes to take effect
```

#### Apple Silicon

✅ **Works out of the box.** Ensure Xcode Command Line Tools are installed:

```bash
xcode-select --install
```

`llama-cpp-python` automatically uses Metal backend on Apple Silicon — no extra configuration needed.

---

## 🚀 Usage

### Basic Interaction

```bash
# Start the agent with a model
c-e-h run --model ./models/llama-3-8b.Q4_K_M.gguf

# Or use the interactive CLI
c-e-h interactive --model ./models/llama-3-8b.Q4_K_M.gguf
```

### Configuration

Create or edit `.agent-config.md` (or `agent.md`) in the project root:

```markdown
# Agent Configuration

## Identity
name: CEH-Agent
version: 0.1.0
description: Your local AI assistant

## Model Settings
model:
  path: ./models/llama-3-8b.Q4_K_M.gguf
  n_gpu_layers: -1        # Offload all layers to GPU (Apple Silicon / Vulkan)
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

## Tools
tools:
  file_read: true
  file_write: true
  execute_command: true
  web_search: false        # Disabled by default
```

---

## 🔒 Security

C.E.H. is designed with security as a first-class concern:

| Layer | Mechanism |
|-------|-----------|
| **Permission System** | Graceful degradation: autonomous → approval mode after errors |
| **Tool Validation** | Pydantic-based schema validation for all tool arguments |
| **Sandboxed Execution** | `shell=False`, restricted environment, timeout limits |
| **Injection Protection** | Argument sanitization before command execution |
| **Least Privilege** | Runs with minimal filesystem and network permissions |

### Default Tool Permissions

| Action | Allowed | Notes |
|--------|---------|-------|
| **File reading** | ✅ | Within `cwd` only, path traversal blocked |
| **File writing** | ⚠️ | Requires confirmation if `permissions.mode=approval` |
| **Command execution** | ⚠️ | `shell=False`, 30s timeout, dangerous commands blocked (`rm -rf`, `curl`, `wget`) |
| **Network requests** | ❌ | Disabled by default, enable in `agent.md` |
| **Python imports** | ⚠️ | Standard library + `pydantic`, `rich` only |

See [`SECURITY.md`](SECURITY.md) for full sandbox details and threat model.

---

### 🧠 How Memory Works

```
project/
├── agent.md              # Persistent config (read/write)
├── .ceh_state.db         # SQLite: sessions, steps, context chunks
├── MEMORY/
│   └── sessions/         # Archived session summaries (JSON)
└── embeddings/           # (Optional) FAISS for semantic search
```

**Memory tiers:**

| Tier | Storage | Purpose | Lifetime |
|------|---------|---------|----------|
| **Persistent** | `agent.md` | Identity, config, long-term instructions | Permanent |
| **Short-term** | Context window + SQLite | Current session conversation | Session |
| **Long-term** | Vector DB (FAISS/ChromaDB) | Semantic memory across sessions | Permanent |

**Context compaction strategies:**

| Strategy | Behavior | Use case |
|----------|----------|----------|
| `snip` | Trims oldest context when limit exceeded | Simple, fast, no LLM overhead |
| `microcompact` | Summarizes trimmed context via LLM call | Preserves semantic meaning |

---

### 🖥️ Hardware Expectations (Approximate)

| Model | Quantization | Min VRAM | Recommended RAM | Expected Speed |
|-------|-------------|----------|-----------------|----------------|
| **7B** (e.g., Llama 3.2) | Q4_K_M | 6 GB | 16 GB | 15–25 tokens/sec |
| **14B** (e.g., Mistral 7B v0.3) | Q4_K_M | 10 GB | 24 GB | 8–15 tokens/sec |
| **32B** (e.g., Qwen 2.5) | Q4_K_M | 20 GB | 32 GB | 3–7 tokens/sec* |
| **70B+** | Q4_K_M | 40 GB | 64 GB | 1–3 tokens/sec* |

\* With `n_gpu_layers=-1` on RTX 4090 / M2 Max. On CPU only: 1–2 tokens/sec.

> **Tip:** Start with a 7B–14B model for best balance of speed and capability. Upgrade as your hardware allows.

---

## 📁 Project Structure

```
c-e-h/
├── pyproject.toml          # Project configuration & dependencies
├── uv.lock                 # Deterministic dependency lock file
├── README.md               # This file
├── agent.md                # Agent configuration template
├── .gitignore              # Git ignore rules
├── src/
│   └── c_e_h/
│       ├── __init__.py     # Package initialization
│       ├── cli.py          # CLI interface (typer)
│       ├── agent.py        # Core agent class
│       ├── memory.py       # 3-tier memory system
│       ├── tools.py        # Tool registry & execution
│       └── llama_backend.py # llama.cpp integration
├── tests/
│   ├── __init__.py
│   ├── test_cli.py
│   ├── test_agent.py
│   ├── test_memory.py
│   └── test_tools.py
├── models/                 # GGUF model storage
├── scripts/
│   ├── setup.sh            # Setup script
│   └── audit_deps.sh       # Dependency audit script
└── MEMORY/                 # Project state & task tracking
    ├── PROJECT_STATE.md
    ├── TASK_BOARD.md
    ├── EVIDENCE_STANDARD.md
    ├── EXECUTION_MODE_POLICY.md
    └── TASKS/
```

---

## 🧪 Development

### Diagnostic Command

```bash
# Run system diagnostics
$ c-e-h doctor
✅ Python 3.11.7
✅ llama-cpp-python 0.2.78 (GPU: Metal)
✅ GGUF model: llama-3-8b.Q4_K_M.gguf (14.2 GB)
⚠️  n_ctx=8192, but only 6000 tokens available due to VRAM constraints
✅ Permissions: autonomous mode
⚠️  web_search disabled — configure in agent.md to enable
```

### Running Tests

```bash
uv run pytest tests/ -v
```

#### Example Tests

```python
# tests/test_tools.py
def test_file_read_validation():
    """Verify read_file blocks path traversal outside cwd"""
    with pytest.raises(ValidationError):
        execute_tool("read_file", path="../../../etc/passwd")

def test_permission_degradation():
    """After 3 errors, agent switches to approval mode"""
    agent = Agent(permissions={"max_auto_errors": 3})
    for _ in range(3):
        agent.record_error()
    assert agent.permissions.mode == "approval"
```

### Linting & Type Checking

```bash
uv run ruff check src/ tests/
uv run mypy src/
```

### Updating Dependencies

```bash
# Update all dependencies
uv sync --upgrade

# Update a specific package
uv add pydantic --upgrade

# Audit dependencies
./scripts/audit_deps.sh
```

### Example Plugin

Create a custom tool in `src/c_e_h/tools/`:

```python
# tools/github.py
from c_e_h.tools import tool, ToolResult

@tool(
    name="create_issue",
    description="Create a GitHub issue in a repository",
    requires_permission=True
)
def create_issue(repo: str, title: str, body: str) -> ToolResult:
    """Creates an issue using PyGithub library."""
    import os
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        return ToolResult(error="GITHUB_TOKEN not configured")
    
    # Implementation via PyGithub
    # ...
    return ToolResult(success=True, data={"url": f"https://github.com/{repo}/issues/{number}"})
```

Register in `agent.md`:

```yaml
tools:
  github:
    enabled: true
    token_env: GITHUB_TOKEN
```

---

## 📜 Dependency Policy

C.E.H. follows a strict dependency management policy for long-term stability:

- **Python LTS only**: 3.11 or 3.12
- **Max 30 direct dependencies**
- **No AI "all-in-one" frameworks** (LangChain, LlamaIndex, CrewAI, etc.)
- **Quarterly updates**: patch/minor versions only, no major bumps without approval
- **Deterministic builds**: `uv.lock` committed to version control

See [`DEPENDENCY_POLICY.md`](DEPENDENCY_POLICY.md) for full details.

---

## 🗺️ Roadmap

| Phase | Status | Features |
|-------|--------|----------|
| **P0: Foundation** | 🔄 In Progress | Project scaffolding, core agent, llama.cpp backend |
| **P1: Intelligence** | 📋 Planned | 3-tier memory, tool system, permission management |
| **P2: Stability** | 📋 Planned | Dependency audit, CI/CD, documentation |
| **P3: Swarm** | 📋 Planned | Multi-agent orchestration, planner/executor pattern |
| **P4: Production** | 📋 Planned | Advanced sandboxing, MCP ecosystem, cross-platform testing |

---

## 🔄 CI/CD

C.E.H. uses GitHub Actions for automated testing across platforms:

```yaml
# .github/workflows/test.yml
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: uv-python/setup-python@v1
        with:
          python-version: ${{ matrix.python }}
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --frozen
      - run: uv run pytest tests/ -v
      - run: uv run ruff check src/ tests/
      - run: uv run mypy src/
```

Monthly dependency audit runs automatically on the 1st of each month.

---

## 🤝 Contributing

Contributions are welcome! Please read the following before submitting PRs:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`uv run pytest`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **[llama.cpp](https://github.com/ggerganov/llama.cpp)** by Georgi Gerganov — the foundation of local LLM inference
- **[Claude Code](https://www.anthropic.com/claude-code)** — architectural inspiration for agent design
- **[llama-cpp-python](https://github.com/abetlen/llama-cpp-python)** — Python bindings for llama.cpp
- **TheBloke** — GGUF model quantizations on HuggingFace

---

<div align="center">

**C.E.H.** — *Your AI, Your Machine, Your Control.*

</div>
