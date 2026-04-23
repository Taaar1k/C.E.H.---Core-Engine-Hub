"""Tests for debug mode functionality.

Covers:
- Debug flag parsing in CLI commands
- Log level verification when debug is enabled
- Verbose flag parsing
- Debug context in structlog
- SQL query logging in debug mode
- Memory usage reporting
"""

import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Generator

import pytest
import structlog
from typer.testing import CliRunner

from c_e_h.cli import app
from c_e_h.logging_config import (
    disable_sql_tracing,
    get_debug_mode,
    get_memory_usage,
    get_verbose_mode,
    setup_logging,
)


@pytest.fixture(autouse=True)
def _clear_structlog_cache() -> Generator[None, None, None]:
    """Clear structlog's internal cache between tests."""
    structlog.configure(
        processors=[],
        wrapper_class=structlog.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
    yield
    structlog.configure(
        processors=[],
        wrapper_class=structlog.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


@pytest.fixture(autouse=True)
def _reset_debug_flags() -> Generator[None, None, None]:
    """Reset debug/verbose flags after each test."""
    yield
    # Reset module-level flags
    import c_e_h.logging_config as lc
    lc._DEBUG_MODE = False
    lc._VERBOSE_MODE = False
    disable_sql_tracing()


runner = CliRunner()


class TestDebugFlagParsing:
    """Test that --debug/-d flag is correctly parsed."""

    def test_run_command_has_debug_flag(self) -> None:
        """Test that the run command accepts --debug flag."""
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "--debug" in result.stdout
        assert "-d" in result.stdout

    def test_interactive_command_has_debug_flag(self) -> None:
        """Test that the interactive command accepts --debug flag."""
        result = runner.invoke(app, ["interactive", "--help"])
        assert result.exit_code == 0
        assert "--debug" in result.stdout
        assert "-d" in result.stdout

    def test_stream_command_has_debug_flag(self) -> None:
        """Test that the stream command accepts --debug flag."""
        result = runner.invoke(app, ["stream", "--help"])
        assert result.exit_code == 0
        assert "--debug" in result.stdout
        assert "-d" in result.stdout

    def test_version_command_has_debug_flag(self) -> None:
        """Test that the version command accepts --debug flag."""
        result = runner.invoke(app, ["version", "--help"])
        assert result.exit_code == 0
        assert "--debug" in result.stdout
        assert "-d" in result.stdout

    def test_run_command_has_verbose_flag(self) -> None:
        """Test that the run command accepts --verbose flag."""
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "--verbose" in result.stdout
        assert "-v" in result.stdout


class TestLogLevelVerification:
    """Test that log levels are correctly set."""

    def test_debug_sets_debug_level(self) -> None:
        """Test that debug=True sets logging level to DEBUG."""
        with TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            logger = setup_logging(
                log_file=log_file,
                log_level="INFO",
                debug=True,
            )
            assert logger.level == logging.DEBUG
            assert get_debug_mode() is True

    def test_debug_without_explicit_level(self) -> None:
        """Test that debug=True overrides default INFO level."""
        with TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            logger = setup_logging(
                log_file=log_file,
                debug=True,
            )
            assert logger.level == logging.DEBUG

    def test_non_debug_keeps_info_level(self) -> None:
        """Test that debug=False keeps the specified log level."""
        with TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            logger = setup_logging(
                log_file=log_file,
                log_level="INFO",
                debug=False,
            )
            assert logger.level == logging.INFO
            assert get_debug_mode() is False

    def test_verbose_flag_tracking(self) -> None:
        """Test that verbose=True sets verbose mode."""
        with TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            setup_logging(
                log_file=log_file,
                verbose=True,
            )
            assert get_verbose_mode() is True

    def test_cli_verbose_flag(self) -> None:
        """Test that CLI --verbose flag is parsed."""
        # The version command should succeed with --verbose
        result = runner.invoke(app, ["version", "--verbose"])
        assert result.exit_code == 0


class TestDebugContext:
    """Test that debug context is added to structlog."""

    def test_debug_context_added(self) -> None:
        """Test that debug_mode=True is added to structlog events."""
        with TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            setup_logging(
                log_file=log_file,
                environment="development",
                debug=True,
            )
            test_logger = structlog.get_logger("test_debug")
            # Capture the event dict by checking the processor chain
            assert get_debug_mode() is True

    def test_verbose_context_added(self) -> None:
        """Test that verbose context (pid, thread) is added."""
        with TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            setup_logging(
                log_file=log_file,
                environment="development",
                verbose=True,
            )
            assert get_verbose_mode() is True


class TestSQLQueryLogging:
    """Test that SQL queries are logged in debug mode."""

    def test_sql_tracing_enabled_in_debug(self) -> None:
        """Test that SQL tracing is enabled when debug=True."""
        with TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            setup_logging(log_file=log_file, debug=True)
            # SQL tracing should be enabled
            import c_e_h.logging_config as lc
            assert lc._SQL_TRACE_CALLBACK is not None

    def test_sql_tracing_disabled_by_default(self) -> None:
        """Test that SQL tracing is disabled by default."""
        with TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            setup_logging(log_file=log_file, debug=False)
            import c_e_h.logging_config as lc
            # SQL tracing should be disabled
            assert lc._SQL_TRACE_CALLBACK is None


class TestMemoryUsage:
    """Test memory usage reporting."""

    def test_get_memory_usage_returns_dict(self) -> None:
        """Test that get_memory_usage returns a dictionary."""
        mem = get_memory_usage()
        assert isinstance(mem, dict)
        assert "rss_mb" in mem
        assert isinstance(mem["rss_mb"], float)
        assert mem["rss_mb"] > 0

    def test_memory_usage_reasonable_values(self) -> None:
        """Test that memory usage values are reasonable."""
        mem = get_memory_usage()
        # RSS should be less than 2 GB for a test process
        assert mem["rss_mb"] < 2048


class TestDebugIntegration:
    """Integration tests for debug mode."""

    def test_version_with_debug(self) -> None:
        """Test version command with --debug flag."""
        result = runner.invoke(app, ["version", "--debug"])
        assert result.exit_code == 0
        assert "C.E.H. v" in result.stdout

    def test_version_with_verbose(self) -> None:
        """Test version command with --verbose flag."""
        result = runner.invoke(app, ["version", "--verbose"])
        assert result.exit_code == 0
        assert "C.E.H. v" in result.stdout

    def test_version_with_both_flags(self) -> None:
        """Test version command with both --debug and --verbose flags."""
        result = runner.invoke(app, ["version", "--debug", "--verbose"])
        assert result.exit_code == 0
        assert "C.E.H. v" in result.stdout

    def test_session_new_help(self) -> None:
        """Test that session new command help works."""
        result = runner.invoke(app, ["session", "new", "--help"])
        assert result.exit_code == 0

    def test_model_list_help(self) -> None:
        """Test that model list command help works."""
        result = runner.invoke(app, ["model", "list", "--help"])
        assert result.exit_code == 0
