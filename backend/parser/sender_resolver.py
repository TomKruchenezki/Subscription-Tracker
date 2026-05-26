"""
Resolves a sender email address to a canonical subscription service name.
Delegates to sender_list.TIER_1 for known services; falls back to domain label extraction.
"""
import re
from backend.detector.sender_list import TIER_1, EXCLUDED


def _extract_domain(email_address: str) -> str:
    """Return the domain part of an email address, lowercased."""
    email_address = email_address.strip().lower()
    if "@" in email_address:
        return email_address.split("@", 1)[1]
    return email_address


def _domain_label(domain: str) -> str:
    """
    Extract the most meaningful label from an unknown domain.
    billing@billing.unknownapp.io → unknownapp
    """
    # Strip common prefixes like "mail.", "billing.", "no-reply."
    parts = domain.split(".")
    # Drop known noise prefixes
    noise = {"mail", "billing", "no-reply", "noreply", "email", "invoices", "notify",
             "payments", "support", "hello", "info"}
    meaningful = [p for p in parts[:-1] if p not in noise]  # exclude TLD
    if meaningful:
        return meaningful[-1]
    return parts[0]


def resolve_sender(email_address: str) -> str | None:
    """
    Returns canonical service name, or a best-guess label for unknown domains.
    Returns None for explicitly excluded domains (e.g. amazon.com).
    """
    domain = _extract_domain(email_address)

    if domain in EXCLUDED:
        return None

    # Direct lookup
    if domain in TIER_1:
        return TIER_1[domain]

    # Subdomain match: billing@accounts.netflix.com → Netflix
    for known, name in TIER_1.items():
        if domain.endswith("." + known):
            return name

    # Fallback: extract best label from unknown domain
    return _domain_label(domain)
