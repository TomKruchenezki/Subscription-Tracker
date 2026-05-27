from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class EmailMetadata:
    source_message_id: str
    source_provider: str
    source_account_id: str
    source_account_email: str
    sender_address: str
    sender_name: str | None
    subject: str
    email_date: datetime
    # Snippet: short body preview included for free in format="metadata" Gmail responses.
    # Used only for parser extraction — NEVER stored in the database or logged.
    snippet: str | None = field(default=None)
