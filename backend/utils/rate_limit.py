import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.time()
        request_times = self._requests[key]

        while request_times and request_times[0] <= now - self.window_seconds:
            request_times.popleft()

        if len(request_times) >= self.max_requests:
            return False

        request_times.append(now)
        return True
