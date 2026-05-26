"""Abstract base class for email sources. Both MockEmailSource and GmailEmailSource
implement this interface so the detection layer never needs to change."""
from abc import ABC, abstractmethod
from backend.models.email_metadata import EmailMetadata


class EmailSource(ABC):
    @abstractmethod
    def fetch(self) -> list[EmailMetadata]:
        """Fetch all available email metadata records."""
        ...
