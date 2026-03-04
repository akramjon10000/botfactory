import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple


class InMemoryRateLimiter:
    """Simple per-process sliding-window rate limiter."""

    def __init__(self) -> None:
        self._events: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def is_allowed(self, key: str, limit: int, window_seconds: int) -> Tuple[bool, int]:
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            queue = self._events[key]

            while queue and queue[0] <= cutoff:
                queue.popleft()

            if len(queue) >= limit:
                retry_after = max(1, int(window_seconds - (now - queue[0])))
                return False, retry_after

            queue.append(now)
            return True, 0


def get_client_ip(req) -> str:
    forwarded_for = (req.headers.get("X-Forwarded-For") or "").strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = (req.headers.get("X-Real-IP") or "").strip()
    if real_ip:
        return real_ip

    return req.remote_addr or "unknown"


rate_limiter = InMemoryRateLimiter()

