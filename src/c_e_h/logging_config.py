"""Logging configuration for C.E.H.

Provides ``setup_logging()`` with size-based rotation (RotatingFileHandler),
optional time-based rotation (TimedRotatingFileHandler), and stdlib
logging for structured logging.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from logging import Logger
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

LOG_DIR: Path = Path.home() / ".ceh" / "logs"
LOG_FILE: Path = LOG_DIR / "ceh.log"
MAX_BYTES: int = 10 * 1024 * 1024  # 10 MB
BACKUP_COUNT: int = 5
LOG_LEVEL_DEFAULT: str = "INFO"
LOG_LEVELS: tuple[str, ...] = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

FILE_LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
CONSOLE_LOG_FORMAT: str = "%(levelname)s: %(message)s"

# Global flags for debug mode
_DEBUG_MODE: bool = False
_VERBOSE_MODE: bool = False

# Module-level state for SQL trace callback
_SQL_TRACE_CALLBACK: Optional[Any] = None


def setup_logging(
    log_level: str = LOG_LEVEL_DEFAULT,
    log_file: Optional[Path] = None,
    enable_timed_rotation: bool = False,
    environment: str = "production",
    debug: bool = False,
    verbose: bool = False,
) -> Logger:
    """Configure logging for C.E.H.

    Sets up:
    - A **RotatingFileHandler** writing to ``~/.ceh/logs/ceh.log`` with
      ``maxBytes=10*1024*1024`` (10 MB) and ``backupCount=5``.
    - An optional **TimedRotatingFileHandler** for daily rotation.
    - A **ConsoleHandler** with a human-readable format.

    Args:
        log_level: Logging verbosity level. One of DEBUG, INFO, WARNING,
            ERROR, CRITICAL. Defaults to ``INFO``.
        log_file: Override the default log file path. Defaults to
            ``~/.ceh/logs/ceh.log``.
        enable_timed_rotation: When ``True``, also attach a
            TimedRotatingFileHandler for daily rotation at midnight.
        environment: Either ``"production"`` or ``"development"``.
            (Currently unused; kept for API compatibility.)
        debug: When ``True``, enable debug mode (DEBUG log level, SQL tracing,
            memory reporting).
        verbose: When ``True``, enable verbose output in addition to debug.

    Returns:
        The root logger configured for the application.

    Raises:
        ValueError: If *log_level* is not a recognised level.
    """
    global _DEBUG_MODE, _VERBOSE_MODE
    _DEBUG_MODE = debug
    _VERBOSE_MODE = verbose
    # --- Override log level to DEBUG when debug mode is enabled ------------
    if debug:
        log_level_upper: str = "DEBUG"
    else:
        log_level_upper = log_level.upper()
    if log_level_upper not in LOG_LEVELS:
        raise ValueError(
            f"Invalid log level: {log_level!r}. Must be one of {LOG_LEVELS}"
        )

    # --- Resolve paths -----------------------------------------------------
    log_file_path = log_file or LOG_FILE
    log_dir = log_file_path.parent
    log_dir.mkdir(parents=True, exist_ok=True)

    # --- Root logger -------------------------------------------------------
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level_upper))

    # Remove any existing handlers to avoid duplicates on repeated calls.
    root_logger.handlers.clear()

    # --- File handler (RotatingFileHandler) --------------------------------
    file_handler = logging.handlers.RotatingFileHandler(
        filename=str(log_file_path),
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(getattr(logging, log_level_upper))
    file_formatter = logging.Formatter(FILE_LOG_FORMAT)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # --- Optional TimedRotatingFileHandler ---------------------------------
    if enable_timed_rotation:
        timed_handler = logging.handlers.TimedRotatingFileHandler(
            filename=str(log_file_path.with_suffix(".daily.log")),
            when="midnight",
            interval=1,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        timed_handler.setLevel(getattr(logging, log_level_upper))
        timed_handler.setFormatter(file_formatter)
        timed_handler.suffix = "%Y-%m-%d"
        root_logger.addHandler(timed_handler)

    # --- Console handler ---------------------------------------------------
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level_upper))
    console_formatter = logging.Formatter(CONSOLE_LOG_FORMAT)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # --- Enable SQL query tracing in debug mode ----------------------------
    if debug:
        _enable_sql_tracing()

    return root_logger


def get_debug_mode() -> bool:
    """Return whether debug mode is currently enabled.

    Returns:
        ``True`` if debug mode is enabled, ``False`` otherwise.
    """
    return _DEBUG_MODE


def get_verbose_mode() -> bool:
    """Return whether verbose mode is currently enabled.

    Returns:
        ``True`` if verbose mode is enabled, ``False`` otherwise.
    """
    return _VERBOSE_MODE


def _enable_sql_tracing() -> None:
    """Enable SQLite query tracing via trace function.

    When debug mode is enabled, this registers a trace function with the
    default sqlite3 connection that logs all SQL queries to the root logger.
    """
    import sqlite3 as _sqlite3

    _logger = logging.getLogger(__name__)

    def _trace_callback(query: str) -> None:
        """Trace callback for SQLite queries.

        Args:
            query: The SQL query string being executed.
        """
        _logger.debug("SQL query: %s", query)

    _sqlite3.enable_callback_tracebacks(True)
    # Store the trace function on the module for later removal
    global _SQL_TRACE_CALLBACK
    _SQL_TRACE_CALLBACK = _trace_callback


def get_logger(name: str) -> logging.Logger:
    """Return a stdlib logger for the given *name*.

    Args:
        name: Logger name (typically ``__name__``).

    Returns:
        A stdlib Logger instance.
    """
    return logging.getLogger(name)


def disable_sql_tracing() -> None:
    """Disable SQLite query tracing.

    Removes the trace function from sqlite3 connections.
    """
    global _SQL_TRACE_CALLBACK
    import sqlite3 as _sqlite3

    _sqlite3.enable_callback_tracebacks(False)
    _SQL_TRACE_CALLBACK = None


def get_memory_usage() -> dict[str, float]:
    """Get current memory usage information.

    Uses the ``resource`` module on Unix-like systems. Falls back to
    reading ``/proc/self/status`` on Linux if available.

    Returns:
        Dictionary with ``rss_mb`` (resident set size in MB) and
        ``vms_mb`` (virtual memory size in MB) keys.
    """
    import resource as _resource  # Unix-only

    usage = _resource.getrusage(_resource.RUSAGE_SELF)
    # ru_maxrss is in KB on Linux, in bytes on macOS
    if sys.platform == "darwin":
        rss_kb = usage.ru_maxrss
    else:
        rss_kb = usage.ru_maxrss

    return {
        "rss_mb": round(rss_kb / 1024, 2),
        "vms_mb": round(usage.ru_ixrss / 1024, 2) if sys.platform == "darwin" else 0.0,
    }
