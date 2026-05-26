from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass
class EmailMetadata:
    message_id: str
    sender_address: str
    sender_name: str | None
    subject: str
    email_date: datetime
    source: Literal["MOCK", "GMAIL"]
