"""SQLite schema migration system for C.E.H.

Provides versioned migration support for the session database, including
additive changes via ``ALTER TABLE ADD COLUMN`` and complex changes via
the table-rebuild pattern.  All migration functions are idempotent.

Usage::

    from c_e_h.db_migrate import migrate_database, SCHEMA_VERSION

    migrate_database(Path("/path/to/sessions.db"))

"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Callable, Dict, List, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Version constant
# ---------------------------------------------------------------------------

#: Current schema version.  Increment this when adding new migrations.
SCHEMA_VERSION: int = 1

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class MigrationError(Exception):
    """Raised when a migration fails."""


class MigrationRollbackError(MigrationError):
    """Raised when a rollback (downgrade) fails."""

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

#: Mapping from target version -> (description, migration function).
_MIGRATIONS: Dict[int, Tuple[str, Callable[[sqlite3.Connection], None]]] = {}


def _register_migration(
    version: int,
    description: str,
) -> Callable[[Callable[[sqlite3.Connection], None]], Callable[[sqlite3.Connection], None]]:
    """Decorator to register a migration function.

    Args:
        version: Target schema version.
        description: Human-readable description of the migration.

    Returns:
        Decorator function.
    """

    def decorator(func: Callable[[sqlite3.Connection], None]) -> Callable[[sqlite3.Connection], None]:
        _MIGRATIONS[version] = (description, func)
        return func

    return decorator


def _ensure_schema_migrations_table(conn: sqlite3.Connection) -> None:
    """Create the ``schema_migrations`` table if it does not exist.

    Args:
        conn: SQLite connection.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now')),
            description TEXT
        );
        """
    )
    conn.commit()


def _get_current_version(conn: sqlite3.Connection) -> int:
    """Return the current schema version, or 0 if no migrations exist.

    Args:
        conn: SQLite connection.

    Returns:
        Current version number.
    """
    row = conn.execute(
        "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return 0
    return int(row[0])


def _record_migration(
    conn: sqlite3.Connection, version: int, description: str
) -> None:
    """Record a migration as applied.

    Args:
        conn: SQLite connection.
        version: Schema version that was applied.
        description: Migration description.
    """
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations (version, description) VALUES (?, ?)",
        (version, description),
    )
    conn.commit()

# ---------------------------------------------------------------------------
# Migration functions
# ---------------------------------------------------------------------------


@_register_migration(
    1,
    "Initial schema: sessions, messages, indexes",
)
def _migrate_to_v1(conn: sqlite3.Connection) -> None:
    """Apply v1 migration: create initial schema tables.

    This migration creates the ``sessions`` and ``messages`` tables
    along with supporting indexes.  It is idempotent (uses IF NOT EXISTS).

    Args:
        conn: SQLite connection.
    """
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def migrate_database(db_path: str | Path) -> None:
    """Apply pending database migrations.

    Creates the ``schema_migrations`` table if needed, determines the
    current version, and applies all pending migrations in order up to
    :data:`SCHEMA_VERSION`.

    This function is safe to call multiple times — all migrations are
    idempotent.

    Args:
        db_path: Path to the SQLite database file.

    Raises:
        MigrationError: If a migration fails to apply.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        logger.info("Database does not exist yet; skipping migrations db_path=%s", str(db_path))
        return

    conn = sqlite3.connect(str(db_path))
    try:
        _ensure_schema_migrations_table(conn)
        current_version = _get_current_version(conn)
        logger.info(
            "Migration check current_version=%d target_version=%d",
            current_version,
            SCHEMA_VERSION,
        )

        if current_version >= SCHEMA_VERSION:
            logger.info("Database is up to date version=%d", current_version)
            return

        # Apply pending migrations in order
        for version in range(current_version + 1, SCHEMA_VERSION + 1):
            if version not in _MIGRATIONS:
                raise MigrationError(f"No migration registered for version {version}")
            description, func = _MIGRATIONS[version]
            logger.info(
                "Applying migration version=%d description=%s",
                version,
                description,
            )
            try:
                func(conn)
                _record_migration(conn, version, description)
                logger.info(
                    "Migration applied version=%d description=%s",
                    version,
                    description,
                )
            except sqlite3.Error as exc:
                conn.rollback()
                raise MigrationError(
                    f"Migration v{version} ({description}) failed: {exc}"
                ) from exc

        conn.commit()
    finally:
        conn.close()


def rollback_database(
    db_path: str | Path,
    target_version: int,
) -> None:
    """Rollback (downgrade) the database schema to a previous version.

    .. warning::
        This is a destructive operation.  Data in newly added columns
        or tables may be lost.  Use with caution.

    Args:
        db_path: Path to the SQLite database file.
        target_version: Target version to rollback to (must be < current).

    Raises:
        MigrationRollbackError: If rollback fails or target_version is
            invalid.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        raise MigrationRollbackError("Database does not exist")

    if target_version < 0:
        raise MigrationRollbackError(f"Invalid target version: {target_version}")

    conn = sqlite3.connect(str(db_path))
    try:
        _ensure_schema_migrations_table(conn)
        current_version = _get_current_version(conn)

        if current_version <= target_version:
            logger.info(
                "Database already at or below target version current=%d target=%d",
                current_version,
                target_version,
            )
            return

        # Collect migrations to rollback in reverse order
        versions_to_rollback: List[int] = []
        for v in range(current_version, target_version, -1):
            if v in _MIGRATIONS:
                versions_to_rollback.append(v)

        if not versions_to_rollback:
            raise MigrationRollbackError(
                f"No migrations found to rollback from {current_version} to {target_version}"
            )

        for version in versions_to_rollback:
            description, _ = _MIGRATIONS[version]
            logger.info(
                "Rolling back migration version=%d description=%s",
                version,
                description,
            )
            try:
                _rollback_version(conn, version)
                # Remove the migration record
                conn.execute(
                    "DELETE FROM schema_migrations WHERE version = ?",
                    (version,),
                )
                conn.commit()
                logger.info(
                    "Rollback complete version=%d",
                    version,
                )
            except sqlite3.Error as exc:
                conn.rollback()
                raise MigrationRollbackError(
                    f"Rollback of v{version} ({description}) failed: {exc}"
                ) from exc

    finally:
        conn.close()


def _rollback_version(conn: sqlite3.Connection, version: int) -> None:
    """Perform the actual rollback for a single version.

    For the initial schema (v1), this raises
    :class:`MigrationRollbackError` because the schema tables cannot be
    cleanly dropped without losing data.  Future migrations should
    implement proper rollback logic.

    Args:
        conn: SQLite connection.
        version: Version to rollback from.

    Raises:
        MigrationRollbackError: If rollback cannot be performed.
    """
    if version == 1:
        # Cannot safely rollback the initial schema — tables may contain data.
        logger.warning(
            "Cannot safely rollback initial schema (v1); data may be lost",
        )
        raise MigrationRollbackError(
            "Cannot rollback initial schema (v1); data may be lost"
        )

    raise MigrationRollbackError(
        f"No rollback logic implemented for version {version}"
    )


def get_schema_version(db_path: str | Path) -> int:
    """Return the current schema version of the database.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Current schema version, or 0 if the database has no migrations.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return 0

    conn = sqlite3.connect(str(db_path))
    try:
        _ensure_schema_migrations_table(conn)
        return _get_current_version(conn)
    finally:
        conn.close()
