"""Token bucket rate limiter (task fixture t-005)."""


class TokenBucket:
    def __init__(self, rate: float, capacity: float, now):
        """rate: tokens per second; capacity: max tokens; now: clock fn."""
        self.rate = rate
        self.capacity = capacity
        self._now = now
        self._tokens = capacity
        self._last = now()

    def _refill(self):
        elapsed = self._now() - self._last
        self._tokens += int(elapsed) * self.rate
        self._last = self._now()

    def consume(self, n: int) -> bool:
        """Consume n tokens; True if allowed, False otherwise."""
        self._refill()
        if self._tokens >= n:
            self._tokens -= n
            return True
        return False
