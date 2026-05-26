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
    ) -> list[EmailMetadata]:
        """Fetch email metadata records, optionally filtered by date range."""
        ...
