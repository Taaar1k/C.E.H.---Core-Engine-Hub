# TASK-004: Tool Integration & Permission System

## Metadata
- **Task ID**: TASK-004
- **Title**: Tool Integration & Permission System
- **Assigned To**: Code
- **Mode**: strict
- **Created**: 2026-04-20
- **Dependencies**: TASK-002 (Core Agent Architecture)

## Description
Implement the tool integration framework with permission system, including graceful degradation (autonomous → approval mode after 3 errors), tool schema validation, and sandboxed execution.

## Acceptance Criteria
1. **Tool Registry**: Central registry for tool discovery and dispatch
2. **Permission System**:
   - Agent starts in `autonomous` mode
   - Error counter tracks consecutive failures (threshold: 3)
   - After threshold: switch to `approval` mode (request user confirmation per step)
   - Error counter resets after N successful steps (N=5)
3. **Tool Schema Validation**: Pydantic-based validation for all tool arguments
4. **Sandboxed Execution**: Subprocess execution with `shell=False`, restricted environment
5. **Built-in Tools**: File read/write, shell command execution, web search (local)
6. **MCP Adapter**: Basic Model Context Protocol interface for tool interoperability

## DoD (Definition of Done)
- [ ] `ToolRegistry` class with `register()`, `get()`, `list()` methods
- [ ] Permission manager with `autonomous` and `approval` modes
- [ ] Error counter implemented with configurable threshold (`max_auto_errors` in config)
- [ ] Mode switching logic: autonomous → approval after 3 errors, approval → autonomous after 5 successes
- [ ] All tool arguments validated via Pydantic before execution
- [ ] Subprocess execution uses `shell=False`, environment variables sanitized
- [ ] Built-in tools: `read_file`, `write_file`, `execute_command`, `web_search`
- [ ] MCP adapter interface defined (minimal viable implementation)
- [ ] Unit tests cover: permission mode switching, tool validation, sandboxed execution
- [ ] Reviewer approval (PASS or PASS_WITH_NOTES on REVIEW_REPORT)

## Implementation Notes
- Tool schema example:
  ```python
  class ReadFileSchema(BaseModel):
      path: str = Field(..., description="Path to file to read")
      max_lines: int = Field(default=100, description="Maximum lines to read")
  ```
- Permission states: `PERMISSION_AUTONOMOUS = "autonomous"`, `PERMISSION_APPROVAL = "approval"`
- Error counter stored in agent state (sqlite3 `sessions` table)
- Sandbox: use `subprocess.run()` with `shell=False`, `env=restricted_env`, `timeout=30`
- Tool output captured and stored in context with role="tool"
- Do NOT implement network access by default — web search should use local cache or return "not configured"
