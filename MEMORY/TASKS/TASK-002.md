# TASK-002: Core Agent Architecture (Single-Agent Mode)

## Metadata
- **Task ID**: TASK-002
- **Title**: Core Agent Architecture (Single-Agent Mode)
- **Assigned To**: Code
- **Mode**: strict
- **Created**: 2026-04-20
- **Dependencies**: TASK-001 (Project Initialization)

## Description
Implement the core agent class for single-agent mode. This includes the main `Agent` class with task understanding, step execution, and decision-making capabilities. The agent should be able to process user input, generate responses, and execute tools in a loop.

## Acceptance Criteria
1. `Agent` class implemented in `src/c_e_h/agent.py`
2. Agent reads and parses `agent.md` configuration on initialization
3. Main execution loop: receive input → generate response → execute tools if needed → repeat
4. Context window management with token counting
5. Graceful handling of LLM errors (retry, fallback)
6. CLI interface via `typer` for agent interaction
7. Structured logging with `structlog`
8. Agent state serialization/deserialization

## DoD (Definition of Done)
- [ ] `Agent` class exists in `src/c_e_h/agent.py` with proper type hints
- [ ] Agent initialization reads `agent.md` and loads configuration
- [ ] Main execution loop implemented with clear state transitions
- [ ] Token counting mechanism implemented (using llama.cpp metadata or heuristic)
- [ ] Error handling with retry logic (max 3 retries, exponential backoff)
- [ ] CLI command `c-e-h run --model <path>` works and starts agent loop
- [ ] All logging uses `structlog` with JSON format in production
- [ ] Agent state can be serialized to dict and restored
- [ ] Unit tests cover: initialization, loop iteration, error handling, state serialization
- [ ] Reviewer approval (PASS or PASS_WITH_NOTES on REVIEW_REPORT)

## Implementation Notes
- Agent class should have clear separation of concerns:
  - `__init__`: load config, initialize LLM backend, set up memory
  - `run()`: main loop, process user input
  - `generate_response()`: call LLM, parse output
  - `execute_tool()`: dispatch tool calls
  - `save_state()` / `load_state()`: persistence
- Use `pydantic` for configuration validation
- Context window should be configurable via `agent.md` (default 8192 tokens)
- Do NOT implement multi-agent logic yet — focus on single-agent robustness
