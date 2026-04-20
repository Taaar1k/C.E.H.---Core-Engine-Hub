# PROJECT_STATE

## Metadata
- project_name: C.E.H. (Core Engine Hub)
- date: 2026-04-20
- phase: planning

## Current Context
C.E.H. is a minimalist, secure, and cross-platform local agent framework based on llama.cpp, inspired by Claude Code's architecture. The project aims to implement ideas derived from Claude code analysis, adapted for full local usage. Key principles include exclusive locality, GGUF models via llama.cpp, maximum user simplicity, and power for solving tasks from basic coding to complex business processes.

## Active Decisions
1. **Sequential scaling architecture**: Start with single-agent mode, then add multi-agent orchestration layer
2. **Memory system**: 3-tier architecture (persistent config, short-term context, long-term vector DB)
3. **State management**: Replace JSON with sqlite3 for atomic transactions and integrity
4. **Permission system**: Graceful degradation — agent starts autonomous, switches to approval mode after 3 errors
5. **Dependency strategy**: Minimal dependencies (<30 direct packages), no AI "all-in-one" frameworks
6. **Model routing**: Adaptive model selection based on task complexity (small fast model → large powerful model)
7. **Sandboxing**: Bubblewrap/Docker container for tool execution isolation

## Constraints
- Must work entirely locally (no cloud services)
- GGUF models via llama.cpp only
- Cross-platform (Linux, macOS, Windows)
- Python 3.11+ LTS
- Max 30 direct dependencies
- No LangChain, LlamaIndex, CrewAI, or similar frameworks

## Current Phase Summary
Phase: Planning. Research report received and analyzed. Task decomposition in progress. Next steps: create structured tasks for project initialization, core architecture, memory system, tool integration, llama.cpp layer, and dependency management.
