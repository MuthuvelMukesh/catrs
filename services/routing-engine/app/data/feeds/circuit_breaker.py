"""Thread-safe Circuit Breaker pattern for external ingestion feeds."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import threading
import time


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(RuntimeError):
    """Raised when an external request is rejected by an open circuit breaker."""
    pass


class CircuitBreaker:
    """Stateful circuit breaker protecting external service integrations from cascading failures."""

    def __init__(
        self,
        name: str = "feed_breaker",
        failure_threshold: int = 3,
        recovery_timeout_s: float = 30.0,
        half_open_max_trials: int = 1,
    ) -> None:
        self.name = name
        self.failure_threshold = max(1, failure_threshold)
        self.recovery_timeout_s = max(0.01, recovery_timeout_s)
        self.half_open_max_trials = max(1, half_open_max_trials)

        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._last_failure_time: float | None = None
        self._half_open_trials = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._check_state_transition()
            return self._state

    def _check_state_transition(self) -> None:
        if self._state == CircuitState.OPEN and self._last_failure_time is not None:
            if time.monotonic() - self._last_failure_time >= self.recovery_timeout_s:
                self._state = CircuitState.HALF_OPEN
                self._half_open_trials = 0

    def can_execute(self) -> bool:
        """Check whether an outbound request is permitted."""
        with self._lock:
            self._check_state_transition()
            if self._state == CircuitState.CLOSED:
                return True
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_trials < self.half_open_max_trials:
                    self._half_open_trials += 1
                    return True
                return False
            return False

    def record_success(self) -> None:
        """Record successful invocation, closing or maintaining closed state."""
        with self._lock:
            self._consecutive_failures = 0
            self._state = CircuitState.CLOSED
            self._half_open_trials = 0

    def record_failure(self) -> None:
        """Record failed invocation, tripping to OPEN if threshold reached."""
        with self._lock:
            self._consecutive_failures += 1
            self._last_failure_time = time.monotonic()
            if self._state == CircuitState.HALF_OPEN or self._consecutive_failures >= self.failure_threshold:
                self._state = CircuitState.OPEN

    def reset(self) -> None:
        """Reset breaker back to initial CLOSED state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._last_failure_time = None
            self._half_open_trials = 0
