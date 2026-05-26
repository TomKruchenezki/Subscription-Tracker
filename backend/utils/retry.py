"""
Exponential backoff decorator for Gmail API calls.

Retries on transient HTTP errors (429 rate-limit, 500/503 server errors).
Non-retryable errors (400 Bad Request, 401 Unauthorized, 403 Forbidden) are
re-raised immediately — they indicate a configuration or auth problem that
requires user intervention, not a transient failure.

Usage:
    from backend.utils.retry import with_retry

    @with_retry()
    def call_gmail_api():
        return service.users().messages().list(...).execute()
"""
import functools
import logging
import time

logger = logging.getLogger(__name__)

# Backoff schedule in seconds: [1, 2, 4, 8, 16, 32, 60]
# Maximum 7 attempts before giving up.
RETRY_DELAYS = [1, 2, 4, 8, 16, 32, 60]


def with_retry(max_attempts: int = 7):
    """Decorator: retry on transient Gmail API errors with exponential backoff.

    Args:
        max_attempts: Maximum total attempts (default 7, matching RETRY_DELAYS length).

    Retries on:
        - googleapiclient.errors.HttpError with status 429, 500, or 503
        - ConnectionError, TimeoutError (network transients)

    Does NOT retry on:
        - HttpError with status 400, 401, 403 (auth/config errors — surface immediately)
        - Any other exception type
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            delays = RETRY_DELAYS[:max_attempts - 1]  # n-1 delays for n attempts
            last_exc: Exception | None = None

            for attempt, delay in enumerate([0] + delays):
                if delay:
                    logger.warning(
                        "Retrying %s (attempt %d/%d) after %ds",
                        fn.__name__, attempt + 1, max_attempts, delay,
                    )
                    time.sleep(delay)

                try:
                    return fn(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if _is_retryable(exc):
                        continue
                    raise  # non-retryable — re-raise immediately

            # All attempts exhausted
            raise RuntimeError(
                f"{fn.__name__} failed after {max_attempts} attempts"
            ) from last_exc

        return wrapper
    return decorator


def _is_retryable(exc: Exception) -> bool:
    """Return True if this exception represents a transient error worth retrying."""
    # Network transients
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True

    # Google API HTTP errors — only retry on rate-limit and server errors
    try:
        from googleapiclient.errors import HttpError
        if isinstance(exc, HttpError):
            status = int(exc.resp.status)
            return status in (429, 500, 503)
    except ImportError:
        pass  # google-api-python-client not installed (test environment)

    return False
