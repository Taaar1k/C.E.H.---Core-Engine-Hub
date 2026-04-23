"""UI package for C.E.H. — Interactive terminal user interface components.

Provides:
- Reusable Rich widgets (StatusBadge, MetricRow, MessageBubble, ProgressBar)
- Enhanced streaming display with multi-section panels and token speed graph
- Interactive dashboard with real-time agent state monitoring
- Session management browser with search and filtering

All components support TTY and non-TTY environments with graceful degradation.
"""

from __future__ import annotations

from c_e_h.ui.dashboard import Dashboard
from c_e_h.ui.session_ui import SessionBrowser
from c_e_h.ui.streaming_enhanced import EnhancedStreamDisplay
from c_e_h.ui.widgets import MessageBubble, MetricRow, ProgressBar, StatusBadge

__all__ = [
    "Dashboard",
    "EnhancedStreamDisplay",
    "MessageBubble",
    "MetricRow",
    "ProgressBar",
    "SessionBrowser",
    "StatusBadge",
]
