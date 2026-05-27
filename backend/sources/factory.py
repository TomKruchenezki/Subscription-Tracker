"""Returns the appropriate EmailSource based on the USE_MOCK environment variable."""
import os
from backend.sources.base import EmailSource
from backend.sources.mock import MockEmailSource


def get_email_source(account_id: str | None = None) -> EmailSource:
    """
    USE_MOCK=true  (default) → MockEmailSource (account_id ignored)
    USE_MOCK=false            → GmailEmailSource(account_id=account_id)

    The caller (scan.py) is responsible for resolving account_id from the DB
    before calling this function when USE_MOCK=false.
    """
    use_mock = os.getenv("USE_MOCK", "true").lower() not in {"false", "0", "no"}
    if use_mock:
        return MockEmailSource()

    # Phase 2: import GmailEmailSource only when needed to avoid hard dependency
    try:
        from backend.sources.gmail import GmailEmailSource
        return GmailEmailSource(account_id=account_id)
    except ImportError as exc:
        raise RuntimeError(
            "USE_MOCK=false but google-auth-oauthlib is not installed. "
            "Run: pip install google-auth-oauthlib google-api-python-client"
        ) from exc
