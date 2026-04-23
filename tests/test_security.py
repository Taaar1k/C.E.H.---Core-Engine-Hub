"""Tests for the C.E.H. Security module.

Covers:
  - Path traversal prevention (safe_path)
  - Command whitelist validation (validate_command)
  - Input sanitization (sanitize_input)
  - Security event logging (log_security_event)
  - SecurityPolicy class integration
  - Exception types (PathTraversalError, CommandNotAllowedError, InputValidationError)
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from c_e_h.security import (
    ALLOWED_COMMANDS,
    CommandNotAllowedError,
    InputValidationError,
    PathTraversalError,
    SecurityPolicy,
    log_security_event,
    safe_path,
    sanitize_input,
    validate_command,
)

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture()
def temp_workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace directory with a subdirectory."""
    sub = tmp_path / "subdir"
    sub.mkdir()
    (tmp_path / "file.txt").write_text("hello")
    (sub / "nested.txt").write_text("world")
    return tmp_path


# ===========================================================================
# safe_path Tests
# ===========================================================================


class TestSafePath:
    """Tests for safe_path function and SecurityPolicy.safe_path method."""

    def test_safe_path_returns_resolved_path(self, temp_workspace: Path):
        """Test that safe_path returns the resolved path for valid input."""
        result = safe_path(str(temp_workspace), "file.txt")
        expected = str(temp_workspace / "file.txt")
        assert result == os.path.realpath(expected)

    def test_safe_path_resolves_subdirectory(self, temp_workspace: Path):
        """Test that safe_path resolves paths within subdirectories."""
        result = safe_path(str(temp_workspace), "subdir/nested.txt")
        expected = str(temp_workspace / "subdir" / "nested.txt")
        assert result == os.path.realpath(expected)

    def test_safe_path_resolves_dot_components(self, temp_workspace: Path):
        """Test that safe_path resolves ./ and ../ components."""
        result = safe_path(str(temp_workspace), "./file.txt")
        expected = str(temp_workspace / "file.txt")
        assert result == os.path.realpath(expected)

    def test_safe_path_rejects_path_traversal(self, temp_workspace: Path):
        """Test that safe_path raises PathTraversalError for ../ traversal."""
        with pytest.raises(PathTraversalError, match="Path traversal detected"):
            safe_path(str(temp_workspace), "../etc/passwd")

    def test_safe_path_rejects_double_traversal(self, temp_workspace: Path):
        """Test that safe_path raises PathTraversalError for ../../ traversal."""
        with pytest.raises(PathTraversalError, match="Path traversal detected"):
            safe_path(str(temp_workspace), "../../etc/passwd")

    def test_safe_path_rejects_traversal_in_middle(self, temp_workspace: Path):
        """Test that safe_path raises PathTraversalError for traversal in middle."""
        with pytest.raises(PathTraversalError, match="Path traversal detected"):
            safe_path(str(temp_workspace), "subdir/../../etc/passwd")

    def test_safe_path_allows_base_dir_itself(self, temp_workspace: Path):
        """Test that safe_path allows the base directory itself."""
        result = safe_path(str(temp_workspace), ".")
        assert result == os.path.realpath(str(temp_workspace))

    def test_safe_path_class_method(self, temp_workspace: Path):
        """Test SecurityPolicy.safe_path as instance method."""
        policy = SecurityPolicy()
        result = policy.safe_path(str(temp_workspace), "file.txt")
        expected = str(temp_workspace / "file.txt")
        assert result == os.path.realpath(expected)

    def test_safe_path_class_rejects_traversal(self, temp_workspace: Path):
        """Test SecurityPolicy.safe_path rejects path traversal."""
        policy = SecurityPolicy()
        with pytest.raises(PathTraversalError, match="Path traversal detected"):
            policy.safe_path(str(temp_workspace), "../etc/passwd")

    def test_safe_path_with_absolute_user_path(self, temp_workspace: Path):
        """Test that safe_path rejects absolute user paths outside base."""
        with pytest.raises(PathTraversalError, match="Path traversal detected"):
            safe_path(str(temp_workspace), "/etc/passwd")


# ===========================================================================
# validate_command Tests
# ===========================================================================


class TestValidateCommand:
    """Tests for validate_command function and SecurityPolicy.validate_command method."""

    def test_validate_command_allows_whitelisted(self):
        """Test that validate_command allows commands in ALLOWED_COMMANDS."""
        for cmd in ("ls", "cat", "grep", "find", "git", "cp", "mv", "mkdir", "echo"):
            result = validate_command(f"{cmd} --help")
            assert result == cmd

    def test_validate_command_rejects_non_whitelisted(self):
        """Test that validate_command rejects commands not in whitelist."""
        # Use a clearly non-whitelisted command
        with pytest.raises(CommandNotAllowedError, match="not in the whitelist"):
            validate_command("perl -e 'print 1'")

    def test_validate_command_rejects_dangerous_commands(self):
        """Test that dangerous commands are rejected."""
        dangerous = ("wget", "curl", "python", "bash", "sh", "chmod", "chown")
        for cmd in dangerous:
            with pytest.raises(CommandNotAllowedError, match="not in the whitelist"):
                validate_command(f"{cmd} something")

    def test_validate_command_rejects_empty(self):
        """Test that validate_command rejects empty commands."""
        with pytest.raises(CommandNotAllowedError, match="Empty command"):
            validate_command("")

    def test_validate_command_rejects_whitespace_only(self):
        """Test that validate_command rejects whitespace-only commands."""
        with pytest.raises(CommandNotAllowedError, match="Empty command"):
            validate_command("   ")

    def test_validate_command_returns_cmd_name(self):
        """Test that validate_command returns the base command name."""
        result = validate_command("ls -la /tmp")
        assert result == "ls"

    def test_validate_command_class_method(self):
        """Test SecurityPolicy.validate_command as instance method."""
        policy = SecurityPolicy()
        result = policy.validate_command("git status")
        assert result == "git"

    def test_validate_command_class_rejects_non_whitelisted(self):
        """Test SecurityPolicy.validate_command rejects non-whitelisted."""
        policy = SecurityPolicy()
        with pytest.raises(CommandNotAllowedError, match="not in the whitelist"):
            policy.validate_command("perl -e 'print 1'")

    def test_validate_command_with_path_prefix(self):
        """Test that validate_command extracts basename from path."""
        # /bin/ls should resolve to "ls" via basename
        result = validate_command("/bin/ls -la")
        assert result == "ls"

    def test_validate_command_uses_shutil_which(self):
        """Test that validate_command uses shutil.which to verify executable."""
        with patch("c_e_h.security.shutil.which", return_value=None):
            with pytest.raises(CommandNotAllowedError, match="not found in PATH"):
                validate_command("ls --help")


# ===========================================================================
# sanitize_input Tests
# ===========================================================================


class TestSanitizeInput:
    """Tests for sanitize_input function and SecurityPolicy.sanitize_input method."""

    def test_sanitize_input_returns_string(self):
        """Test that sanitize_input returns a string."""
        result = sanitize_input("hello world")
        assert isinstance(result, str)
        assert result == "hello world"

    def test_sanitize_input_converts_non_string(self):
        """Test that sanitize_input converts non-string input."""
        result = sanitize_input(12345)
        assert result == "12345"

    def test_sanitize_input_truncates_long_input(self):
        """Test that sanitize_input truncates input exceeding max_length."""
        long_text = "a" * 200
        result = sanitize_input(long_text, max_length=50)
        assert len(result) == 50
        assert result == "a" * 50

    def test_sanitize_input_respects_default_max_length(self):
        """Test that sanitize_input uses default max_length (10000)."""
        short = "x" * 100
        result = sanitize_input(short)
        assert result == short

    def test_sanitize_input_rejects_zero_max_length(self):
        """Test that sanitize_input raises InputValidationError for max_length=0."""
        with pytest.raises(InputValidationError, match="exceeds maximum 0"):
            sanitize_input("anything", max_length=0)

    def test_sanitize_input_exact_length(self):
        """Test that sanitize_input allows input exactly at max_length."""
        exact = "b" * 100
        result = sanitize_input(exact, max_length=100)
        assert len(result) == 100
        assert result == exact

    def test_sanitize_input_class_method(self):
        """Test SecurityPolicy.sanitize_input as instance method."""
        policy = SecurityPolicy()
        result = policy.sanitize_input("test", max_length=100)
        assert result == "test"

    def test_sanitize_input_class_truncates(self):
        """Test SecurityPolicy.sanitize_input truncates correctly."""
        policy = SecurityPolicy()
        result = policy.sanitize_input("x" * 500, max_length=100)
        assert len(result) == 100

    def test_sanitize_input_custom_default(self):
        """Test SecurityPolicy with custom default_max_length."""
        policy = SecurityPolicy(default_max_length=50)
        result = policy.sanitize_input("a" * 100)
        assert len(result) == 50


# ===========================================================================
# log_security_event Tests
# ===========================================================================


class TestLogSecurityEvent:
    """Tests for log_security_event function and SecurityPolicy.log_security_event method."""

    def test_log_security_event_does_not_raise(self):
        """Test that log_security_event does not raise exceptions."""
        # Should not raise
        log_security_event("test_event", {"key": "value"})
        log_security_event("test_event")

    def test_log_security_event_class_method(self):
        """Test SecurityPolicy.log_security_event as instance method."""
        policy = SecurityPolicy()
        # Should not raise
        policy.log_security_event("test_event", {"detail": "test"})

    def test_log_security_event_with_details(self):
        """Test that log_security_event accepts details dict."""
        details = {"path": "/tmp/test", "user": "testuser"}
        # Should not raise
        log_security_event("path_traversal_detected", details)


# ===========================================================================
# SecurityPolicy Class Tests
# ===========================================================================


class TestSecurityPolicy:
    """Integration tests for SecurityPolicy class."""

    def test_policy_default_allowed_commands(self):
        """Test that SecurityPolicy has default ALLOWED_COMMANDS."""
        policy = SecurityPolicy()
        assert "ls" in policy.allowed_commands
        assert "cat" in policy.allowed_commands
        assert "rm" in policy.allowed_commands

    def test_policy_custom_allowed_commands(self):
        """Test that SecurityPolicy accepts custom allowed_commands."""
        custom = {"ls", "cat"}
        policy = SecurityPolicy(allowed_commands=custom)
        assert policy.allowed_commands == frozenset(custom)
        assert "git" not in policy.allowed_commands

    def test_policy_default_max_length(self):
        """Test that SecurityPolicy has default max_length of 10000."""
        policy = SecurityPolicy()
        assert policy.default_max_length == 10000

    def test_policy_custom_max_length(self):
        """Test that SecurityPolicy accepts custom default_max_length."""
        policy = SecurityPolicy(default_max_length=5000)
        assert policy.default_max_length == 5000

    def test_policy_full_workflow(self, temp_workspace: Path):
        """Test a full security workflow with SecurityPolicy."""
        policy = SecurityPolicy()

        # Path validation
        resolved = policy.safe_path(str(temp_workspace), "file.txt")
        assert os.path.isfile(resolved)

        # Command validation
        cmd_name = policy.validate_command("ls -la")
        assert cmd_name == "ls"

        # Input sanitization
        cleaned = policy.sanitize_input("x" * 200, max_length=50)
        assert len(cleaned) == 50

        # Security event logging
        policy.log_security_event("test_event", {"info": "test"})


# ===========================================================================
# ALLOWED_COMMANDS Constant Tests
# ===========================================================================


class TestAllowedCommands:
    """Tests for ALLOWED_COMMANDS constant."""

    def test_allowed_commands_is_frozenset(self):
        """Test that ALLOWED_COMMANDS is a frozenset."""
        assert isinstance(ALLOWED_COMMANDS, frozenset)

    def test_allowed_commands_contains_expected(self):
        """Test that ALLOWED_COMMANDS contains expected commands."""
        expected = {"ls", "cat", "grep", "find", "git", "cp", "mv", "rm", "mkdir", "echo"}
        assert ALLOWED_COMMANDS == expected

    def test_allowed_commands_is_immutable(self):
        """Test that ALLOWED_COMMANDS cannot be modified."""
        with pytest.raises(AttributeError):
            ALLOWED_COMMANDS.add("new_command")


# ===========================================================================
# Exception Type Tests
# ===========================================================================


class TestExceptionTypes:
    """Tests for security exception types."""

    def test_path_traversal_error_is_security_error(self):
        """Test that PathTraversalError is a SecurityError subclass."""
        from c_e_h.security import SecurityError

        assert issubclass(PathTraversalError, SecurityError)

    def test_command_not_allowed_error_is_security_error(self):
        """Test that CommandNotAllowedError is a SecurityError subclass."""
        from c_e_h.security import SecurityError

        assert issubclass(CommandNotAllowedError, SecurityError)

    def test_input_validation_error_is_security_error(self):
        """Test that InputValidationError is a SecurityError subclass."""
        from c_e_h.security import SecurityError

        assert issubclass(InputValidationError, SecurityError)


# ===========================================================================
# Tools Integration Tests
# ===========================================================================


class TestToolsIntegration:
    """Tests for security integration in tools.py."""

    def test_read_file_rejects_path_traversal(self, temp_workspace: Path):
        """Test that read_file tool rejects path traversal."""
        from c_e_h.tools import read_file

        with pytest.raises(PathTraversalError):
            read_file("../etc/passwd")

    def test_write_file_rejects_path_traversal(self, temp_workspace: Path):
        """Test that write_file tool rejects path traversal."""
        from c_e_h.tools import write_file

        with pytest.raises(PathTraversalError):
            write_file("../etc/evil.txt", "malicious content")

    def test_execute_command_rejects_non_whitelisted(self):
        """Test that execute_command tool rejects non-whitelisted commands."""
        from c_e_h.tools import execute_command

        with pytest.raises(CommandNotAllowedError):
            execute_command("wget http://example.com")

    def test_execute_command_allows_whitelisted(self):
        """Test that execute_command tool allows whitelisted commands."""
        from c_e_h.tools import execute_command

        # echo is whitelisted and always available
        result = execute_command("echo hello")
        assert "hello" in result
        assert "Return code: 0" in result

    def test_tools_use_shell_false(self):
        """Verify that sandbox_execute uses shell=False (code review)."""
        import inspect

        from c_e_h.tools import sandbox_execute

        source = inspect.getsource(sandbox_execute)
        # Check that subprocess.run uses shell=False
        assert '"shell": False' in source or "'shell': False" in source
