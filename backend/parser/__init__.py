from .amount_extractor import extract_amount
from .sender_resolver import resolve_sender
from .cycle_detector import detect_cycle
from backend.models.email_metadata import EmailMetadata


def parse_email_metadata(email: EmailMetadata):
    """Combine all three parsers and return a ParsedMetadata dict."""
    amount, currency = extract_amount(email.subject)
    canonical_name = resolve_sender(email.sender_address)
    cycle = detect_cycle(email.subject)
    return {
        "canonical_name": canonical_name,
        "amount": amount,
        "currency": currency,
        "billing_cycle": cycle,
    }
