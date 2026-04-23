# C.E.H. API Documentation

> Complete reference for the Core Engine Hub application programming interfaces.

## Overview

This directory contains detailed API documentation for all public interfaces in C.E.H. The framework is organized into five core subsystems:

| Module | Description | File |
|--------|-------------|------|
| [CLI](cli.md) | Command-line interface reference | `src/c_e_h/cli.py` |
| [Agent](agent.md) | Core agent class and task loop | `src/c_e_h/agent.py` |
| [Memory](memory.md) | Three-tier memory system | `src/c_e_h/memory.py` |
| [Tools](tools.md) | Tool registry and execution framework | `src/c_e_h/tools.py` |
| [Llama Backend](llama_backend.md) | llama.cpp integration layer | `src/c_e_h/llama_backend.py` |

## Quick Navigation

- **Getting Started**: Read [`cli.md`](cli.md) for command-line usage, then [`agent.md`](agent.md) for the core agent lifecycle.
- **Extending C.E.H.**: See [`tools.md`](tools.md) for creating custom tools, then [`agent.md`](agent.md) for agent configuration.
- **Memory System**: Refer to [`memory.md`](memory.md) for context management, compaction strategies, and persistence.
- **LLM Integration**: See [`llama_backend.md`](llama_backend.md) for model loading, inference, and grammar sampling.

## Architecture Summary

```
┌─────────────────────────────────────────────────────────┐
│                      C.E.H. Core                        │
├─────────────┬──────────────┬──────────────┬─────────────┤
│  Agent      │  Memory      │  Tools       │  LLM        │
│  Engine     │  System      │  Framework   │  Backend    │
├─────────────┼──────────────┼──────────────┼─────────────┤
│ cli.py      │ memory.py    │ tools.py     │ llama_     │
│ agent.py    │              │              │ backend.py  │
└─────────────┴──────────────┴──────────────┴─────────────┘
```

## Versioning

C.E.H. follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html). API documentation is versioned alongside the project. Breaking changes to public APIs will be documented in [`CHANGELOG.md`](../../CHANGELOG.md) with migration instructions.

## License

MIT License — see [`LICENSE`](../../LICENSE) for details.
