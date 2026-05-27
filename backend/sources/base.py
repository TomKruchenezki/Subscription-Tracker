"""Abstract base class for email sources. Both MockEmailSource and GmailEmailSource
implement this interface so the detection layer never needs to change."""
from abc import ABC, abstractmethod
from datetime import datetime
from backend.models.email_metadata import EmailMetadata


class EmailSource(ABC):
    @abstractmethod
    def fetch(
        self,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        mode: str = "deep",
        content_access_level: str = "metadata_plus_snippet",
    ) -> list[EmailMetadata]:
        """Fetch email metadata records, optionally filtered by date range.

        Args:
            date_from: Only return emails on or after this datetime.
            date_to: Only return emails on or before this datetime.
            mode: Scan depth — "quick", "deep" (default), or "forensic".
                  MockEmailSource ignores this; GmailEmailSource uses it to
                  select which query passes to run.
            content_access_level: Controls what content is read from each email.
                "metadata_plus_snippet" — subject, sender, date, snippet (default).
                "body_text_ephemeral"   — also fetches full body text ephemerally
                                          for forensic parsing; raw content is
                                          discarded immediately, never stored/logged.
        """
        ...
