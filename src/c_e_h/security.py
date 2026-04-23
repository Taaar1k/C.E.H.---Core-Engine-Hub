"""Security hardening module for C.E.H.

Provides:
  - SecurityPolicy: central security policy with path validation and command whitelisting
  - safe_path(): path traversal prevention using os.path.realpath()
  - validate_command(): command whitelist enforcement
  - sanitize_input(): input length limit enforcement
  - log_security_event(): security event logging via stdlib logging

All functions use type hints and docstrings.
No hardcoded secrets or credentials.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)

# Command whitelist — only these base commands are permitted
ALLOWED_COMMANDS: Set[str] = frozenset({
    "ls", "cat", "grep", "find", "git", "cp", "mv", "rm", "mkdir", "echo",
})

# Default maximum input length in characters
DEFAULT_MAX_INPUT_LENGTH: int = 10000


class SecurityError(Exception):
    """Base exception for security violations."""

    pass


class PathTraversalError(SecurityError):
    """Raised when a path traversal attempt is detected."""

    pass


class CommandNotAllowedError(SecurityError):
    """Raised when a command is not in the whitelist."""

    pass


class InputValidationError(SecurityError):
    """Raised when input validation fails (e.g., length exceeded)."""

    pass


class SecurityPolicy:
    """Central security policy for path validation, command whitelisting,
    and input sanitization.

    Usage::

        policy = SecurityPolicy()
        resolved = policy.safe_path("/workspace", "subdir/file.txt")
        policy.validate_command("ls -la")
        cleaned = policy.sanitize_input(long_text, max_length=5000)
        policy.log_security_event("path_traversal", {"path": "../etc/passwd"})
    """

    def __init__(
        self,
        allowed_commands: Optional[Set[str]] = None,
        default_max_length: int = DEFAULT_MAX_INPUT_LENGTH,
    ) -> None:
        """Initialize SecurityPolicy.

        Args:
            allowed_commands: Custom set of allowed command base names.
                Defaults to ``ALLOWED_COMMANDS``.
            default_max_length: Default maximum input length in characters.
                Defaults to ``DEFAULT_MAX_INPUT_LENGTH`` (10000).
        """
        self._allowed_commands: Set[str] = (
            allowed_commands if allowed_commands is not None else ALLOWED_COMMANDS
        )
        self._default_max_length: int = default_max_length

    # ------------------------------------------------------------------
    # Path Validation
    # ------------------------------------------------------------------

    def safe_path(self, base_dir: str, user_path: str) -> str:
        """Resolve a user-supplied path relative to a base directory and
        verify it stays within the base directory.

        Uses ``os.path.realpath()`` to resolve symlinks and ``..`` components.

        Args:
            base_dir: The allowed base directory (e.g. ``"/workspace"``).
            user_path: The user-supplied path relative to ``base_dir``
                (e.g. ``"subdir/file.txt"`` or ``"../etc/passwd"``).

        Returns:
            The resolved absolute path.

        Raises:
            PathTraversalError: If the resolved path escapes ``base_dir``.
        """
        joined = os.path.join(base_dir, user_path)
        resolved = os.path.realpath(joined)
        base_resolved = os.path.realpath(base_dir)

        if resolved == base_resolved:
            return resolved

        # Normalize separator for startswith comparison
        sep = os.sep
        if not resolved.startswith(base_resolved + sep):
            self.log_security_event(
                event_type="path_traversal_detected",
                details={"user_path": user_path, "resolved": resolved, "base": base_resolved},
            )
            raise PathTraversalError(
                f"Path traversal detected: {user_path}"
            )
        return resolved

    def safe_path_any(self, allowed_bases: list[str], user_path: str) -> str:
        """Check if a resolved path is within any of the allowed base directories.

        Args:
            allowed_bases: List of allowed base directories.
            user_path: An already-resolved absolute path to check.

        Returns:
            The resolved path if it is within any allowed base.

        Raises:
            PathTraversalError: If the path is outside all allowed bases.
        """
        resolved = os.path.realpath(user_path)
        for base in allowed_bases:
            base_resolved = os.path.realpath(base)
            if resolved == base_resolved:
                return resolved
            sep = os.sep
            if resolved.startswith(base_resolved + sep):
                return resolved
        self.log_security_event(
            event_type="path_traversal_detected",
            details={"user_path": user_path, "resolved": resolved, "allowed_bases": allowed_bases},
        )
        raise PathTraversalError(f"Path outside allowed directories: {user_path}")

    # ------------------------------------------------------------------
    # Command Whitelisting
    # ------------------------------------------------------------------

    def validate_command(self, command: str) -> str:
        """Validate that the base command is in the allowed whitelist.

        Extracts the base command name (first token, basename only) and
        checks it against ``ALLOWED_COMMANDS``. Also verifies the
        executable exists in PATH using ``shutil.which()``.

        Args:
            command: The full command string (e.g. ``"ls -la /tmp"``).

        Returns:
            The validated base command name.

        Raises:
            CommandNotAllowedError: If the command is not whitelisted
                or not found in PATH.
        """
        if not command or not command.strip():
            self.log_security_event(
                event_type="empty_command",
                details={"command": repr(command)},
            )
            raise CommandNotAllowedError("Empty command rejected")

        # Extract base command name
        first_token = command.strip().split()[0]
        cmd_name = os.path.basename(first_token)

        if cmd_name not in self._allowed_commands:
            self.log_security_event(
                event_type="command_not_whitelisted",
                details={"command": command, "cmd_name": cmd_name},
            )
            raise CommandNotAllowedError(
                f"Command '{cmd_name}' is not in the whitelist"
            )

        # Verify executable exists in PATH
        if shutil.which(cmd_name) is None:
            self.log_security_event(
                event_type="command_not_in_path",
                details={"command": command, "cmd_name": cmd_name},
            )
            raise CommandNotAllowedError(
                f"Command '{cmd_name}' not found in PATH"
            )

        return cmd_name

    # ------------------------------------------------------------------
    # Input Sanitization
    # ------------------------------------------------------------------

    def sanitize_input(self, text: Any, max_length: Optional[int] = None) -> str:
        """Sanitize input text by enforcing a maximum length limit.

        Args:
            text: The input text to sanitize. Will be converted to ``str``.
            max_length: Maximum allowed length in characters.
                Defaults to ``self._default_max_length``.

        Returns:
            The sanitized string (truncated if necessary).

        Raises:
            InputValidationError: If the input exceeds ``max_length``
                and truncation is not applied (when ``max_length`` is 0).
        """
        if max_length is None:
            max_length = self._default_max_length

        text_str = str(text) if not isinstance(text, str) else text

        if max_length == 0:
            self.log_security_event(
                event_type="input_length_exceeded",
                details={"input_length": len(text_str), "max_length": 0},
            )
            raise InputValidationError(
                f"Input length {len(text_str)} exceeds maximum 0"
            )

        if len(text_str) > max_length:
            self.log_security_event(
                event_type="input_truncated",
                details={"input_length": len(text_str), "max_length": max_length},
            )
            return text_str[:max_length]

        return text_str

    # ------------------------------------------------------------------
    # Security Event Logging
    # ------------------------------------------------------------------

    def log_security_event(
        self,
        event_type: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log a security-relevant event at WARNING level using stdlib logging.

        Args:
            event_type: Type of security event (e.g. ``"path_traversal_detected"``).
            details: Optional dictionary of additional context.
        """
        event_details = details or {}
        logger.warning(
            "security_event: type=%s details=%s",
            event_type,
            json.dumps(event_details),
        )

    @property
    def allowed_commands(self) -> Set[str]:
        """Set of allowed command base names."""
        return frozenset(self._allowed_commands)

    @property
    def default_max_length(self) -> int:
        """Default maximum input length."""
        return self._default_max_length


# ---------------------------------------------------------------------------
# Module-level convenience functions (use SecurityPolicy internally)
# ---------------------------------------------------------------------------

# Global policy instance
_default_policy: Optional[SecurityPolicy] = None


def _get_policy() -> SecurityPolicy:
    """Return the global SecurityPolicy instance (lazy-init)."""
    global _default_policy
    if _default_policy is None:
        _default_policy = SecurityPolicy()
    return _default_policy


def safe_path(base_dir: str, user_path: str) -> str:
    """Resolve a user-supplied path relative to a base directory and
    verify it stays within the base directory.

    Args:
        base_dir: The allowed base directory.
        user_path: The user-supplied path relative to base_dir.

    Returns:
        The resolved absolute path.

    Raises:
        PathTraversalError: If the resolved path escapes base_dir.
    """
    return _get_policy().safe_path(base_dir, user_path)


def safe_path_any(allowed_bases: list[str], user_path: str) -> str:
    """Check if a resolved path is within any of the allowed base directories.

    Args:
        allowed_bases: List of allowed base directories.
        user_path: An already-resolved absolute path to check.

    Returns:
        The resolved path if it is within any allowed base.

    Raises:
        PathTraversalError: If the path is outside all allowed bases.
    """
    return _get_policy().safe_path_any(allowed_bases, user_path)


def validate_command(command: str) -> str:
    """Validate that the base command is in the allowed whitelist.

    Args:
        command: The full command string.

    Returns:
        The validated base command name.

    Raises:
        CommandNotAllowedError: If the command is not whitelisted.
    """
    return _get_policy().validate_command(command)


def sanitize_input(text: Any, max_length: Optional[int] = None) -> str:
    """Sanitize input text by enforcing a maximum length limit.

    Args:
        text: The input text to sanitize.
        max_length: Maximum allowed length in characters.

    Returns:
        The sanitized string (truncated if necessary).

    Raises:
        InputValidationError: If the input exceeds max_length.
    """
    return _get_policy().sanitize_input(text, max_length)


def log_security_event(
    event_type: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Log a security-relevant event at WARNING level using stdlib logging.

    Args:
        event_type: Type of security event.
        details: Optional dictionary of additional context.
    """
    _get_policy().log_security_event(event_type, details)
