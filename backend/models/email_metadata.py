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
    # Body text extracted from format="full" Gmail response (forensic mode only).
    # Used only for parser extraction — NEVER stored in the database, NEVER logged,
    # NEVER returned by any API endpoint.
    body_text: str | None = field(default=None)
    # Phase 3.7: attachment metadata + transient PDF-derived evidence (forensic mode).
    # Each element is a dict:
    #   {filename, mime_type, size_bytes, gmail_attachment_id,
    #    detected_attachment_type, processing_status, evidence}
    # where "evidence" is an (ephemeral) PdfEvidence or None. The raw PDF bytes/text
    # that produced "evidence" are NEVER attached here, NEVER stored, NEVER logged.
    # Only the structured PdfEvidence fields are later persisted by the detector.
    attachments: list = field(default_factory=list)
