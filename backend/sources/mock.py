"""Loads EmailMetadata records from data/mock/mock_emails.json."""
import json
from datetime import datetime, timezone
from pathlib import Path

from backend.models.email_metadata import EmailMetadata
from backend.sources.base import EmailSource

_MOCK_DATA_PATH = Path(__file__).parent.parent.parent / "data" / "mock" / "mock_emails.json"


class MockEmailSource(EmailSource):
    def __init__(self, data_path: Path | None = None):
        self._path = data_path or _MOCK_DATA_PATH

    def fetch(self) -> list[EmailMetadata]:
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        emails = []
        for record in raw:
            emails.append(
                EmailMetadata(
                    message_id=record["message_id"],
                    sender_address=record["sender_address"],
                    sender_name=record.get("sender_name"),
                    subject=record["subject"],
                    email_date=datetime.fromisoformat(
                        record["email_date"].replace("Z", "+00:00")
                    ),
                    source="MOCK",
                )
            )
        return emails
