# C.E.H. UI — Interactive Terminal Interface

> **Version**: 1.0.0
> **Last Updated**: 2026-04-22
> **Dependencies**: Rich >= 13.7 (already in project)

## Overview

The C.E.H. UI package provides interactive terminal-based user interfaces for the Core Engine Hub agent framework. It includes:

- **Interactive Dashboard** — Real-time multi-panel view of agent status, sessions, messages, and metrics
- **Session Management UI** — Browse, search, filter, and switch sessions
- **Enhanced Streaming Display** — Multi-section panel with live metrics and token speed graph
- **Reusable Widgets** — Status badges, metric rows, message bubbles, progress bars

## Quick Start

### Dashboard

```bash
ceh dashboard --model ./models/llama-3-8b.Q4_K_M.gguf
```

### Session Browser

```bash
ceh sessions
ceh sessions --filter "test"
ceh sessions --create "New Session"
ceh sessions --interactive
```

### Enhanced Streaming (Programmatic)

```python
from c_e_h.ui import EnhancedStreamDisplay

display = EnhancedStreamDisplay(
    title="AI Response",
    model_info="llama-3-8b",
    speed_graph_width=30,
)
result = display.render(chunks)
print(f"Generated {result.token_count} tokens at {result.tokens_per_second:.1f} tok/s")
```

## Module Reference

| Module | Description | Key Classes |
|--------|-------------|-------------|
| [`widgets.py`](../src/c_e_h/ui/widgets.py) | Reusable Rich components | `StatusBadge`, `MetricRow`, `MessageBubble`, `ProgressBar` |
| [`streaming_enhanced.py`](../src/c_e_h/ui/streaming_enhanced.py) | Enhanced streaming display | `EnhancedStreamDisplay` |
| [`dashboard.py`](../src/c_e_h/ui/dashboard.py) | Interactive dashboard | `Dashboard` |
| [`session_ui.py`](../src/c_e_h/ui/session_ui.py) | Session management UI | `SessionBrowser` |

## Features

### Terminal Compatibility

- **TTY mode**: Full interactive UI with colors and live updates
- **non-TTY mode**: Graceful fallback to text output
- **256-color terminals**: Full color support
- **Monochrome terminals**: Fallback to text-only styling

### Keyboard Controls (Dashboard)

| Key | Action |
|-----|--------|
| `q` | Quit dashboard |
| `s` | Switch session |
| `c` | Clear context |
| `?` / `h` | Toggle help overlay |
| `r` | Force refresh |

### Widget Examples

#### StatusBadge

```python
from c_e_h.ui import StatusBadge

badge = StatusBadge("running")
console.print(badge.render())  # ● RUNNING
```

#### MetricRow

```python
from c_e_h.ui import MetricRow

metrics = [
    MetricRow("Tokens", 128),
    MetricRow("Speed", 42.5, "tok/s"),
]
console.print(MetricRow.render_multiple(metrics))
```

#### MessageBubble

```python
from c_e_h.ui import MessageBubble

bubble = MessageBubble("user", "Hello, agent!")
console.print(bubble.render())
```

#### ProgressBar

```python
from c_e_h.ui import ProgressBar

with ProgressBar("Processing", total=100) as progress:
    for i in range(100):
        progress.update(i + 1, speed=10.0)
```

## Architecture

```
src/c_e_h/ui/
├── __init__.py          # Public API exports
├── widgets.py           # Reusable Rich components
├── streaming_enhanced.py # Enhanced streaming display
├── dashboard.py         # Interactive dashboard
└── session_ui.py        # Session management UI
```

## Testing

```bash
pytest tests/test_ui_*.py -v
```

## Design Principles

1. **No new dependencies** — Only uses Rich (already in project)
2. **Graceful degradation** — Works on TTY, non-TTY, and monochrome terminals
3. **Lazy imports** — UI modules don't block basic CLI commands
4. **Type hints** — Full type annotation coverage
5. **Docstrings** — Sphinx-style documentation in all modules
