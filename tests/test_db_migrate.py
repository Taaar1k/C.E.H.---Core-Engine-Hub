"""Tests for the SQLite schema migration system (:mod:`c_e_h.db_migrate`)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from c_e_h import db_migrate
from c_e_h.db_migrate import (
    SCHEMA_VERSION,
    MigrationRollbackError,
    get_schema_version,
    migrate_database,
    rollback_database,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    """Create a temporary SQLite database file and return its path."""
    return tmp_path / "test.db"


@pytest.fixture()
def empty_db(tmp_db: Path) -> Path:
    """Create an empty SQLite database file (no tables)."""
    conn = sqlite3.connect(str(tmp_db))
    conn.close()
    return tmp_db


@pytest.fixture()
def v1_db(tmp_db: Path) -> Path:
    """Create a database with v1 schema already applied."""
    conn = sqlite3.connect(str(tmp_db))
    conn.executescript(
        """
        CREATE TABLE schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now')),
            description TEXT
        );

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

        CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sessions(created_at);
        CREATE INDEX IF NOT EXISTS idx_sessions_last_accessed ON sessions(last_accessed);

        INSERT INTO schema_migrations (version, description) VALUES (1, 'Initial schema');
        """
    )
    conn.commit()
    conn.close()
    return tmp_db

# ---------------------------------------------------------------------------
# Tests — SCHEMA_VERSION constant
# ---------------------------------------------------------------------------


class TestSchemaVersion:
    """Verify the SCHEMA_VERSION constant."""

    def test_schema_version_is_int(self) -> None:
        assert isinstance(SCHEMA_VERSION, int)

    def test_schema_version_is_positive(self) -> None:
        assert SCHEMA_VERSION > 0

    def test_module_schema_version_matches_constant(self) -> None:
        assert db_migrate.SCHEMA_VERSION == SCHEMA_VERSION

# ---------------------------------------------------------------------------
# Tests — migrate_database (migration application)
# ---------------------------------------------------------------------------


class TestMigrateDatabase:
    """Test migration application."""

    def test_migrate_nonexistent_db_is_noop(self, tmp_db: Path) -> None:
        """migrate_database should not error when the DB file does not exist."""
        migrate_database(tmp_db)  # should not raise

    def test_migrate_empty_db_applies_v1(self, empty_db: Path) -> None:
        """A fresh database should have v1 schema applied after migration."""
        migrate_database(empty_db)

        conn = sqlite3.connect(str(empty_db))
        try:
            # schema_migrations table should exist
            row = conn.execute(
                "SELECT version FROM schema_migrations WHERE version = 1"
            ).fetchone()
            assert row is not None
            assert row[0] == 1

            # sessions table should exist
            table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
            ).fetchone()
            assert table is not None

            # messages table should exist
            table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='messages'"
            ).fetchone()
            assert table is not None
        finally:
            conn.close()

    def test_migrate_v1_db_is_noop(self, v1_db: Path) -> None:
        """A database already at SCHEMA_VERSION should not change."""
        migrate_database(v1_db)

        version = get_schema_version(v1_db)
        assert version == SCHEMA_VERSION

    def test_migrate_records_description(self, empty_db: Path) -> None:
        """Migration should record a description in schema_migrations."""
        migrate_database(empty_db)

        conn = sqlite3.connect(str(empty_db))
        try:
            row = conn.execute(
                "SELECT description FROM schema_migrations WHERE version = 1"
            ).fetchone()
            assert row is not None
            assert "Initial schema" in row[0]
        finally:
            conn.close()

    def test_migrate_creates_schema_migrations_table(self, empty_db: Path) -> None:
        """Migration should create schema_migrations table."""
        migrate_database(empty_db)

        conn = sqlite3.connect(str(empty_db))
        try:
            table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ).fetchone()
            assert table is not None
        finally:
            conn.close()

# ---------------------------------------------------------------------------
# Tests — Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    """Test that migrations are idempotent."""

    def test_double_migration_succeeds(self, empty_db: Path) -> None:
        """Running migration twice should not raise."""
        migrate_database(empty_db)
        migrate_database(empty_db)  # second run

        version = get_schema_version(empty_db)
        assert version == SCHEMA_VERSION

    def test_triple_migration_succeeds(self, empty_db: Path) -> None:
        """Running migration three times should not raise."""
        for _ in range(3):
            migrate_database(empty_db)

        version = get_schema_version(empty_db)
        assert version == SCHEMA_VERSION

    def test_schema_migrations_has_single_entry(self, empty_db: Path) -> None:
        """Running migration multiple times should not duplicate entries."""
        migrate_database(empty_db)
        migrate_database(empty_db)

        conn = sqlite3.connect(str(empty_db))
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM schema_migrations WHERE version = 1"
            ).fetchone()[0]
            assert count == 1
        finally:
            conn.close()

# ---------------------------------------------------------------------------
# Tests — Version tracking
# ---------------------------------------------------------------------------


class TestVersionTracking:
    """Test schema version tracking."""

    def test_get_version_nonexistent_db(self, tmp_db: Path) -> None:
        """Version of a non-existent database should be 0."""
        assert get_schema_version(tmp_db) == 0

    def test_get_version_empty_db(self, empty_db: Path) -> None:
        """Version of an empty database (no migrations table) should be 0."""
        assert get_schema_version(empty_db) == 0

    def test_get_version_after_migration(self, empty_db: Path) -> None:
        """Version should be SCHEMA_VERSION after migration."""
        migrate_database(empty_db)
        assert get_schema_version(empty_db) == SCHEMA_VERSION

    def test_get_version_v1_db(self, v1_db: Path) -> None:
        """Version should be 1 for a v1 database."""
        assert get_schema_version(v1_db) == 1

# ---------------------------------------------------------------------------
# Tests — rollback_database
# ---------------------------------------------------------------------------


class TestRollbackDatabase:
    """Test migration rollback."""

    def test_rollback_nonexistent_db(self, tmp_db: Path) -> None:
        """Rollback on non-existent DB should raise MigrationRollbackError."""
        with pytest.raises(MigrationRollbackError, match="does not exist"):
            rollback_database(tmp_db, target_version=0)

    def test_rollback_v1_db_raises(self, v1_db: Path) -> None:
        """Rollback of v1 should raise MigrationRollbackError."""
        with pytest.raises(MigrationRollbackError, match="Cannot rollback initial schema"):
            rollback_database(v1_db, target_version=0)
        # Version should still be 1 (rollback failed, record preserved)
        version = get_schema_version(v1_db)
        assert version == 1

    def test_rollback_invalid_target_negative(self, empty_db: Path) -> None:
        """Rollback with negative target should raise."""
        with pytest.raises(MigrationRollbackError, match="Invalid target"):
            rollback_database(empty_db, target_version=-1)

    def test_rollback_already_at_target(self, v1_db: Path) -> None:
        """Rollback to current version should be a no-op."""
        rollback_database(v1_db, target_version=1)
        version = get_schema_version(v1_db)
        assert version == 1

# ---------------------------------------------------------------------------
# Tests — Integration with SessionManager
# ---------------------------------------------------------------------------


class TestSessionManagerIntegration:
    """Test that SessionManager runs migrations on init."""

    def test_session_manager_runs_migration(self, tmp_db: Path) -> None:
        """SessionManager should apply migrations when created."""
        # Create an empty database
        conn = sqlite3.connect(str(tmp_db))
        conn.close()

        # Import here to avoid circular imports at module level
        from c_e_h.session_manager import SessionManager

        _sm = SessionManager(db_path=str(tmp_db))

        # Verify migrations were applied
        version = get_schema_version(tmp_db)
        assert version == SCHEMA_VERSION

        # Verify tables exist
        conn = sqlite3.connect(str(tmp_db))
        try:
            table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
            ).fetchone()
            assert table is not None
        finally:
            conn.close()

    def test_session_manager_creates_db_and_migrates(self, tmp_path: Path) -> None:
        """SessionManager should create DB directory and apply migrations."""
        db_path = tmp_path / "nested" / "sessions.db"

        from c_e_h.session_manager import SessionManager

        _sm = SessionManager(db_path=str(db_path))

        assert db_path.exists()
        version = get_schema_version(db_path)
        assert version == SCHEMA_VERSION
