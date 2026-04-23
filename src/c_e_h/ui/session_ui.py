"""Session management UI for C.E.H. — Browse, search, and switch sessions.

Provides ``SessionBrowser`` class for listing and switching sessions
with:
- Table view showing ID, name, message count, last accessed
- Search/filter by name
- Visual indicator for active session
- Integration with ``SessionManager`` from ``session_manager.py``
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from c_e_h.session_manager import Session, SessionManager

logger = logging.getLogger(__name__)


class SessionBrowser:
    """Interactive session browser for CEH.

    Provides a table-based view of all sessions with search,
    filtering, and selection capabilities.

    Attributes:
        session_manager: The SessionManager instance.
        console: Rich Console instance.
        _active_session_id: Currently active session ID (if any).

    Example:
        >>> from c_e_h.session_manager import SessionManager
        >>> sm = SessionManager()
        >>> browser = SessionBrowser(sm)
        >>> browser.render()
    """

    def __init__(
        self,
        session_manager: "SessionManager",
        console: Optional[Console] = None,
        active_session_id: Optional[str] = None,
    ) -> None:
        """Initialize SessionBrowser.

        Args:
            session_manager: SessionManager instance.
            console: Rich Console instance.
            active_session_id: Currently active session ID.
        """
        self.session_manager = session_manager
        self.console = console or Console()
        self._active_session_id = active_session_id

    def render(self, filter_text: Optional[str] = None) -> None:
        """Render the session browser table.

        Displays all sessions (optionally filtered) in a Rich table
        with visual indicators for the active session.

        Args:
            filter_text: Optional text to filter sessions by name.
        """
        try:
            sessions = self.session_manager.list_sessions()
        except Exception as e:
            self.console.print(f"[red]Error listing sessions: {e}[/red]")
            return

        # Apply filter
        if filter_text:
            sessions = [
                s for s in sessions
                if filter_text.lower() in s.name.lower()
            ]

        if not sessions:
            msg = "No sessions found."
            if filter_text:
                msg += f" (filtered by '{filter_text}')"
            self.console.print(Panel(msg, title="Sessions", border_style="yellow"))
            return

        table = self._build_table(sessions)
        self.console.print(table)

        # Show footer info
        total = len(sessions)
        self.console.print(f"[dim]Showing {total} session(s). Press 'q' to quit.[/dim]")

    def render_as_string(self, filter_text: Optional[str] = None) -> str:
        """Render the session browser as a string.

        Args:
            filter_text: Optional text to filter sessions by name.

        Returns:
            String representation of the session table.
        """
        try:
            sessions = self.session_manager.list_sessions()
        except Exception:
            return "Error listing sessions."

        if filter_text:
            sessions = [
                s for s in sessions
                if filter_text.lower() in s.name.lower()
            ]

        if not sessions:
            return "No sessions found."

        table = self._build_table(sessions)

        # Render table to string
        from io import StringIO
        output = StringIO()
        temp_console = Console(file=output, force_terminal=True)
        temp_console.print(table)
        result = output.getvalue()
        result += f"Showing {len(sessions)} session(s).\n"
        return result

    def _build_table(self, sessions: list["Session"]) -> Table:
        """Build a Rich table from session list.

        Args:
            sessions: List of Session objects.

        Returns:
            Rich Table with session data.
        """
        table = Table(
            title="Sessions",
            title_style="bold blue",
            show_header=True,
            header_style="bold magenta",
            border_style="blue",
            expand=True,
        )

        table.add_column("ID", style="cyan", width=8, justify="center")
        table.add_column("Name", style="white", ratio=2)
        table.add_column("Messages", style="green", width=5, justify="right")
        table.add_column("Created", style="dim", width=10)
        table.add_column("Last Access", style="dim", width=10)
        table.add_column("Model", style="yellow", width=8)

        for session in sessions:
            # Active session indicator
            is_active = session.id == self._active_session_id
            id_str = f"● {session.id}" if is_active else f"  {session.id}"
            if is_active:
                id_str = f"[bold green]{session.id}[/bold green] *"

            name = session.name
            if is_active:
                name = f"[bold green]{name}[/bold green] (active)"

            created = self._format_timestamp(session.created_at)
            last_accessed = self._format_timestamp(session.last_accessed)
            model = session.model or "-"

            table.add_row(
                id_str,
                name,
                str(session.message_count),
                created,
                last_accessed,
                model,
            )

        return table

    def _format_timestamp(self, ts: str) -> str:
        """Format an ISO-8601 timestamp for display.

        Args:
            ts: ISO-8601 timestamp string.

        Returns:
            Formatted timestamp (YYYY-MM-DD HH:MM).
        """
        try:
            dt = datetime.fromisoformat(ts)
            return dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            return ts[:16] if len(ts) >= 16 else ts

    def select_session(self, session_id: str) -> Optional["Session"]:
        """Select and return a session by ID.

        Args:
            session_id: Session ID to select.

        Returns:
            Session object or None if not found.
        """
        try:
            session = self.session_manager.get_session(session_id)
            if session:
                self._active_session_id = session_id
                logger.info("Session selected: %s", session_id)
            return session
        except Exception as e:
            self.console.print(f"[red]Error selecting session: {e}[/red]")
            return None

    def create_session(self, name: str, model: Optional[str] = None) -> Optional["Session"]:
        """Create a new session and return it.

        Args:
            name: Session name.
            model: Optional model identifier.

        Returns:
            New Session object or None on error.
        """
        try:
            session = self.session_manager.create_session(name=name, model=model)
            self.console.print(f"[green]Created session: {session.id} — {session.name}[/green]")
            return session
        except Exception as e:
            self.console.print(f"[red]Error creating session: {e}[/red]")
            return None

    def delete_session(self, session_id: str) -> bool:
        """Delete a session.

        Args:
            session_id: Session ID to delete.

        Returns:
            True if deleted, False if not found.
        """
        try:
            result = self.session_manager.delete_session(session_id)
            if result:
                self.console.print(f"[yellow]Deleted session: {session_id}[/yellow]")
                if self._active_session_id == session_id:
                    self._active_session_id = None
            else:
                self.console.print(f"[dim]Session not found: {session_id}[/dim]")
            return result
        except Exception as e:
            self.console.print(f"[red]Error deleting session: {e}[/red]")
            return False

    def interactive_mode(self) -> Optional[str]:
        """Run interactive session browser with keyboard input.

        Allows user to:
        - Browse sessions in a table
        - Filter by name
        - Select a session
        - Create new session
        - Delete session
        - Quit

        Returns:
            Selected session ID, or None if no selection made.
        """
        if not self.console.is_terminal:
            self.render()
            return self._active_session_id

        import select
        import sys

        self._running = True
        filter_text = ""
        selected_id: Optional[str] = None

        while self._running:
            # Clear and re-render
            self.console.clear()
            self.render(filter_text if filter_text else None)

            # Non-blocking input
            ready, _, _ = select.select([sys.stdin], [], [], 0.5)
            if ready:
                key = sys.stdin.read(1)
                selected_id = self._handle_key(key, filter_text)
                if selected_id is None and key in ("q", "Q"):
                    break

        return selected_id

    def _handle_key(self, key: str, current_filter: str) -> Optional[str]:
        """Handle keyboard input in interactive mode.

        Args:
            key: Key pressed.
            current_filter: Current filter text.

        Returns:
            Selected session ID, or None to continue.
        """
        if key in ("q", "Q"):
            self._running = False
            return None
        elif key in ("c", "C"):
            # Create new session
            name = f"Session-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
            session = self.create_session(name)
            return session.id if session else None
        elif key in ("d", "D"):
            # Delete last shown session (simplified)
            self.console.print("[dim]Delete: specify session ID after listing[/dim]")
            return None
        elif key == "\r" or key == "\n":
            # Enter: select active session
            return self._active_session_id
        elif len(key) == 1 and key.isprintable():
            # Append to filter
            new_filter = current_filter + key
            if len(new_filter) < 50:
                return None  # Will re-render with new filter
        return None
