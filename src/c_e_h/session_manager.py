"""Session management with SQLite backend.

Provides ``Session`` dataclass and ``SessionManager`` class for
creating, listing, switching, and deleting sessions with message
storage and proper indexing.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from c_e_h.logging_config import get_debug_mode

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class SessionError(Exception):
    """Base exception for session-related errors."""


class SessionNotFoundError(SessionError):
    """Raised when a requested session does not exist."""


class CleanupError(SessionError):
    """Raised when cleanup operations fail."""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CleanupReport:
    """Summary of a cleanup operation.

    Attributes:
        sessions_scanned: Total number of sessions examined.
        sessions_deleted: Number of sessions removed.
        sessions_archived: Number of sessions moved to archive.
        messages_archived: Total messages archived.
        space_freed_bytes: Approximate bytes freed from the database.
        archive_dir: Path to the archive directory.
    """

    sessions_scanned: int = 0
    sessions_deleted: int = 0
    sessions_archived: int = 0
    messages_archived: int = 0
    space_freed_bytes: int = 0
    archive_dir: str = ""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Session:
    """Represents a single agent session.

    Attributes:
        id: Short UUID4 prefix (8 chars).
        name: Human-readable session name.
        created_at: ISO-8601 timestamp of creation.
        last_accessed: ISO-8601 timestamp of last access.
        message_count: Number of messages in this session.
        model: Model identifier (nullable).
        system_prompt: System prompt text (nullable).
        metadata: Arbitrary JSON-serialisable dict (nullable).
    """

    id: str
    name: str
    created_at: str
    last_accessed: str
    message_count: int = 0
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    metadata: Optional[dict[str, Any]] = field(default_factory=dict)


@dataclass
class Message:
    """Represents a single message within a session.

    Attributes:
        id: Auto-incrementing integer primary key.
        session_id: Parent session ID.
        role: One of ``user``, ``assistant``, ``system``, ``tool``.
        content: Message text content.
        token_count: Estimated token count (nullable).
        created_at: ISO-8601 timestamp.
        metadata: Arbitrary JSON-serialisable dict (nullable).
    """

    id: int
    session_id: str
    role: str
    content: str
    token_count: Optional[int] = None
    created_at: str = ""
    metadata: Optional[dict[str, Any]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# SessionManager
# ---------------------------------------------------------------------------


class SessionManager:
    """Manages sessions and their messages using a SQLite backend.

    Args:
        db_path: Path to the SQLite database file. Defaults to
            ``~/.ceh/sessions.db``.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = Path(db_path) if db_path else self._default_db_path()
        self._ensure_db_dir()
        # Initialise base schema first (idempotent), then run migrations on top
        self._init_schema()
        from c_e_h.db_migrate import migrate_database

        migrate_database(self.db_path)
        logger.info("SessionManager initialised db_path=%s", str(self.db_path))

    # -- public API --------------------------------------------------------

    def create_session(
        self,
        name: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Session:
        """Create a new session.

        Args:
            name: Human-readable session name.
            system_prompt: Optional system prompt.
            model: Optional model identifier.

        Returns:
            The newly created :class:`Session`.

        Raises:
            SessionError: On database errors.
        """
        session_id = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn = self._connect()
            conn.execute(
                """
                INSERT INTO sessions
                    (id, name, created_at, last_accessed, message_count,
                     model, system_prompt, metadata)
                VALUES (?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    session_id,
                    name,
                    now,
                    now,
                    model,
                    system_prompt,
                    None,  # metadata
                ),
            )
            conn.commit()
            conn.close()
        except sqlite3.Error as exc:
            raise SessionError(f"Failed to create session: {exc}") from exc

        logger.info("Session created session_id=%s name=%s", session_id, name)
        return Session(
            id=session_id,
            name=name,
            created_at=now,
            last_accessed=now,
            message_count=0,
            model=model,
            system_prompt=system_prompt,
        )

    def list_sessions(self) -> list[Session]:
        """List all sessions ordered by ``last_accessed`` DESC.

        Returns:
            List of :class:`Session` objects.
        """
        try:
            conn = self._connect()
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY last_accessed DESC"
            ).fetchall()
            conn.close()
        except sqlite3.Error as exc:
            raise SessionError(f"Failed to list sessions: {exc}") from exc

        sessions: list[Session] = []
        for row in rows:
            sessions.append(
                Session(
                    id=row[0],
                    name=row[1],
                    created_at=row[2],
                    last_accessed=row[3],
                    message_count=row[4],
                    model=row[5],
                    system_prompt=row[6],
                    metadata=self._parse_metadata(row[7]),
                )
            )
        return sessions

    def get_session(self, session_id: str) -> Optional[Session]:
        """Retrieve a single session by ID.

        Args:
            session_id: The session ID (8-char UUID prefix).

        Returns:
            :class:`Session` or ``None`` if not found.
        """
        try:
            conn = self._connect()
            row = conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            conn.close()
        except sqlite3.Error as exc:
            raise SessionError(f"Failed to get session: {exc}") from exc

        if row is None:
            return None

        return Session(
            id=row[0],
            name=row[1],
            created_at=row[2],
            last_accessed=row[3],
            message_count=row[4],
            model=row[5],
            system_prompt=row[6],
            metadata=self._parse_metadata(row[7]),
        )

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its messages (cascade).

        Args:
            session_id: The session ID to delete.

        Returns:
            ``True`` if a session was deleted, ``False`` otherwise.
        """
        try:
            conn = self._connect()
            cursor = conn.execute(
                "DELETE FROM sessions WHERE id = ?", (session_id,)
            )
            conn.commit()
            deleted = cursor.rowcount > 0
            conn.close()
        except sqlite3.Error as exc:
            raise SessionError(f"Failed to delete session: {exc}") from exc

        if deleted:
            logger.info("Session deleted session_id=%s", session_id)
        return deleted

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        token_count: Optional[int] = None,
    ) -> None:
        """Add a message to a session.

        Args:
            session_id: Parent session ID.
            role: One of ``user``, ``assistant``, ``system``, ``tool``.
            content: Message text.
            token_count: Optional token count.

        Raises:
            SessionNotFoundError: If the session does not exist.
            SessionError: On database errors or invalid role.
        """
        valid_roles = ("user", "assistant", "system", "tool")
        if role not in valid_roles:
            raise SessionError(
                f"Invalid role '{role}'. Must be one of {valid_roles}"
            )

        # Verify session exists
        session = self.get_session(session_id)
        if session is None:
            raise SessionNotFoundError(f"Session not found: {session_id}")

        now = datetime.now(timezone.utc).isoformat()
        try:
            conn = self._connect()
            conn.execute(
                """
                INSERT INTO messages
                    (session_id, role, content, token_count, created_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, role, content, token_count, now, None),
            )
            # Update message_count on the session
            conn.execute(
                "UPDATE sessions SET message_count = message_count + 1, "
                "last_accessed = ? WHERE id = ?",
                (now, session_id),
            )
            conn.commit()
            conn.close()
        except sqlite3.Error as exc:
            raise SessionError(f"Failed to add message: {exc}") from exc

        logger.info(
            "Message added session_id=%s role=%s token_count=%s",
            session_id,
            role,
            token_count,
        )

    def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
    ) -> list[Message]:
        """Retrieve messages for a session.

        Args:
            session_id: Parent session ID.
            limit: Optional maximum number of messages to return.

        Returns:
            List of :class:`Message` objects ordered by ``created_at`` ASC.

        Raises:
            SessionNotFoundError: If the session does not exist.
        """
        session = self.get_session(session_id)
        if session is None:
            raise SessionNotFoundError(f"Session not found: {session_id}")

        try:
            conn = self._connect()
            if limit:
                rows = conn.execute(
                    "SELECT * FROM messages WHERE session_id = ? "
                    "ORDER BY created_at ASC LIMIT ?",
                    (session_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM messages WHERE session_id = ? "
                    "ORDER BY created_at ASC",
                    (session_id,),
                ).fetchall()
            conn.close()
        except sqlite3.Error as exc:
            raise SessionError(f"Failed to get messages: {exc}") from exc

        messages: list[Message] = []
        for row in rows:
            messages.append(
                Message(
                    id=row[0],
                    session_id=row[1],
                    role=row[2],
                    content=row[3],
                    token_count=row[4],
                    created_at=row[5],
                    metadata=self._parse_metadata(row[6]),
                )
            )
        return messages

    def update_last_accessed(self, session_id: str) -> None:
        """Update the ``last_accessed`` timestamp for a session.

        Args:
            session_id: The session ID.

        Raises:
            SessionNotFoundError: If the session does not exist.
        """
        session = self.get_session(session_id)
        if session is None:
            raise SessionNotFoundError(f"Session not found: {session_id}")

        now = datetime.now(timezone.utc).isoformat()
        try:
            conn = self._connect()
            conn.execute(
                "UPDATE sessions SET last_accessed = ? WHERE id = ?",
                (now, session_id),
            )
            conn.commit()
            conn.close()
        except sqlite3.Error as exc:
            raise SessionError(
                f"Failed to update last_accessed: {exc}"
            ) from exc

    # -- cleanup and archive -----------------------------------------------

    def cleanup_old_sessions(
        self,
        max_age_days: int = 30,
        max_session_count: int = 100,
        archive: bool = True,
        auto_cleanup_on_startup: bool = False,
    ) -> CleanupReport:
        """Clean up old sessions based on TTL and count limits.

        This method performs two cleanup passes:
        1. **TTL-based expiration**: Removes sessions older than ``max_age_days``
           based on the ``last_accessed`` timestamp.
        2. **Max session count enforcement**: If the total session count exceeds
           ``max_session_count``, the oldest sessions (by ``last_accessed``) are
           archived or deleted until the limit is met.

        Args:
            max_age_days: Maximum age in days before a session is considered
                expired. Defaults to 30.
            max_session_count: Maximum number of sessions to retain.
                Defaults to 100.
            archive: If ``True``, expired sessions are archived to
                ``~/.ceh/archive/`` before deletion. If ``False``, they are
                deleted directly. Defaults to ``True``.
            auto_cleanup_on_startup: If ``True``, run cleanup automatically
                when this method is called (useful for startup hooks).
                Defaults to ``False``.

        Returns:
            A :class:`CleanupReport` with statistics about the operation.

        Raises:
            CleanupError: On archive directory creation failures.
            SessionError: On database errors during cleanup.
        """
        now = datetime.now(timezone.utc)
        cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=max_age_days)

        sessions = self.list_sessions()
        report = CleanupReport(
            sessions_scanned=len(sessions),
            archive_dir=str(self._get_archive_dir()),
        )

        # Pass 1: TTL-based expiration
        expired_sessions: list[Session] = []
        for session in sessions:
            try:
                last_accessed = datetime.fromisoformat(session.last_accessed)
                if last_accessed < cutoff:
                    expired_sessions.append(session)
            except (ValueError, TypeError):
                # If we can't parse the timestamp, skip this session
                logger.warning(
                    "Skipping session with invalid last_accessed",
                    session_id=session.id,
                    last_accessed=session.last_accessed,
                )

        for session in expired_sessions:
            if archive:
                msg_count = self._count_messages(session.id)  # capture BEFORE archive deletes
                archived = self._archive_session(session)
                if archived:
                    report.sessions_archived += 1
                    report.messages_archived += msg_count
            else:
                self._delete_session_data(session.id)
            report.sessions_deleted += 1

        # Pass 2: Max session count enforcement
        remaining = self.list_sessions()
        if len(remaining) > max_session_count:
            # Sort by last_accessed ASC (oldest first)
            remaining.sort(key=lambda s: s.last_accessed)
            excess = len(remaining) - max_session_count
            for session in remaining[:excess]:
                if archive:
                    msg_count = self._count_messages(session.id)  # capture BEFORE archive deletes
                    archived = self._archive_session(session)
                    if archived:
                        report.sessions_archived += 1
                        report.messages_archived += msg_count
                else:
                    self._delete_session_data(session.id)
                report.sessions_deleted += 1

        # Calculate space freed (approximate)
        # We don't have the original size, so report 0 for now
        report.space_freed_bytes = 0

        logger.info(
            "Cleanup completed scanned=%d deleted=%d archived=%d messages_archived=%d",
            report.sessions_scanned,
            report.sessions_deleted,
            report.sessions_archived,
            report.messages_archived,
        )

        return report

    def _get_archive_dir(self) -> Path:
        """Return the archive directory path (~/.ceh/archive/)."""
        archive_dir = Path.home() / ".ceh" / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        return archive_dir

    def _archive_session(self, session: Session) -> bool:
        """Archive a session's data to the archive directory.

        Creates a JSON file containing the session metadata and all its
        messages.

        Args:
            session: The session to archive.

        Returns:
            ``True`` if archived successfully, ``False`` on failure.
        """
        try:
            archive_dir = self._get_archive_dir()
            archive_file = archive_dir / f"{session.id}_{''.join(session.last_accessed.split(':'))}.json"

            # Gather all messages for this session
            messages = self.get_messages(session.id)
            message_data = [
                {
                    "id": m.id,
                    "session_id": m.session_id,
                    "role": m.role,
                    "content": m.content,
                    "token_count": m.token_count,
                    "created_at": m.created_at,
                    "metadata": m.metadata,
                }
                for m in messages
            ]

            archive_data = {
                "session": {
                    "id": session.id,
                    "name": session.name,
                    "created_at": session.created_at,
                    "last_accessed": session.last_accessed,
                    "message_count": session.message_count,
                    "model": session.model,
                    "system_prompt": session.system_prompt,
                    "metadata": session.metadata,
                },
                "messages": message_data,
                "archived_at": datetime.now(timezone.utc).isoformat(),
            }

            with open(archive_file, "w", encoding="utf-8") as f:
                json.dump(archive_data, f, indent=2, default=str)

            # Delete the session data after successful archive
            self._delete_session_data(session.id)

            logger.info("Session archived session_id=%s archive_file=%s", session.id, str(archive_file))
            return True
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed to archive session session_id=%s error=%s", session.id, str(exc))
            return False

    def _delete_session_data(self, session_id: str) -> None:
        """Delete a session and all its messages from the database.

        Args:
            session_id: The session ID to delete.

        Raises:
            SessionError: On database errors.
        """
        try:
            conn = self._connect()
            # Delete messages first (sessions table has ON DELETE CASCADE)
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()
            conn.close()
        except sqlite3.Error as exc:
            raise SessionError(f"Failed to delete session data: {exc}") from exc

        logger.info("Session data deleted session_id=%s", session_id)

    def _count_messages(self, session_id: str) -> int:
        """Count the number of messages in a session.

        Args:
            session_id: The session ID.

        Returns:
            Number of messages, or 0 on error.
        """
        try:
            conn = self._connect()
            row = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)
            ).fetchone()
            conn.close()
            return row[0] if row else 0
        except sqlite3.Error:
            return 0

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _default_db_path() -> Path:
        """Return the default session database path (~/.ceh/sessions.db)."""
        home = Path.home()
        db_dir = home / ".ceh"
        db_dir.mkdir(parents=True, exist_ok=True)
        return db_dir / "sessions.db"

    def _ensure_db_dir(self) -> None:
        """Create the parent directory for the database if it doesn't exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        """Create and return a SQLite connection with foreign keys enabled.

        In debug mode, enables SQL query tracing on the connection.
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row

        # Enable SQL query tracing in debug mode
        if get_debug_mode():
            conn.set_trace_callback(lambda query: logger.debug("SQL: %s", query))

        return conn

    def _init_schema(self) -> None:
        """Initialise the SQLite schema (idempotent via IF NOT EXISTS)."""
        conn = self._connect()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_accessed TEXT NOT NULL,
                message_count INTEGER NOT NULL DEFAULT 0,
                model TEXT,
                system_prompt TEXT,
                metadata TEXT
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system', 'tool')),
                content TEXT NOT NULL,
                token_count INTEGER,
                created_at TEXT NOT NULL,
                metadata TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session_id
                ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_created_at
                ON sessions(created_at);
            CREATE INDEX IF NOT EXISTS idx_sessions_last_accessed
                ON sessions(last_accessed);
            """
        )
        conn.commit()
        conn.close()

    @staticmethod
    def _parse_metadata(raw: Optional[str]) -> Optional[dict[str, Any]]:
        """Parse a JSON metadata string, returning ``None`` if empty."""
        if not raw:
            return None
        import json

        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
