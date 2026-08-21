"""Session manager with sequence contract (task fixture t-015)."""


class SessionError(Exception):
    pass


class SessionManager:
    def __init__(self):
        self._active = False
        self._count = 0

    def connect(self):
        if self._active:
            raise SessionError("already connected")
        self._active = True
        self._count = 0

    def request(self, payload) -> int:
        self._count += 1
        return self._count

    def close(self) -> bool:
        if not self._active:
            return False
        self._active = False
        self._count = 0
        return True
