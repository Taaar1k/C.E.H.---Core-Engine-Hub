# C.E.H. UI Commands Reference

> **Version**: 1.0.0
> **Last Updated**: 2026-04-22

## Dashboard Command

### `ceh dashboard`

Launch the interactive real-time dashboard.

```bash
ceh dashboard [OPTIONS]
```

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--model` | `-m` | `str` | `None` | Path to GGUF model file |
| `--config` | `-C` | `str` | `None` | Path to agent.md config file |
| `--refresh` | `-r` | `float` | `2.0` | Refresh interval in seconds |
| `--log-level` | `-l` | `str` | `INFO` | Logging verbosity level |
| `--debug` | `-d` | `flag` | `False` | Enable debug mode |

#### Examples

```bash
# Basic dashboard with default config
ceh dashboard

# Dashboard with specific model
ceh dashboard --model ./models/llama-3-8b.Q4_K_M.gguf

# Dashboard with custom config
ceh dashboard --config agent.md

# Dashboard with 1-second refresh
ceh dashboard --refresh 1.0

# Dashboard with debug logging
ceh dashboard --debug
```

#### Keyboard Controls

| Key | Action |
|-----|--------|
| `q` | Quit dashboard |
| `s` | Switch session |
| `c` | Clear context |
| `?` / `h` | Toggle help overlay |
| `r` | Force refresh |

---

## Sessions Command

### `ceh sessions`

Launch the session management UI.

```bash
ceh sessions [OPTIONS]
```

#### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--filter` | `-f` | `str` | `None` | Filter sessions by name |
| `--create` | `-c` | `str` | `None` | Create new session with name |
| `--delete` | `-d` | `str` | `None` | Delete session by ID |
| `--interactive` | `-i` | `flag` | `False` | Run in interactive mode |

#### Examples

```bash
# List all sessions
ceh sessions

# Filter sessions by name
ceh sessions --filter "test"

# Create a new session
ceh sessions --create "My New Session"

# Delete a session
ceh sessions --delete sess0001

# Interactive session browser
ceh sessions --interactive
```

---

## Integration with Existing Commands

### Enhanced Streaming

The `ceh stream` command uses the existing `stream_display()` from `streaming.py`.
For enhanced streaming with metrics and speed graph, use programmatically:

```python
from c_e_h.ui import EnhancedStreamDisplay
from c_e_h.streaming import stream_display

display = EnhancedStreamDisplay(
    title="AI Response",
    model_info="llama-3-8b",
    speed_graph_width=30,
)
result = display.render(chunks, prompt_time=0.5, prompt_tokens=64)
```

### Dashboard with Agent

```python
from c_e_h.agent import Agent
from c_e_h.session_manager import SessionManager
from c_e_h.ui import Dashboard

agent = Agent()
sm = SessionManager()
dashboard = Dashboard(agent, session_manager=sm, refresh_interval=2.0)
dashboard.run()
```

---

## CLI Help

```bash
# Show all commands
ceh --help

# Show dashboard help
ceh dashboard --help

# Show sessions help
ceh sessions --help
```
