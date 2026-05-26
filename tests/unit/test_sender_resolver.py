import pytest
from backend.parser.sender_resolver import resolve_sender


@pytest.mark.parametrize("email, expected", [
    ("no-reply@netflix.com",           "Netflix"),
    ("billing@account.netflix.com",    "Netflix"),   # subdomain match
    ("no-reply@spotify.com",           "Spotify"),
    ("noreply@primevideo.com",          "Amazon Prime Video"),
    ("no-reply@mail.notion.so",        "Notion"),
    ("billing@digitalocean.com",       "DigitalOcean"),
    ("nytdirect@nytimes.com",          "New York Times"),
    # Fallback: unknown domain → label extracted from domain
    ("billing@billing.unknownapp.io",  "unknownapp"),
    ("hello@syncspace.co",             "syncspace"),
    ("payments@pixelcraft.ai",         "pixelcraft"),
])
def test_resolve_sender(email, expected):
    assert resolve_sender(email) == expected


def test_excluded_domain_returns_none():
    """amazon.com is excluded — one-time purchase, not a subscription service."""
    assert resolve_sender("no-reply@amazon.com") is None


def test_primevideo_is_not_excluded():
    """primevideo.com is Tier 1 — Amazon Prime Video is a subscription."""
    result = resolve_sender("noreply@primevideo.com")
    assert result == "Amazon Prime Video"
