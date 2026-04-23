# Security Policy — C.E.H. (Core Engine Hub)

## Threat Model

C.E.H. is a **local agent framework** that executes tools on the user's machine. The primary threat model assumes:

1. **Untrusted LLM output**: The model may generate malicious tool arguments
2. **Prompt injection**: User input or tool output may contain injection attempts
3. **Filesystem access**: Tools may attempt to read/write/delete files outside intended scope
4. **Command execution**: Shell commands may attempt system compromise

## Security Layers

### Layer 1: Permission System

C.E.H. uses a **graceful degradation** permission model:

| Mode | Behavior | Trigger |
|------|----------|---------|
| `autonomous` | Agent executes tools without confirmation | Default on startup |
| `approval` | Agent requests user confirmation per step | After `max_auto_errors` consecutive failures |

**Configuration** (in `agent.md`):

```yaml
permissions:
  mode: autonomous          # autonomous | approval
  max_auto_errors: 3        # Switch to approval after N errors
  success_reset: 5          # Reset to autonomous after N successes
```

**Error tracking**:
- Error counter stored in `.ceh_state.db` (sqlite3)
- Resets after `success_reset` consecutive successful tool executions
- Persists across agent restarts

### Layer 2: Tool Schema Validation

All tool arguments are validated using **Pydantic models** before execution:

```python
class ExecuteCommandSchema(BaseModel):
    command: str = Field(..., description="Command to execute")
    args: list[str] = Field(default=[], description="Command arguments")

    @validator("command")
    def validate_command(cls, v):
        # Block dangerous commands
        dangerous = ["rm -rf", "mkfs", "dd if=", "> /dev/"]
        if any(d in v.lower() for d in dangerous):
            raise ValueError(f"Blocked dangerous command pattern: {v}")
        return v
```

### Layer 3: Sandboxed Execution

**Subprocess execution rules**:

| Rule | Implementation |
|------|----------------|
| `shell=False` | No shell interpretation, no command chaining |
| Environment sanitization | Only whitelisted env vars passed |
| Timeout | 30-second hard limit per command |
| Working directory | Restricted to project `cwd` |
| File descriptor limits | `ulimit` applied where possible |

**Example execution**:

```python
import subprocess
import os

def execute_tool(command: str, args: list[str], cwd: str) -> dict:
    # Block dangerous patterns
    dangerous_patterns = ["rm -rf", "mkfs", "dd if=", "> /dev/", "curl |", "wget -O - |"]
    full_cmd = f"{command} {' '.join(args)}"
    if any(p in full_cmd for p in dangerous_patterns):
        raise SecurityError(f"Blocked dangerous command: {full_cmd}")

    # Sanitize environment
    safe_env = {
        k: v for k, v in os.environ.items()
        if k in ("PATH", "HOME", "LANG", "TERM", "GITHUB_TOKEN")
    }

    # Execute with timeout
    result = subprocess.run(
        [command] + args,
        cwd=cwd,
        env=safe_env,
        capture_output=True,
        text=True,
        timeout=30
    )
    return {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}
```

### Layer 4: Injection Protection

**Input sanitization**:

1. **Argument escaping**: All tool arguments passed as separate list elements (no shell interpolation)
2. **Path traversal blocking**: File operations restricted to project `cwd`
3. **Prompt injection detection**: System prompt includes instructions to ignore injected commands
4. **Output sanitization**: Tool output stored with role="tool" to prevent prompt confusion

**Path validation**:

```python
from pathlib import Path

def validate_path(requested: str, base: Path) -> Path:
    resolved = (base / requested).resolve()
    if not str(resolved).startswith(str(base.resolve())):
        raise SecurityError(f"Path traversal blocked: {requested}")
    return resolved
```

## Default Tool Permissions

| Tool | Allowed | Restrictions |
|------|---------|-------------|
| `read_file` | ✅ | Within `cwd` only, max 1000 lines |
| `write_file` | ⚠️ | Confirmation required if `mode=approval` |
| `execute_command` | ⚠️ | `shell=False`, 30s timeout, dangerous patterns blocked |
| `web_search` | ❌ | Disabled by default, enable in `agent.md` |
| `import_module` | ⚠️ | Standard library + `pydantic`, `rich` only |

## Reporting Security Issues

If you discover a security vulnerability, please:

1. **Do NOT open a public issue**
2. Email security findings to: `security@ceh-framework.dev` (placeholder)
3. Allow 72 hours for response before public disclosure

We will acknowledge receipt within 24 hours and provide a timeline for remediation.

## Responsible Disclosure

| Severity | Example | Response Time |
|----------|---------|---------------|
| **Critical** | Arbitrary code execution, data exfiltration | 24 hours |
| **High** | Path traversal, permission bypass | 72 hours |
| **Medium** | Injection in tool output | 1 week |
| **Low** | Information disclosure | 2 weeks |

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2026-04-20 | 0.1.0 | Initial security policy |
