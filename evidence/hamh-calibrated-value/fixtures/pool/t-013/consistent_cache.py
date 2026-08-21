"""TTL cache with capacity (task fixture t-013)."""

import copy


class TtlCache:
    def __init__(self, capacity: int, ttl_seconds: float, now):
        self.capacity = capacity
        self.ttl = ttl_seconds
        self._now = now
        self._store = {}  # key -> (expires_at, value)

    def _expire(self, key):
        entry = self._store.get(key)
        if entry and entry[0] < self._now():
            del self._store[key]

    def set(self, key, value):
        expires = self._now() + self.ttl
        if key in self._store:
            self._store[key] = (expires, value)
            return
        if len(self._store) >= self.capacity:
            return  # full: silently drop (BUG)
        self._store[key] = (expires, value)

    def get(self, key):
        self._expire(key)
        entry = self._store.get(key)
        if entry is None:
            return None
        return copy.deepcopy(entry[1])
