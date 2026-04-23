# CLI Reference

> Complete command-line interface documentation for C.E.H.

## Overview

C.E.H. uses [Typer](https://typer.tiangolo.com/) for its CLI framework. The CLI provides a unified interface for all agent operations.

## Commands

### `ceh run`

Start the agent in non-interactive (single-shot) mode.

```bash
ceh run [OPTIONS] [PROMPT]
```

**Arguments:**

| Name | Type | Description |
|------|------|-------------|
| `PROMPT` | `str` | Optional single-shot prompt. If omitted, reads from stdin. |

**Options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--model`, `-m` | `str` | Required | Path to GGUF model file |
| `--config`, `-c` | `str` | `.agent-config.md` | Path to agent configuration file |
| `--n-gpu-layers`, `-ngl` | `int` | `-1` | Number of layers to offload to GPU (`-1` = all) |
| `--n-ctx` | `int` | `8192` | Context window size in tokens |
| `--temperature` | `float` | `0.7` | Sampling temperature |
| `--max-tokens` | `int` | `4096` | Maximum generation tokens |
| `--verbose`, `-v` | `flag` | `False` | Enable verbose output |
| `--quiet`, `-q` | `flag` | `False` | Suppress non-essential output |

**Examples:**

```bash
# Run with a prompt
ceh run -m ./models/llama-3-8b.Q4_K_M.gguf "Write a Python function to sort a list"

# Run with config file
ceh run -m ./models/model.gguf -c ./agent.md

# Verbose mode
ceh run -m ./models/model.gguf --verbose "Analyze this codebase"
```

---

### `ceh interactive`

Start the agent in interactive REPL mode.

```bash
ceh interactive [OPTIONS]
```

**Options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--model`, `-m` | `str` | Required | Path to GGUF model file |
| `--config`, `-c` | `str` | `.agent-config.md` | Path to agent configuration file |
| `--n-gpu-layers`, `-ngl` | `int` | `-1` | Number of layers to offload to GPU |
| `--n-ctx` | `int` | `8192` | Context window size in tokens |
| `--temperature` | `float` | `0.7` | Sampling temperature |
| `--history-file` | `str` | `.ceh_history` | Path to command history file |
| `--verbose`, `-v` | `flag` | `False` | Enable verbose output |

**Examples:**

```bash
# Start interactive session
ceh interactive -m ./models/llama-3-8b.Q4_K_M.gguf

# With custom history
ceh interactive -m ./models/model.gguf --history-file ~/.ceh_history
```

---

### `ceh doctor`

Run system diagnostics to verify the environment.

```bash
ceh doctor [OPTIONS]
```

**Options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--json` | `flag` | `False` | Output results as JSON |
| `--model`, `-m` | `str` | `None` | Optional model path to test inference |

**Output Format:**

```
✅ Python 3.11.7
✅ llama-cpp-python 0.2.78 (GPU: Metal)
✅ GGUF model: llama-3-8b.Q4_K_M.gguf (14.2 GB)
⚠️  n_ctx=8192, but only 6000 tokens available due to VRAM constraints
✅ Permissions: autonomous mode
⚠️  web_search disabled — configure in agent.md to enable
```

---

### `ceh config`

Manage agent configuration.

```bash
ceh config [COMMAND] [OPTIONS]
```

**Subcommands:**

| Command | Description |
|---------|-------------|
| `show` | Display current configuration |
| `validate` | Validate configuration file |
| `init` | Generate default configuration template |

**Examples:**

```bash
# Show current config
ceh config show

# Validate config file
ceh config validate -c ./agent.md

# Generate default config
ceh config init -o ./agent.md
```

---

### `ceh model`

Model management utilities.

```bash
ceh model [COMMAND] [OPTIONS]
```

**Subcommands:**

| Command | Description |
|---------|-------------|
| `info` | Display model metadata (size, quantization, vocab size) |
| `list` | List available models in a directory |
| `download` | Download a GGUF model from HuggingFace |

**Examples:**

```bash
# Show model info
ceh model info -m ./models/llama-3-8b.Q4_K_M.gguf

# List models
ceh model list ./models/

# Download model
ceh model download TheBloke/Llama-3-8B-GGUF llama-3-8b.Q4_K_M.gguf --output ./models/
```

---

### `ceh session`

Session management.

```bash
ceh session [COMMAND] [OPTIONS]
```

**Subcommands:**

| Command | Description |
|---------|-------------|
| `list` | List all sessions |
| `show` | Display session details |
| `clear` | Clear session history |
| `export` | Export session to file |

**Examples:**

```bash
# List sessions
ceh session list

# Show last session
ceh session show --last

# Export session
ceh session export --last -o ./session-export.json
```

---

## Global Options

All commands support these global options:

| Option | Type | Description |
|--------|------|-------------|
| `--version` | `flag` | Show version and exit |
| `--help`, `-h` | `flag` | Show help and exit |

## Exit Codes

| Code | Description |
|------|-------------|
| `0` | Success |
| `1` | General error |
| `2` | Invalid arguments |
| `3` | Model loading failed |
| `4` | Configuration error |
| `5` | Permission denied |

## Configuration File Format

The configuration file (default: `.agent-config.md`) uses Markdown YAML front matter:

```markdown
---
model:
  path: ./models/llama-3-8b.Q4_K_M.gguf
  n_gpu_layers: -1
  n_ctx: 8192
  temperature: 0.7

memory:
  max_context_tokens: 8192
  compaction_strategy: microcompact

permissions:
  mode: autonomous
  max_auto_errors: 3
  success_reset: 5

tools:
  file_read: true
  file_write: true
  execute_command: true
  web_search: false
---
```
