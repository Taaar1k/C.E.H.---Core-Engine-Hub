# C.E.H. API Documentation

> Complete reference for the Core Engine Hub application programming interfaces.

## Overview

This directory contains detailed API documentation for all public interfaces in C.E.H. The framework is organized into six core subsystems:

| Module | Description | File |
|--------|-------------|------|
| [CLI](cli.md) | Command-line interface reference | `src/c_e_h/cli.py` |
| [Agent](agent.md) | Core agent class and task loop | `src/c_e_h/agent.py` |
| [Memory](memory.md) | Three-tier memory system | `src/c_e_h/memory.py` |
| [Tools](tools.md) | Tool registry and execution framework | `src/c_e_h/tools.py` |
| [Llama Backend](llama_backend.md) | llama.cpp integration layer | `src/c_e_h/llama_backend.py` |
| [Security](../SECURITY.md) | Security policy and sandboxing | `src/c_e_h/security.py` |

## Additional Modules

C.E.H. includes several supporting modules not yet fully documented in this API directory:

| Module | Description | File |
|--------|-------------|------|
| [Grammar Engine](#) | Structured output compilation and parsing | `src/c_e_h/grammar.py` |
| [Model Scanner](#) | Auto-discovery of `.gguf` files on disk | `src/c_e_h/model_scanner.py` |
| [Model Registry](#) | Model metadata and download registry | `src/c_e_h/model_registry.py` |
| [Profile Manager](#) | Save/load configuration profiles (YAML) | `src/c_e_h/profile_manager.py` |
| [Session Manager](#) | Session management with SQLite backend | `src/c_e_h/session_manager.py` |
| [Database Migration](#) | SQLite schema migration system | `src/c_e_h/db_migrate.py` |
| [Streaming](#) | Streaming display utilities | `src/c_e_h/streaming.py` |
| [Shutdown Handler](#) | Graceful shutdown signal handling | `src/c_e_h/shutdown.py` |
| [Logging Configuration](#) | Structured logging setup | `src/c_e_h/logging_config.py` |
| [Plugin System](#) | Plugin registration and loading | `src/c_e_h/plugin.py` |
| [Prompt Template](#) | Prompt templating utilities | `src/c_e_h/prompt_template.py` |

## UI Modules

| Module | Description | File |
|--------|-------------|------|
| [Interactive Launcher](../UI/LAUNCHER.md) | Unified `ceh run` interactive flow | `src/c_e_h/ui/launcher.py` |
| [Dashboard](../UI/README.md) | Real-time agent state monitoring TUI | `src/c_e_h/ui/dashboard.py` |
| [Clean Display](../UI/README.md) | Spinner + final response display | `src/c_e_h/ui/clean_display.py` |
| [Session UI](../UI/COMMANDS.md) | Session browser and management | `src/c_e_h/ui/session_ui.py` |
| [Enhanced Streaming](../UI/README.md) | Multi-section panel streaming display | `src/c_e_h/ui/streaming_enhanced.py` |
| [Widgets](../UI/README.md) | Reusable Rich UI components | `src/c_e_h/ui/widgets.py` |

## Quick Navigation

- **Getting Started**: Read [`cli.md`](cli.md) for command-line usage, then [`agent.md`](agent.md) for the core agent lifecycle.
- **Extending C.E.H.**: See [`tools.md`](tools.md) for creating custom tools, then [`agent.md`](agent.md) for agent configuration.
- **Memory System**: Refer to [`memory.md`](memory.md) for context management, compaction strategies, and persistence.
- **LLM Integration**: See [`llama_backend.md`](llama_backend.md) for model loading, inference, and grammar sampling.
- **Security**: See [`SECURITY.md`](../SECURITY.md) for the threat model, permission system, and sandboxing.

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────────────┐
│                        C.E.H. Core Engine                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────┬──────────────┬──────────────┬──────────────────┐  │
│  │  CLI        │  Agent       │  Memory      │  LLM Backend     │  │
│  │  (cli.py)   │  (agent.py)  │  (memory.py) │  (llama_         │  │
│  │             │              │              │   backend.py)    │  │
│  ├─────────────┼──────────────┼──────────────┼──────────────────┤  │
│  │  Tools      │  Security    │  Grammar     │  Model Scanner   │  │
│  │  (tools.py) │  (security. │  (grammar.   │  (model_         │  │
│  │             │   py)        │   py)        │   scanner.py)    │  │
│  ├─────────────┼──────────────┼──────────────┼──────────────────┤  │
│  │  Profile    │  Session     │  DB Migrate  │  Plugin System   │  │
│  │  Manager    │  Manager     │  (db_       │  (plugin.py)     │  │
│  │  (profile_  │  (session_   │   migrate.   │                  │  │
│  │   manager.  │   manager.py)│   py)        │                  │  │
│  │   py)       │              │              │                  │  │
│  └─────────────┴──────────────┴──────────────┴──────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                     UI Layer (src/c_e_h/ui/)                 │  │
│  │  ┌─────────────┬─────────────┬──────────────┬─────────────┐  │  │
│  │  │  Launcher   │  Dashboard  │  Session UI  │  Widgets    │  │  │
│  │  │  (launcher. │  (dashboard │  (session_  │  (widgets.  │  │  │
│  │  │   py)       │   .py)      │   ui.py)     │   py)       │  │  │
│  │  ├─────────────┼─────────────┼──────────────┼─────────────┤  │  │
│  │  │  Clean      │  Enhanced   │  Streaming   │             │  │  │
│  │  │  Display    │  Streaming  │  (streaming  │             │  │  │
│  │  │  (clean_    │  (streaming │  _enhanced.  │             │  │  │
│  │  │   display.  │   .py)      │   py)        │             │  │  │
│  │  │   py)       │             │              │             │  │  │
│  │  └─────────────┴─────────────┴──────────────┴─────────────┘  │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Data Flow

```
User Input (CLI/UI)
       │
       ▼
   CLI Layer (cli.py)
       │
       ├──► Interactive Launcher (ui/launcher.py)
       │
       ▼
   Agent Engine (agent.py)
       │
       ├──► Llama Backend (llama_backend.py) ──► GGUF Model
       │
       ├──► Tool Registry (tools.py)
       │       │
       │       ├──► Security Policy (security.py)
       │       │
       │       └──► Built-in Tools (read_file, write_file, etc.)
       │
       ├──► Memory System (memory.py)
       │       │
       │       ├──► SessionManager (SQLite)
       │       │
       │       ├──► ContextManager (short-term, token tracking)
       │       │
       │       ├──► PersistentMemory (agent.md + SQLite)
       │       │
       │       └──► VectorDB (FAISS / ChromaDB)
       │
       └──► Grammar Engine (grammar.py) ──► Structured Output
```

## Versioning

C.E.H. follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html). API documentation is versioned alongside the project. Breaking changes to public APIs will be documented in [`CHANGELOG.md`](../../CHANGELOG.md) with migration instructions.

## License

MIT License — see [`LICENSE`](../../LICENSE) for details.
