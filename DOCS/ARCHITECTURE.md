# Architecture

> System architecture, design decisions, and component interactions for C.E.H.

## Table of Contents

- [Design Philosophy](#design-philosophy)
- [High-Level Architecture](#high-level-architecture)
- [Component Details](#component-details)
- [Data Flow](#data-flow)
- [Memory Architecture](#memory-architecture)
- [Security Architecture](#security-architecture)
- [Scaling Strategy](#scaling-strategy)
- [Design Decisions](#design-decisions)
- [Future Architecture](#future-architecture)

## Design Philosophy

C.E.H. is built on five core principles:

| Principle | Description | Trade-off |
|-----------|-------------|-----------|
| **Exclusive Locality** | No cloud services, no external APIs by default | Larger local footprint |
| **Minimal Dependencies** | <30 direct packages, no AI frameworks | More code to maintain |
| **Sequential Scaling** | Single-agent first, multi-agent on demand | Simpler initial architecture |
| **Secure by Default** | Sandboxed execution, permission degradation | Slightly slower execution |
| **Maximum Simplicity** | One command to start, intuitive config | Less flexibility for power users |

## High-Level Architecture

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
                              │           │
                              ▼           ▼
                    ┌────────────────┐  ┌──────────────┐
                    │  SQLite DB     │  │ Vector Store │
                    │  (.ceh_state)  │  │  (FAISS)     │
                    └────────────────┘  └──────────────┘
```

## Component Details

### CLI Layer (`src/c_e_h/cli.py`)

The CLI is the entry point for all user interactions. Built with [Typer](https://typer.tiangolo.com/), it provides:

- **Command routing**: Dispatches to appropriate handlers
- **Argument validation**: Typer-based type checking
- **Configuration loading**: Reads `.agent-config.md` or `agent.md`
- **Error handling**: User-friendly error messages with exit codes

```
User Input
    │
    ▼
┌─────────────┐
│   CLI       │  ← Typer command parser
│  (Typer)    │  ← Config loader
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Agent.run()│  ← Single-shot
│  or         │
│  Agent.run_loop()  ← Multi-step
└─────────────┘
```

### Agent Engine (`src/c_e_h/agent.py`)

The Agent is the central orchestrator. It manages:

1. **Task Loop**: The main inference-execution cycle
2. **Context Management**: Conversation history and compaction
3. **State Management**: Permissions, error tracking, session persistence
4. **Decision Making**: Tool call parsing vs. final response detection

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent Task Loop                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────┐     ┌──────────┐     ┌──────────────────┐    │
│  │  Prompt  │────►│  LLM     │────►│  Parse Output    │    │
│  │  Input   │     │  Generate│     │  (tool vs text)  │    │
│  └──────────┘     └──────────┘     └────────┬─────────┘    │
│                                              │              │
│                              ┌───────────────┼───────┐      │
│                              │               │       │      │
│                              ▼               ▼       ▼      │
│                        ┌──────────┐  ┌────────┐  ┌──────┐   │
│                        │  Tool    │  │ Final  │  │ Error│   │
│                        │  Call    │  │ Response│  │      │   │
│                        └────┬─────┘  └────────┘  └──────┘   │
│                             │                                │
│                             ▼                                │
│                      ┌─────────────┐                         │
│                      │  Execute    │                         │
│                      │  Tool       │                         │
│                      └──────┬──────┘                         │
│                             │                                │
│                             ▼                                │
│                      ┌─────────────┐                         │
│                      │  Add to     │                         │
│                      │  Context    │                         │
│                      └─────────────┘                         │
│                             │                                │
│                             ▼                                │
│                    ┌────────────────┐                         │
│                    │  Check Limits  │                         │
│                    │  (max_iter,    │                         │
│                    │   context full)│                         │
│                    └────────┬───────┘                         │
│                             │                                │
│                     ┌───────┴───────┐                         │
│                     │               │                         │
│                Continue        Return                           │
│                     │               │                         │
└─────────────────────┴───────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

### Memory System (`src/c_e_h/memory.py`)

Three-tier memory architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                    Memory System                            │
├─────────────┬──────────────────┬────────────────────────────┤
│  Persistent │   Short-term     │    Long-term               │
│  (agent.md) │   (Context +     │    (FAISS Vector DB)       │
│             │    SQLite)       │                            │
├─────────────┼──────────────────┼────────────────────────────┤
│ • Identity  │ • Conversation   │ • Semantic memories        │
│ • Config    │ • Tool history   │ • Cross-session knowledge  │
│ • Instructions│ • System state │ • Embedding-indexed        │
│             │                  │                            │
│ Format:     │ Format:          │ Format:                    │
│ Markdown    │ JSON + SQLite    │ Vector + Metadata          │
│ YAML front  │                  │                            │
│ matter      │                  │                            │
│             │                  │                            │
│ Lifetime:   │ Lifetime:        │ Lifetime:                  │
│ Permanent   │ Session          │ Permanent                  │
└─────────────┴──────────────────┴────────────────────────────┘
```

### Tool Framework (`src/c_e_h/tools.py`)

Tool registry with security controls:

```
┌─────────────────────────────────────────────────────────────┐
│                    Tool Framework                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌───────────────┐   │
│  │  Registry   │───►│  Validator  │───►│  Permission   │   │
│  │  (register, │    │  (Pydantic  │    │  Manager      │   │
│  │   list,     │    │   schema)   │    │  (mode check) │   │
│  │   get)      │    └─────────────┘    └───────┬───────┘   │
│  └─────────────┘                               │           │
│        │                                       ▼           │
│        │                            ┌──────────────────┐   │
│        │                            │  Sandbox         │   │
│        │                            │  (shell=False,   │   │
│        │                            │   timeout, path  │   │
│        │                            │   validation)    │   │
│        │                            └────────┬─────────┘   │
│        │                                     │             │
│        ▼                                     ▼             │
│  ┌─────────────┐                    ┌───────────────┐      │
│  │  Tool       │                    │  ToolResult   │      │
│  │  Functions  │                    │  (success,    │      │
│  │  (read,     │                    │   error,      │      │
│  │   write,    │                    │   data)       │      │
│  │   exec)     │                    └───────────────┘      │
│  └─────────────┘                                           │
└─────────────────────────────────────────────────────────────┘
```

### LLM Backend (`src/c_e_h/llama_backend.py`)

llama.cpp integration layer:

```
┌─────────────────────────────────────────────────────────────┐
│                   LLM Backend                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              llama-cpp-python                         │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐  │  │
│  │  │  GGUF Loader │  │  Inference  │  │  Grammar     │  │  │
│  │  │  • Quantized │  │  Engine     │  │  Sampler     │  │  │
│  │  │    Models    │  │  • KV Cache │  │  • GBNF      │  │  │
│  │  │  • Metadata  │  │  • Streaming│  │  • Constrained│  │  │
│  │  └─────────────┘  └─────────────┘  └──────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  Backend Detection:                                         │
│  • Apple Silicon → Metal                                    │
│  • NVIDIA GPU → CUDA                                        │
│  • AMD GPU → Vulkan                                         │
│  • Fallback → CPU                                           │
└─────────────────────────────────────────────────────────────┘
```

## Data Flow

### Single-Shot Mode

```
User Prompt
    │
    ▼
┌─────────────┐
│    CLI      │  Parse arguments, load config
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Agent     │  Initialize components
│    .run()   │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  LLM        │  Generate response
│  Backend    │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Response   │  Return to user
│  Output     │
└─────────────┘
```

### Multi-Step Mode

```
User Prompt ──────────────────────────────────────────────────┐
    │                                                         │
    ▼                                                         │
┌─────────────┐     ┌─────────────┐     ┌───────────────┐    │
│   Agent     │────►│  LLM        │────►│  Parse Output │    │
│    .run_    │     │  Backend    │     │  (tool vs text)│   │
│    loop()   │     └─────────────┘     └───────┬───────┘    │
└─────────────┘                               │              │
                              ┌───────────────┼───────┐      │
                              │               │       │      │
                              ▼               ▼       ▼      │
                        ┌──────────┐  ┌──────────┐  ┌──────┐  │
                        │  Tool    │  │ Final    │  │ Error│  │
                        │  Call    │  │ Response │  │      │  │
                        └────┬─────┘  └──────────┘  └──────┘  │
                             │                                 │
                             ▼                                 │
                      ┌─────────────┐                          │
                      │  Execute    │                          │
                      │  Tool       │                          │
                      └──────┬──────┘                          │
                             │                                 │
                             ▼                                 │
                      ┌─────────────┐                          │
                      │  Memory     │                          │
                      │  .add_      │                          │
                      │  message()  │                          │
                      └──────┬──────┘                          │
                             │                                 │
                             ▼                                 │
                      ┌─────────────┐     ┌───────────────┐    │
                      │  Check      │────►│  Continue     │    │
                      │  Limits     │     │  Loop?        │    │
                      └─────────────┘     └───────────────┘    │
                                                             │
└────────────────────────────────────────────────────────────┘
```

## Memory Architecture

### Three-Tier Design

```
┌─────────────────────────────────────────────────────────────┐
│                    Memory Tiers                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Tier 1: Persistent (agent.md)                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  - Identity & configuration                           │  │
│  │  - Long-term instructions                             │  │
│  │  - Tool permissions                                   │  │
│  │  - Model settings                                     │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  Tier 2: Short-term (Context Window + SQLite)               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  - Current session conversation                       │  │
│  │  - Tool call history                                  │  │
│  │  - Agent state (permissions, errors)                  │  │
│  │  - Context compaction (snip / microcompact)           │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  Tier 3: Long-term (FAISS Vector Store)                     │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  - Semantic embeddings of past sessions               │  │
│  │  - Cross-session knowledge retrieval                  │  │
│  │  - Automatic memory summarization                     │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  Data Flow:                                                 │
│  Tier 3 ──search──► Tier 2 (inject into context)            │
│  Tier 2 ──end of session──► Tier 3 (embed & store)         │
│  Tier 1 always available (loaded at startup)                │
└─────────────────────────────────────────────────────────────┘
```

### Context Compaction

```
Context Window (8192 tokens)
    │
    ├─ Messages: 150/8192 tokens ──► No action needed
    │
    └─ Messages: 8100/8192 tokens ──► Trigger compaction
         │
         ├─ Strategy: "snip"
         │   └─► Remove oldest 2000 tokens
         │
         └─ Strategy: "microcompact"
             └─► Send oldest 2000 tokens to LLM
                 └─► Replace with summary message
```

## Security Architecture

### Defense in Depth

```
┌─────────────────────────────────────────────────────────────┐
│                 Security Layers                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Layer 4: Output Sanitization                               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  - Tool output stored with role="tool"                │  │
│  │  - No prompt confusion between tool output and user   │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  Layer 3: Sandboxed Execution                               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  - shell=False, timeout=30s, path validation          │  │
│  │  - Environment whitelisting                           │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  Layer 2: Schema Validation                                 │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  - Pydantic models for all tool arguments             │  │
│  │  - Dangerous pattern detection                        │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  Layer 1: Permission System                                 │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  - Graceful degradation (autonomous → approval)       │  │
│  │  - Error tracking with persistence                    │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Scaling Strategy

### Sequential Scaling

```
Phase 1: Single Agent (Current)
┌─────────────────────────────────────────────────────────────┐
│  Agent                                                      │
│  ├── Understands intent                                      │
│  ├── Manages context                                         │
│  ├── Executes tools                                          │
│  └── Learns from experience                                  │
└─────────────────────────────────────────────────────────────┘

Phase 2: Multi-Agent Swarm (Planned)
┌─────────────────────────────────────────────────────────────┐
│  Orchestrator                                               │
│  ├── Planner (decomposes goals)                              │
│  ├── Executor: Code (specialized in coding)                  │
│  ├── Executor: Research (specialized in search)              │
│  ├── Executor: System (specialized in system tasks)          │
│  └── Reviewer (validates output)                             │
└─────────────────────────────────────────────────────────────┘
```

## Design Decisions

### Why llama.cpp?

| Factor | Decision | Rationale |
|--------|----------|-----------|
| Inference engine | llama.cpp | Best open-source GGUF support, C-based, minimal dependencies |
| Python binding | llama-cpp-python | Mature, well-maintained, GPU backend support |
| Model format | GGUF | Native llama.cpp format, quantization support |

### Why SQLite over JSON?

| Factor | Decision | Rationale |
|--------|----------|-----------|
| State storage | SQLite | Atomic transactions, integrity, concurrent access |
| Config storage | Markdown YAML | Human-readable, editable, version-control friendly |

### Why No AI Frameworks?

| Factor | Decision | Rationale |
|--------|----------|-----------|
| Framework choice | None | Avoid vendor lock-in, reduce dependencies, maintain control |
| Alternatives | Custom implementation | Full control over behavior, no hidden complexity |

## Future Architecture

### Planned Components

| Component | Status | Description |
|-----------|--------|-------------|
| MCP Adapter | Planned | Model Context Protocol integration for external tools |
| Plugin System | Planned | Third-party tool and backend plugins |
| Swarm Orchestrator | Planned | Multi-agent coordination layer |
| Advanced Sandboxing | Planned | Docker/bubblewrap container integration |
| Web UI | Planned | Browser-based interface for remote access |

### Extension Points

```
src/c_e_h/
├── plugins/              # Plugin system (planned)
│   ├── loader.py         # Plugin discovery and loading
│   └── api.py            # Plugin interface
├── adapters/             # Adapter pattern (planned)
│   ├── mcp.py            # MCP protocol adapter
│   └── openai.py         # OpenAI API fallback
└── backends/             # Multiple backend support (planned)
    ├── llama.py          # Current llama.cpp backend
    └── custom.py         # Custom backend interface
```
