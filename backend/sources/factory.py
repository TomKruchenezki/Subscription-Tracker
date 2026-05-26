"""Returns the appropriate EmailSource based on the USE_MOCK environment variable."""
import os
from backend.sources.base import EmailSource
from backend.sources.mock import MockEmailSource


def get_email_source() -> EmailSource:
    """
    USE_MOCK=true  (default) → MockEmailSource
    USE_MOCK=false            → GmailEmailSource (Phase 2)
    """
    use_mock = os.getenv("USE_MOCK", "true").lower() not in {"false", "0", "no"}
    if use_mock:
        return MockEmailSource()

    # Phase 2: import GmailEmailSource only when needed to avoid hard dependency
    try:
        from backend.sources.gmail import GmailEmailSource  # noqa: F401
        return GmailEmailSource()
    except ImportError as exc:
        raise RuntimeError(
            "USE_MOCK=false but backend.sources.gmail is not implemented yet. "
            "Complete Phase 2 before switching to Gmail mode."
        ) from exc
