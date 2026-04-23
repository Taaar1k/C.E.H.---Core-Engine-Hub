"""Graceful shutdown handling for C.E.H.

Provides the ``GracefulShutdown`` class for registering signal handlers
(SIGINT / SIGTERM), executing a cleanup sequence, and signalling the
main agent loop that a shutdown is in progress.
"""

from __future__ import annotations

import logging
import signal
import sys
import threading
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ShutdownError(Exception):
    """Raised when cleanup fails during graceful shutdown."""


# ---------------------------------------------------------------------------
# GracefulShutdown
# ---------------------------------------------------------------------------


class GracefulShutdown:
    """Manages graceful shutdown for the C.E.H. agent.

    Registers signal handlers for ``SIGINT`` and ``SIGTERM``, provides a
    ``threading.Event``-based shutdown flag, and executes a configurable
    cleanup sequence before exiting.

    Attributes:
        cleanup_timeout: Maximum seconds allowed for the full cleanup
            sequence.  Defaults to **10**.

    Example::

        shutdown = GracefulShutdown()

        def _cleanup() -> None:
            session_manager.save()
            llama_backend.close()

        shutdown.register(_cleanup)

        while not shutdown.is_shutting_down:
            # … agent loop …
            shutdown.wait_for_shutdown(timeout=1)
    """

    def __init__(self, cleanup_timeout: float = 10.0) -> None:
        """Initialise the shutdown manager.

        Args:
            cleanup_timeout: Seconds to wait for cleanup to complete.
        """
        self._shutdown_event: threading.Event = threading.Event()
        self._cleanup_callback: Optional[Callable[[], None]] = None
        self._original_sigint: Callable[[int, Any], Any] = signal.getsignal(signal.SIGINT)
        self._original_sigterm: Callable[[int, Any], Any] = signal.getsignal(signal.SIGTERM)
        self._cleanup_timeout = cleanup_timeout
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_shutting_down(self) -> bool:
        """Return ``True`` if a shutdown signal has been received."""
        return self._shutdown_event.is_set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, cleanup_callback: Callable[[], None]) -> None:
        """Register a cleanup function and install signal handlers.

        Args:
            cleanup_callback: A zero-argument callable that performs
                all necessary resource cleanup (save session, close LLM,
                close DB, release locks).

        Raises:
            ValueError: If *cleanup_callback* is ``None``.
        """
        if cleanup_callback is None:
            raise ValueError("cleanup_callback must not be None")

        with self._lock:
            self._cleanup_callback = cleanup_callback

        # Install signal handlers
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        logger.info("GracefulShutdown registered cleanup_timeout=%s", self._cleanup_timeout)

    def unregister(self) -> None:
        """Restore original signal handlers and clear the callback."""
        with self._lock:
            self._cleanup_callback = None

        signal.signal(signal.SIGINT, self._original_sigint)
        signal.signal(signal.SIGTERM, self._original_sigterm)

        logger.info("GracefulShutdown unregistered")

    def wait_for_shutdown(self, timeout: float = 30.0) -> bool:
        """Block until a shutdown signal is received or *timeout* elapses.

        Args:
            timeout: Maximum seconds to wait.  Defaults to **30**.

        Returns:
            ``True`` if a shutdown signal was received, ``False`` on
            timeout.
        """
        return self._shutdown_event.wait(timeout=timeout)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _handle_signal(self, signum: int, frame: Any) -> None:
        """Signal handler: set shutdown event, run cleanup, exit.

        Args:
            signum: The signal number received.
            frame: The current stack frame (or ``None``).
        """
        signal_name = signal.Signals(signum).name
        logger.info("Shutdown signal received signum=%d signal_name=%s", signum, signal_name)

        # Set the shutdown event so the agent loop can check it
        self._shutdown_event.set()

        # Run the cleanup sequence
        cleanup_success = True
        with self._lock:
            callback = self._cleanup_callback

        if callback is not None:
            try:
                # Run cleanup with timeout using a thread
                cleanup_exception: Optional[Exception] = None
                result_container: list[Optional[Exception]] = []

                def _run_cleanup() -> None:
                    try:
                        callback()
                    except Exception as exc:
                        result_container.append(exc)

                cleanup_thread = threading.Thread(target=_run_cleanup, daemon=True)
                cleanup_thread.start()
                cleanup_thread.join(timeout=self._cleanup_timeout)

                if cleanup_thread.is_alive():
                    logger.error("Cleanup timed out timeout=%s", self._cleanup_timeout)
                    cleanup_success = False
                elif result_container:
                    cleanup_exception = result_container[0]
                    logger.error(
                        "Cleanup raised exception",
                        exc_info=(
                            type(cleanup_exception),
                            cleanup_exception,
                            cleanup_exception.__traceback__,
                        ),
                    )
                    cleanup_success = False

            except Exception:
                logger.error("Cleanup wrapper failed", exc_info=sys.exc_info())
                cleanup_success = False

        # Restore default signal handlers (always, even on error)
        signal.signal(signal.SIGINT, self._original_sigint)
        signal.signal(signal.SIGTERM, self._original_sigterm)

        # Exit
        if cleanup_success:
            logger.info("Cleanup completed successfully")
            sys.exit(0)
        else:
            logger.error("Cleanup failed, exiting with error")
            sys.exit(1)
