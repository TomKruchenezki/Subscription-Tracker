"""
Resolves a sender email address to a canonical subscription service name.
Delegates to sender_list.TIER_1 for known services; falls back to domain label extraction.

Apple product disambiguation:
  All Apple billing domains (apple.com, email.apple.com, appleid.apple.com) map to the
  generic canonical name "Apple". When the email subject contains a recognizable Apple
  product name (Apple Music, iCloud, App Store, iTunes), the canonical name is refined
  to the specific product. This lets Apple Music and iCloud+ appear as distinct
  subscriptions rather than being merged under "Apple".
"""
import re
from backend.detector.sender_list import TIER_1, EXCLUDED

# Subject-line patterns for Apple product disambiguation.
# Checked only when the sender resolves to canonical name "Apple".
# Priority: first match wins (ordered most-specific first).
_APPLE_PRODUCT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bapple\s+music\b", re.IGNORECASE),    "Apple Music"),
    (re.compile(r"\bicloud\+?\b",     re.IGNORECASE),    "iCloud+"),
    (re.compile(r"\bapp\s+store\b",   re.IGNORECASE),    "App Store"),
    (re.compile(r"\bitunes\b",        re.IGNORECASE),    "Apple Music"),  # iTunes = Apple Music
    (re.compile(r"\bapple\s+tv\+?\b", re.IGNORECASE),   "Apple TV+"),
    (re.compile(r"\bapple\s+one\b",   re.IGNORECASE),   "Apple One"),
    (re.compile(r"\barc(?:ade)?\b",   re.IGNORECASE),   "Apple Arcade"),
]


def _refine_apple_product(subject: str) -> str | None:
    """Return a refined Apple product name from the email subject, or None for generic Apple."""
    for pattern, product_name in _APPLE_PRODUCT_PATTERNS:
        if pattern.search(subject):
            return product_name
    return None


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


def resolve_sender(email_address: str, subject: str = "") -> str | None:
    """
    Returns canonical service name, or a best-guess label for unknown domains.
    Returns None for explicitly excluded domains (e.g. amazon.com).

    Args:
        email_address: Sender email (used for domain lookup).
        subject: Email subject line. Used only for Apple product disambiguation
                 (Apple Music, iCloud+, App Store, iTunes). Never stored or logged.
    """
    domain = _extract_domain(email_address)

    if domain in EXCLUDED:
        return None

    # Direct lookup
    if domain in TIER_1:
        name = TIER_1[domain]
        # Apple product disambiguation: refine "Apple" using subject keywords
        if name == "Apple" and subject:
            refined = _refine_apple_product(subject)
            if refined:
                return refined
        return name

    # Subdomain match: billing@accounts.netflix.com → Netflix
    for known, name in TIER_1.items():
        if domain.endswith("." + known):
            # Apple product disambiguation applies to subdomains too
            if name == "Apple" and subject:
                refined = _refine_apple_product(subject)
                if refined:
                    return refined
            return name

    # Fallback: extract best label from unknown domain
    return _domain_label(domain)
