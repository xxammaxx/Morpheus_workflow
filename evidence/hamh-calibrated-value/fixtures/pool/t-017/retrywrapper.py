"""Retry wrapper (task fixture t-017)."""


def execute_with_retry(fn, max_retries: int, retry_on):
    """Call fn; retry up to max_retries times on retry_on exceptions."""
    attempt = 0
    last_exc = None
    while attempt < max_retries:
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if not any(isinstance(exc, cls) for cls in retry_on):
                raise
            attempt += 1
    raise last_exc
