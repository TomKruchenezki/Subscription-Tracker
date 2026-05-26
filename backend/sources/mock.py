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

    def fetch(
        self,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        mode: str = "deep",  # noqa: ARG002 — mode ignored; mock always returns all matching records
    ) -> list[EmailMetadata]:
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        emails = []
        for record in raw:
            email_date = datetime.fromisoformat(
                record["email_date"].replace("Z", "+00:00")
            )
            if date_from and email_date < date_from:
                continue
            if date_to and email_date > date_to:
                continue
            emails.append(
                EmailMetadata(
                    source_message_id=record.get("source_message_id", record["message_id"]),
                    source_provider="MOCK",
                    source_account_id=record.get("source_account_id", "mock_default"),
                    source_account_email=record.get("source_account_email", "demo@mock.local"),
                    sender_address=record["sender_address"],
                    sender_name=record.get("sender_name"),
                    subject=record["subject"],
                    email_date=email_date,
                )
            )
        return emails
