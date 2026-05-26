"""
Exponential backoff decorator — stub for Phase 1.
Phase 2 (Gmail) will implement actual retry logic for 429 and 500 responses.
"""
import functools
import time
import logging

logger = logging.getLogger(__name__)


def with_retry(max_attempts: int = 3, base_delay: float = 1.0):
    """Decorator: retry on exception with exponential backoff. Stub in Phase 1."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            # Phase 1: no retries needed (mock source never fails)
            return fn(*args, **kwargs)
        return wrapper
    return decorator
