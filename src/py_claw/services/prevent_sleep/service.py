"""
PreventSleep service - macOS caffeinate-based sleep prevention.

Uses the built-in `caffeinate` command to create a power assertion
that prevents idle sleep during long-running operations.

Only runs on macOS (darwin). No-op on other platforms.
"""
from __future__ import annotations

import atexit
import logging
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Caffeinate timeout in seconds - auto-exits after this duration.
# We restart it before expiry to maintain continuous sleep prevention.
CAFFEINATE_TIMEOUT_SECONDS = 300  # 5 minutes

# Restart interval - restart caffeinate before it expires (4 minutes).
RESTART_INTERVAL_MS = 4 * 60 * 1000

# Cleanup registry for SIGKILL handling
_cleanup_registry: list[callable] = []


@dataclass
class PreventSleepConfig:
    """Configuration for prevent sleep service."""

    #: Timeout for caffeinate process in seconds.
    timeout_seconds: int = CAFFEINATE_TIMEOUT_SECONDS

    #: How often to restart caffeinate in milliseconds.
    restart_interval_ms: int = RESTART_INTERVAL_MS

    #: Whether to allow the process to keep the Python process alive.
    unref_process: bool = True


class PreventSleepService:
    """Manages macOS caffeinate process to prevent idle sleep.

    Uses reference counting to allow nested calls to enable/disable.
    Caffeinate is restarted periodically before the timeout expires.
    """

    def __init__(self, config: PreventSleepConfig | None = None) -> None:
        self._config = config or PreventSleepConfig()
        self._caffeinate_process: subprocess.Popen[bytes] | None = None
        self._restart_interval: threading.Timer | None = None
        self._ref_count = 0
        self._lock = threading.Lock()
        self._atexit_registered = False

    def enable(self) -> None:
        """Increment ref count and start preventing sleep if first caller."""
        with self._lock:
            self._ref_count += 1
            if self._ref_count == 1:
                self._spawn_caffeinate()
                self._start_restart_interval()

    def disable(self) -> None:
        """Decrement ref count and stop preventing sleep if no more callers."""
        with self._lock:
            if self._ref_count > 0:
                self._ref_count -= 1
            if self._ref_count == 0:
                self._stop_restart_interval()
                self._kill_caffeinate()

    def force_stop(self) -> None:
        """Force stop preventing sleep regardless of ref count."""
        with self._lock:
            self._ref_count = 0
            self._stop_restart_interval()
            self._kill_caffeinate()

    @property
    def is_preventing_sleep(self) -> bool:
        """Whether sleep prevention is currently active."""
        with self._lock:
            return self._ref_count > 0 and self._caffeinate_process is not None

    def _is_darwin(self) -> bool:
        """Check if running on macOS."""
        return os.name == "posix" and os.uname().sysname == "Darwin"

    def _start_restart_interval(self) -> None:
        """Start periodic restart timer for caffeinate."""
        if not self._is_darwin():
            return
        if self._restart_interval is not None:
            return

        self._register_atexit()

        interval_seconds = self._config.restart_interval_ms / 1000

        def restart_loop() -> None:
            with self._lock:
                if self._ref_count > 0:
                    logger.debug("Restarting caffeinate to maintain sleep prevention")
                    self._kill_caffeinate()
                    self._spawn_caffeinate()
                    # Schedule next restart
                    self._restart_interval = threading.Timer(
                        interval_seconds, restart_loop
                    )
                    self._restart_interval.daemon = True
                    self._restart_interval.start()
                else:
                    self._restart_interval = None

        self._restart_interval = threading.Timer(interval_seconds, restart_loop)
        self._restart_interval.daemon = True
        self._restart_interval.start()

    def _stop_restart_interval(self) -> None:
        """Stop the restart timer."""
        if self._restart_interval is not None:
            self._restart_interval.cancel()
            self._restart_interval = None

    def _register_atexit(self) -> None:
        """Register cleanup handler on first use."""
        if not self._atexit_registered:
            self._atexit_registered = True
            atexit.register(self.force_stop)

    def _spawn_caffeinate(self) -> None:
        """Spawn the caffeinate process."""
        if not self._is_darwin():
            return
        if self._caffeinate_process is not None:
            return

        self._register_atexit()

        try:
            # -i: prevent idle sleep (display can still sleep)
            # -t: timeout in seconds (self-healing if process is killed)
            self._caffeinate_process = subprocess.Popen(
                ["caffeinate", "-i", "-t", str(self._config.timeout_seconds)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

            if self._config.unref_process:
                self._caffeinate_process.poll()

            logger.debug("Started caffeinate to prevent sleep")
        except FileNotFoundError:
            logger.debug("caffeinate not found - sleep prevention unavailable")
            self._caffeinate_process = None
        except OSError as e:
            logger.debug(f"Failed to spawn caffeinate: {e}")
            self._caffeinate_process = None

    def _kill_caffeinate(self) -> None:
        """Kill the caffeinate process."""
        if self._caffeinate_process is not None:
            proc = self._caffeinate_process
            self._caffeinate_process = None
            try:
                # SIGKILL for immediate termination
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait(timeout=2)
                logger.debug("Stopped caffeinate, allowing sleep")
            except (ProcessLookupError, subprocess.TimeoutExpired):
                pass
            except OSError:
                pass


# Global singleton instance
_service: PreventSleepService | None = None
_init_lock = threading.Lock()


def get_prevent_sleep_service() -> PreventSleepService:
    """Get the global PreventSleepService singleton."""
    global _service
    if _service is None:
        with _init_lock:
            if _service is None:
                _service = PreventSleepService()
    return _service


def start_prevent_sleep() -> None:
    """Enable sleep prevention (reference counted)."""
    get_prevent_sleep_service().enable()


def stop_prevent_sleep() -> None:
    """Disable sleep prevention (reference counted)."""
    get_prevent_sleep_service().disable()


def force_stop_prevent_sleep() -> None:
    """Force stop sleep prevention regardless of ref count."""
    get_prevent_sleep_service().force_stop()


# Cleanup registry functions for SIGKILL handling
def register_cleanup(func: callable) -> None:
    """Register a cleanup function to be called on exit.

    Cleanup functions are called in reverse order when the process exits.
    This is used to ensure caffeinate processes are killed even if the
    Python process is terminated with SIGKILL.

    Args:
        func: Function to call on cleanup
    """
    if func not in _cleanup_registry:
        _cleanup_registry.append(func)


def unregister_cleanup(func: callable) -> None:
    """Unregister a cleanup function.

    Args:
        func: Function to remove from cleanup registry
    """
    if func in _cleanup_registry:
        _cleanup_registry.remove(func)


def _run_cleanup_registry() -> None:
    """Run all registered cleanup functions."""
    for func in reversed(_cleanup_registry):
        try:
            func()
        except Exception:
            pass  # Best effort cleanup


def _register_cleanup_atexit() -> None:
    """Register the cleanup registry to run at exit."""
    atexit.register(_run_cleanup_registry)
