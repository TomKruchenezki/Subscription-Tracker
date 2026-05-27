from .amount_extractor import extract_amount
from .sender_resolver import resolve_sender
from .cycle_detector import detect_cycle
from backend.models.email_metadata import EmailMetadata


def parse_email_metadata(email: EmailMetadata):
    """Combine all three parsers and return a ParsedMetadata dict.

    Snippet and body_text are passed to amount_extractor and cycle_detector as
    fallback signals. They are used only for extraction — never stored or logged.
    Priority: subject → snippet → body_text.
    """
    amount, currency = extract_amount(
        email.subject, snippet=email.snippet, body_text=email.body_text
    )
    canonical_name = resolve_sender(email.sender_address)
    cycle = detect_cycle(
        email.subject, snippet=email.snippet, body_text=email.body_text
    )
    return {
        "canonical_name": canonical_name,
        "amount": amount,
        "currency": currency,
        "billing_cycle": cycle,
    }
