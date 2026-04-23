"""Tests for the C.E.H. Session Manager module."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from c_e_h.session_manager import (
    SessionError,
    SessionManager,
    SessionNotFoundError,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def session_manager() -> SessionManager:
    """Create a SessionManager with a temporary SQLite database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        sm = SessionManager(db_path=db_path)
        yield sm
    finally:
        os.unlink(db_path)


# ---------------------------------------------------------------------------
# Session CRUD tests
# ---------------------------------------------------------------------------


def test_create_session(session_manager: SessionManager) -> None:
    """Test creating a new session."""
    session = session_manager.create_session(
        name="test-session",
        system_prompt="You are a helpful assistant.",
        model="llama-3.1-8b",
    )

    assert session.id is not None
    assert len(session.id) == 8
    assert session.name == "test-session"
    assert session.system_prompt == "You are a helpful assistant."
    assert session.model == "llama-3.1-8b"
    assert session.message_count == 0
    assert session.created_at != ""
    assert session.last_accessed != ""


def test_create_session_minimal(session_manager: SessionManager) -> None:
    """Test creating a session with minimal arguments."""
    session = session_manager.create_session(name="minimal")

    assert session.name == "minimal"
    assert session.system_prompt is None
    assert session.model is None
    assert session.message_count == 0


def test_list_sessions_empty(session_manager: SessionManager) -> None:
    """Test listing sessions when none exist."""
    sessions = session_manager.list_sessions()
    assert sessions == []


def test_list_sessions_ordered(session_manager: SessionManager) -> None:
    """Test that sessions are ordered by last_accessed DESC."""
    s1 = session_manager.create_session(name="first")
    s2 = session_manager.create_session(name="second")

    sessions = session_manager.list_sessions()
    assert len(sessions) == 2
    # Most recently created should be first (last_accessed DESC)
    assert sessions[0].id == s2.id
    assert sessions[1].id == s1.id


def test_get_session(session_manager: SessionManager) -> None:
    """Test retrieving an existing session."""
    session = session_manager.create_session(name="get-test")
    retrieved = session_manager.get_session(session.id)

    assert retrieved is not None
    assert retrieved.id == session.id
    assert retrieved.name == "get-test"


def test_get_session_not_found(session_manager: SessionManager) -> None:
    """Test retrieving a non-existent session returns None."""
    result = session_manager.get_session("nonexistent")
    assert result is None


def test_delete_session(session_manager: SessionManager) -> None:
    """Test deleting an existing session."""
    session = session_manager.create_session(name="delete-test")
    result = session_manager.delete_session(session.id)

    assert result is True
    assert session_manager.get_session(session.id) is None


def test_delete_session_not_found(session_manager: SessionManager) -> None:
    """Test deleting a non-existent session returns False."""
    result = session_manager.delete_session("nonexistent")
    assert result is False


# ---------------------------------------------------------------------------
# Message storage tests
# ---------------------------------------------------------------------------


def test_add_message(session_manager: SessionManager) -> None:
    """Test adding a message to a session."""
    session = session_manager.create_session(name="msg-test")
    session_manager.add_message(
        session_id=session.id,
        role="user",
        content="Hello, assistant!",
        token_count=5,
    )

    # Verify message count updated
    updated = session_manager.get_session(session.id)
    assert updated.message_count == 1


def test_add_message_roles(session_manager: SessionManager) -> None:
    """Test adding messages with different roles."""
    session = session_manager.create_session(name="role-test")

    for role in ("user", "assistant", "system", "tool"):
        session_manager.add_message(
            session_id=session.id,
            role=role,
            content=f"Message from {role}",
        )

    messages = session_manager.get_messages(session.id)
    assert len(messages) == 4
    roles = [m.role for m in messages]
    assert roles == ["user", "assistant", "system", "tool"]


def test_add_message_invalid_role(session_manager: SessionManager) -> None:
    """Test that adding a message with an invalid role raises SessionError."""
    session = session_manager.create_session(name="role-error-test")

    with pytest.raises(SessionError, match="Invalid role"):
        session_manager.add_message(
            session_id=session.id,
            role="invalid_role",
            content="bad",
        )


def test_add_message_to_nonexistent_session(session_manager: SessionManager) -> None:
    """Test that adding a message to a non-existent session raises SessionNotFoundError."""
    with pytest.raises(SessionNotFoundError, match="Session not found"):
        session_manager.add_message(
            session_id="nonexistent",
            role="user",
            content="bad",
        )


def test_get_messages(session_manager: SessionManager) -> None:
    """Test retrieving messages from a session."""
    session = session_manager.create_session(name="get-msg-test")
    session_manager.add_message(session.id, "user", "Hello")
    session_manager.add_message(session.id, "assistant", "Hi there!")

    messages = session_manager.get_messages(session.id)
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[0].content == "Hello"
    assert messages[1].role == "assistant"
    assert messages[1].content == "Hi there!"


def test_get_messages_with_limit(session_manager: SessionManager) -> None:
    """Test retrieving a limited number of messages."""
    session = session_manager.create_session(name="limit-test")
    for i in range(5):
        session_manager.add_message(session.id, "user", f"Message {i}")

    messages = session_manager.get_messages(session.id, limit=3)
    assert len(messages) == 3


def test_get_messages_from_nonexistent_session(session_manager: SessionManager) -> None:
    """Test that getting messages from a non-existent session raises SessionNotFoundError."""
    with pytest.raises(SessionNotFoundError, match="Session not found"):
        session_manager.get_messages("nonexistent")


# ---------------------------------------------------------------------------
# Cascade delete tests
# ---------------------------------------------------------------------------


def test_cascade_delete_messages(session_manager: SessionManager) -> None:
    """Test that messages are deleted when the session is deleted (ON DELETE CASCADE)."""
    session = session_manager.create_session(name="cascade-test")
    session_manager.add_message(session.id, "user", "Hello")
    session_manager.add_message(session.id, "assistant", "Hi!")

    # Delete the session
    session_manager.delete_session(session.id)

    # Verify session is gone
    assert session_manager.get_session(session.id) is None

    # Verify messages are also gone (cascade)
    with pytest.raises(SessionNotFoundError):
        session_manager.get_messages(session.id)


# ---------------------------------------------------------------------------
# Index verification tests
# ---------------------------------------------------------------------------


def test_indexes_exist(session_manager: SessionManager) -> None:
    """Test that the expected indexes are created in the database."""
    # Create a session to trigger schema creation
    session_manager.create_session(name="index-test")

    conn = session_manager._connect()
    indexes = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
    ).fetchall()
    conn.close()

    index_names = {row[0] for row in indexes}
    assert "idx_messages_session_id" in index_names
    assert "idx_sessions_created_at" in index_names
    assert "idx_sessions_last_accessed" in index_names


# ---------------------------------------------------------------------------
# update_last_accessed tests
# ---------------------------------------------------------------------------


def test_update_last_accessed(session_manager: SessionManager) -> None:
    """Test updating the last_accessed timestamp."""
    session = session_manager.create_session(name="access-test")
    original_accessed = session.last_accessed

    # Small delay to ensure timestamp changes
    import time

    time.sleep(0.01)
    session_manager.update_last_accessed(session.id)

    updated = session_manager.get_session(session.id)
    assert updated.last_accessed != original_accessed


def test_update_last_accessed_nonexistent(session_manager: SessionManager) -> None:
    """Test that updating a non-existent session raises SessionNotFoundError."""
    with pytest.raises(SessionNotFoundError, match="Session not found"):
        session_manager.update_last_accessed("nonexistent")


# ---------------------------------------------------------------------------
# SessionManager default path test
# ---------------------------------------------------------------------------


def test_default_db_path() -> None:
    """Test that the default database path is ~/.ceh/sessions.db."""
    from c_e_h.session_manager import SessionManager

    default = SessionManager._default_db_path()
    assert default == Path.home() / ".ceh" / "sessions.db"


# ---------------------------------------------------------------------------
# Cleanup tests
# ---------------------------------------------------------------------------


def test_cleanup_old_sessions_ttl(session_manager: SessionManager) -> None:
    """Test that sessions older than max_age_days are cleaned up."""
    # Create a session
    session = session_manager.create_session(name="old-session")

    # Manually update last_accessed to 40 days ago
    from datetime import datetime, timedelta, timezone

    old_time = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    conn = session_manager._connect()
    conn.execute(
        "UPDATE sessions SET last_accessed = ? WHERE id = ?",
        (old_time, session.id),
    )
    conn.commit()
    conn.close()

    # Run cleanup with 30-day limit
    report = session_manager.cleanup_old_sessions(max_age_days=30, archive=False)

    assert report.sessions_scanned >= 1
    assert report.sessions_deleted >= 1
    # Verify session is deleted
    assert session_manager.get_session(session.id) is None


def test_cleanup_old_sessions_respects_max_age(session_manager: SessionManager) -> None:
    """Test that recent sessions are NOT cleaned up."""
    # Create a recent session
    session = session_manager.create_session(name="recent-session")

    # Run cleanup with 30-day limit
    report = session_manager.cleanup_old_sessions(max_age_days=30, archive=False)

    # Recent session should NOT be deleted
    assert session_manager.get_session(session.id) is not None
    # But it was scanned
    assert report.sessions_scanned >= 1


def test_cleanup_max_session_count(session_manager: SessionManager) -> None:
    """Test that max_session_count enforces the limit."""
    # Create 5 sessions
    for i in range(5):
        session_manager.create_session(name=f"session-{i}")

    # Set max_session_count to 3
    report = session_manager.cleanup_old_sessions(max_session_count=3, archive=False)

    remaining = session_manager.list_sessions()
    assert len(remaining) <= 3
    assert report.sessions_deleted >= 1


def test_cleanup_archive(session_manager: SessionManager) -> None:
    """Test that sessions are archived before deletion."""
    session = session_manager.create_session(
        name="archive-test",
        system_prompt="Test prompt",
    )
    session_manager.add_message(session.id, "user", "Hello")

    # The session is recent, so it won't be deleted by TTL.
    # But we can test the archive functionality directly.
    archive_dir = session_manager._get_archive_dir()
    assert archive_dir.exists()

    # Manually archive the session
    archived = session_manager._archive_session(session)
    assert archived is True

    # Verify archive file exists
    archive_files = list(archive_dir.glob(f"{session.id}_*.json"))
    assert len(archive_files) >= 1

    # Verify archive content
    with open(archive_files[0], "r") as f:
        archive_data = json.load(f)
    assert archive_data["session"]["name"] == "archive-test"
    assert archive_data["session"]["system_prompt"] == "Test prompt"
    assert len(archive_data["messages"]) >= 1


def test_cleanup_report_statistics(session_manager: SessionManager) -> None:
    """Test that cleanup report contains correct statistics."""
    # Create sessions
    session_manager.create_session(name="session-1")
    session_manager.create_session(name="session-2")

    report = session_manager.cleanup_old_sessions(archive=False)

    assert report.sessions_scanned == 2
    assert isinstance(report.sessions_deleted, int)
    assert isinstance(report.sessions_archived, int)
    assert isinstance(report.messages_archived, int)
    assert isinstance(report.space_freed_bytes, int)
    assert report.archive_dir != ""


def test_cleanup_empty_session_list(session_manager: SessionManager) -> None:
    """Test cleanup with no sessions."""
    report = session_manager.cleanup_old_sessions(archive=False)

    assert report.sessions_scanned == 0
    assert report.sessions_deleted == 0


def test_cleanup_archive_dir_creation(session_manager: SessionManager) -> None:
    """Test that archive directory is created if it doesn't exist."""
    archive_dir = session_manager._get_archive_dir()
    assert archive_dir.exists()


def test_cleanup_report_messages_archived(session_manager: SessionManager) -> None:
    """Test that messages_archived count is non-zero when archiving sessions with messages."""
    from datetime import datetime, timedelta, timezone

    # Create a session with messages
    session = session_manager.create_session(name="archived-session")
    session_manager.add_message(session.id, "user", "Hello")
    session_manager.add_message(session.id, "assistant", "Hi there!")

    # Manually set last_accessed to 40 days ago so TTL cleanup triggers
    old_time = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    conn = session_manager._connect()
    conn.execute(
        "UPDATE sessions SET last_accessed = ? WHERE id = ?",
        (old_time, session.id),
    )
    conn.commit()
    conn.close()

    # Run cleanup with archive enabled
    report = session_manager.cleanup_old_sessions(max_age_days=30, archive=True)

    # Verify messages_archived is non-zero
    assert report.messages_archived >= 2, f"Expected >= 2 messages archived, got {report.messages_archived}"
    assert report.sessions_archived >= 1
