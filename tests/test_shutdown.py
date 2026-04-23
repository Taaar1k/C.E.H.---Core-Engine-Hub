"""Tests for the C.E.H. graceful shutdown module."""

import signal
import threading
import time
from unittest.mock import patch

import pytest

from c_e_h.shutdown import GracefulShutdown

# ---------------------------------------------------------------------------
# GracefulShutdown.__init__
# ---------------------------------------------------------------------------


def test_init_sets_shutdown_event() -> None:
    """Test that __init__ creates a non-set Event."""
    gs = GracefulShutdown()
    assert not gs.is_shutting_down


def test_init_stores_original_handlers() -> None:
    """Test that original signal handlers are captured."""
    gs = GracefulShutdown()
    # Original handlers should not be the same as our handler
    assert gs._original_sigint is not gs._handle_signal
    assert gs._original_sigterm is not gs._handle_signal


def test_init_accepts_custom_timeout() -> None:
    """Test that cleanup_timeout is stored correctly."""
    gs = GracefulShutdown(cleanup_timeout=5.0)
    assert gs._cleanup_timeout == 5.0


# ---------------------------------------------------------------------------
# GracefulShutdown.register
# ---------------------------------------------------------------------------


def test_register_raises_on_none_callback() -> None:
    """Test that register raises ValueError for None callback."""
    gs = GracefulShutdown()
    with pytest.raises(ValueError, match="cleanup_callback must not be None"):
        gs.register(None)  # type: ignore[arg-type]


def test_register_installs_signal_handlers() -> None:
    """Test that register installs signal handlers for SIGINT and SIGTERM."""
    gs = GracefulShutdown()
    gs.register(lambda: None)

    # Python wraps bound methods, so we check that the returned handler
    # is a callable that references our object's _handle_signal method.
    int_handler = signal.getsignal(signal.SIGINT)
    term_handler = signal.getsignal(signal.SIGTERM)
    assert callable(int_handler)
    assert callable(term_handler)
    # Both should be the same handler function
    assert int_handler.__func__ is GracefulShutdown._handle_signal
    assert term_handler.__func__ is GracefulShutdown._handle_signal


def test_register_clears_callback_on_unregister() -> None:
    """Test that unregister clears the callback."""
    gs = GracefulShutdown()
    gs.register(lambda: None)
    gs.unregister()

    assert gs._cleanup_callback is None


# ---------------------------------------------------------------------------
# GracefulShutdown.is_shutting_down
# ---------------------------------------------------------------------------


def test_is_shutting_down_false_by_default() -> None:
    """Test that is_shutting_down is False initially."""
    gs = GracefulShutdown()
    assert gs.is_shutting_down is False


def test_is_shutting_down_true_after_signal() -> None:
    """Test that is_shutting_down becomes True after signal handler runs."""
    gs = GracefulShutdown()
    gs.register(lambda: None)

    with patch("sys.exit"):
        gs._handle_signal(signal.SIGINT, None)

    assert gs.is_shutting_down is True


# ---------------------------------------------------------------------------
# GracefulShutdown.wait_for_shutdown
# ---------------------------------------------------------------------------


def test_wait_for_shutdown_returns_false_on_timeout() -> None:
    """Test that wait_for_shutdown returns False when no signal is received."""
    gs = GracefulShutdown()
    result = gs.wait_for_shutdown(timeout=0.1)
    assert result is False
    assert not gs.is_shutting_down


def test_wait_for_shutdown_returns_true_after_signal() -> None:
    """Test that wait_for_shutdown returns True after shutdown signal."""
    gs = GracefulShutdown()

    def _set_event() -> None:
        time.sleep(0.05)
        gs._shutdown_event.set()

    thread = threading.Thread(target=_set_event, daemon=True)
    thread.start()

    result = gs.wait_for_shutdown(timeout=2.0)
    thread.join(timeout=2.0)

    assert result is True
    assert gs.is_shutting_down


# ---------------------------------------------------------------------------
# GracefulShutdown._handle_signal — success path
# ---------------------------------------------------------------------------


def test_handle_signal_success_exits_zero() -> None:
    """Test that successful cleanup leads to sys.exit(0)."""
    cleanup_called = False

    def _cleanup() -> None:
        nonlocal cleanup_called
        cleanup_called = True

    gs = GracefulShutdown()
    gs.register(_cleanup)

    with patch("sys.exit") as mock_exit:
        gs._handle_signal(signal.SIGINT, None)

    assert cleanup_called is True
    mock_exit.assert_called_once_with(0)


def test_handle_signal_restores_original_handlers() -> None:
    """Test that original signal handlers are restored after cleanup."""
    gs = GracefulShutdown()
    gs.register(lambda: None)

    with patch("sys.exit"):
        gs._handle_signal(signal.SIGTERM, None)

    # Handlers should be restored
    assert signal.getsignal(signal.SIGINT) is gs._original_sigint
    assert signal.getsignal(signal.SIGTERM) is gs._original_sigterm


def test_handle_signal_sets_shutdown_event() -> None:
    """Test that shutdown event is set before cleanup."""
    event_state_during_cleanup: list[bool] = []

    def _cleanup() -> None:
        event_state_during_cleanup.append(gs.is_shutting_down)

    gs = GracefulShutdown()
    gs.register(_cleanup)

    with patch("sys.exit"):
        gs._handle_signal(signal.SIGINT, None)

    assert event_state_during_cleanup[0] is True


# ---------------------------------------------------------------------------
# GracefulShutdown._handle_signal — error path
# ---------------------------------------------------------------------------


def test_handle_signal_cleanup_exception_exits_one() -> None:
    """Test that cleanup exception leads to sys.exit(1)."""
    def _cleanup() -> None:
        raise RuntimeError("cleanup failed")

    gs = GracefulShutdown()
    gs.register(_cleanup)

    with patch("sys.exit") as mock_exit:
        gs._handle_signal(signal.SIGINT, None)

    mock_exit.assert_called_once_with(1)


def test_handle_signal_cleanup_timeout_exits_one() -> None:
    """Test that cleanup timeout leads to sys.exit(1)."""
    # Create a cleanup that blocks longer than the timeout
    def _cleanup() -> None:
        time.sleep(2.0)

    gs = GracefulShutdown(cleanup_timeout=0.1)
    gs.register(_cleanup)

    with patch("sys.exit") as mock_exit:
        gs._handle_signal(signal.SIGINT, None)

    mock_exit.assert_called_once_with(1)


# ---------------------------------------------------------------------------
# GracefulShutdown — integration with agent loop pattern
# ---------------------------------------------------------------------------


def test_agent_loop_pattern_checks_shutdown() -> None:
    """Test the typical agent loop pattern with shutdown check."""
    gs = GracefulShutdown()
    iterations = 0
    max_iterations = 5

    # Simulate agent loop
    while iterations < max_iterations and not gs.is_shutting_down:
        iterations += 1
        gs.wait_for_shutdown(timeout=0.05)

    # Loop should exit after max_iterations because no signal
    assert iterations == max_iterations
    assert not gs.is_shutting_down


def test_agent_loop_exits_on_signal() -> None:
    """Test that agent loop exits when shutdown signal is received."""
    gs = GracefulShutdown()
    gs.register(lambda: None)

    # Trigger signal in a separate thread
    def _trigger() -> None:
        time.sleep(0.05)
        with patch("sys.exit"):
            gs._handle_signal(signal.SIGINT, None)

    thread = threading.Thread(target=_trigger, daemon=True)
    thread.start()

    iterations = 0
    while iterations < 100 and not gs.is_shutting_down:
        iterations += 1
        gs.wait_for_shutdown(timeout=0.1)

    thread.join(timeout=2.0)
    assert gs.is_shutting_down


# ---------------------------------------------------------------------------
# GracefulShutdown — multiple signal handling
# ---------------------------------------------------------------------------


def test_sigint_and_sigterm_both_registered() -> None:
    """Test that both SIGINT and SIGTERM handlers point to _handle_signal."""
    gs = GracefulShutdown()
    gs.register(lambda: None)

    int_handler = signal.getsignal(signal.SIGINT)
    term_handler = signal.getsignal(signal.SIGTERM)

    assert int_handler.__func__ is GracefulShutdown._handle_signal
    assert term_handler.__func__ is GracefulShutdown._handle_signal


# ---------------------------------------------------------------------------
# GracefulShutdown — callback stored correctly
# ---------------------------------------------------------------------------


def test_callback_stored_correctly() -> None:
    """Test that the callback is stored and retrieved correctly."""
    def my_cleanup() -> None:
        pass

    gs = GracefulShutdown()
    gs.register(my_cleanup)

    assert gs._cleanup_callback is my_cleanup


# ---------------------------------------------------------------------------
# GracefulShutdown — no callback runs cleanup directly
# ---------------------------------------------------------------------------


def test_handle_signal_no_callback_exits_zero() -> None:
    """Test that signal with no callback still exits successfully."""
    gs = GracefulShutdown()
    # Don't register any callback

    with patch("sys.exit") as mock_exit:
        gs._handle_signal(signal.SIGINT, None)

    mock_exit.assert_called_once_with(0)


# ---------------------------------------------------------------------------
# GracefulShutdown — concurrent registration (main thread only)
# ---------------------------------------------------------------------------


def test_register_thread_safety_skipped_in_test() -> None:
    """Test that signal registration is skipped in non-main threads.

    signal.signal() only works in the main thread, so we verify that
    concurrent registration raises ValueError as expected.
    """
    gs = GracefulShutdown()
    errors: list[Exception] = []

    def _register_many() -> None:
        try:
            for _ in range(10):
                gs.register(lambda: None)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_register_many) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # signal.signal() raises ValueError in non-main threads, which is expected
    # The important thing is that no crash occurs
    assert len(errors) > 0  # Expected: signal only works in main thread
