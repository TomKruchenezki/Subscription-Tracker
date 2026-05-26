from dataclasses import dataclass
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
