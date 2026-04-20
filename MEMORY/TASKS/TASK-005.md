# TASK-005: llama.cpp Integration Layer

## Metadata
- **Task ID**: TASK-005
- **Title**: llama.cpp Integration Layer
- **Assigned To**: Code
- **Mode**: strict
- **Created**: 2026-04-20
- **Dependencies**: TASK-001 (Project Initialization)

## Description
Implement the integration layer with `llama-cpp-python` for GGUF model inference, including grammar-based structured output, model loading configuration, and adaptive model routing.

## Acceptance Criteria
1. **LLM Backend**: Wrapper around `llama_cpp.Llama` for model inference
2. **GGUF Loading**: Support for all GGUF quantizations (Q4_K_M, Q5_K_M, etc.)
3. **Grammar-based Structured Output**: GBNF grammar enforcement for tool call format
4. **Model Configuration**: GPU offload layers, context size, batch size via config
5. **Adaptive Model Routing**: Interface for switching between small (3B-7B) and large (14B-70B) models
6. **Token Usage Tracking**: Track prompt tokens, completion tokens, and time
7. **Error Handling**: Handle OOM, context overflow, and model loading failures

## DoD (Definition of Done)
- [ ] `LlamaBackend` class in `src/c_e_h/llama_backend.py` wrapping `llama_cpp.Llama`
- [ ] GGUF model loading with configurable parameters (n_gpu_layers, n_ctx, batch_size)
- [ ] GBNF grammar implementation for tool call format (JSON output with schema)
- [ ] Grammar validation: test that output matches expected schema (>90% validity)
- [ ] Pydantic validation layer on top of grammar output
- [ ] Adaptive routing interface: `select_model(task_complexity)` returns appropriate model path
- [ ] Token usage tracking: prompt_tokens, completion_tokens, total_time logged via structlog
- [ ] Error handling: OOM → fallback to CPU, context overflow → trigger compaction
- [ ] Unit tests cover: model loading, grammar enforcement, token tracking, error handling
- [ ] Reviewer approval (PASS or PASS_WITH_NOTES on REVIEW_REPORT)

## Implementation Notes
- Grammar example (GBNF for tool calls):
  ```
  root   ::= object
  object ::= "{" ws pair ws ("," ws pair ws)* "}"
  pair   ::= "\"name\"":ws string "\"value\"":ws array
  string ::= "\"" ([^""]*) "\""
  array  ::= "[" ws (string ws)* "]"
  ws     ::= ([ \t\n] ws)?
  ```
- Use `llama_cpp.Llama.create_completion()` with `grammar` parameter
- Always validate output with Pydantic after grammar enforcement
- Model config in `agent.md`:
  ```yaml
  model:
    path: "./models/llama-3-8b.Q4_K_M.gguf"
    n_gpu_layers: -1
    n_ctx: 8192
    temperature: 0.7
  ```
- Adaptive routing: simple heuristic based on task length and complexity keywords
- Do NOT implement multi-model parallelism — sequential fallback only
