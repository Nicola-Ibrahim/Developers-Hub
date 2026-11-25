"""Process-local rate and concurrency limits for the login endpoint."""

from collections import OrderedDict, deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from threading import Lock
from time import monotonic


class LoginRequestRateLimiter:
    """Limit aggregate login traffic per direct peer without trusting proxy headers."""

    def __init__(
        self,
        *,
        max_requests: int = 300,
        window_seconds: float = 60.0,
        max_peers: int = 4096,
        max_concurrent: int = 4,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if max_requests < 1 or window_seconds <= 0 or max_peers < 1 or max_concurrent < 1:
            raise ValueError("Invalid login rate limit configuration")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_peers = max_peers
        self.max_concurrent = max_concurrent
        self._clock = clock
        self._attempts: OrderedDict[str, deque[float]] = OrderedDict()
        self._active = 0
        self._lock = Lock()

    @contextmanager
    def admit(self, peer: str | None) -> Iterator[bool]:
        admitted = self._acquire(peer)
        try:
            yield admitted
        finally:
            if admitted:
                with self._lock:
                    self._active -= 1

    def _acquire(self, peer: str | None) -> bool:
        key = peer or "unknown-peer"
        with self._lock:
            if self._active >= self.max_concurrent:
                return False
            now = self._clock()
            cutoff = now - self.window_seconds
            while self._attempts:
                oldest_key, oldest_attempts = next(iter(self._attempts.items()))
                if oldest_attempts[-1] > cutoff:
                    break
                del self._attempts[oldest_key]
            attempts = self._attempts.get(key)
            if attempts is None:
                if len(self._attempts) >= self.max_peers:
                    return False
                attempts = deque()
                self._attempts[key] = attempts
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if len(attempts) >= self.max_requests:
                return False
            attempts.append(now)
            self._attempts.move_to_end(key)
            self._active += 1
            return True


login_request_rate_limiter = LoginRequestRateLimiter()
