import pytest
from backend.parser.sender_resolver import resolve_sender


@pytest.mark.parametrize("email, expected", [
    ("no-reply@netflix.com",              "Netflix"),
    ("billing@account.netflix.com",       "Netflix"),   # subdomain match
    ("no-reply@spotify.com",              "Spotify"),
    ("noreply@primevideo.com",            "Amazon Prime Video"),
    ("no-reply@mail.notion.so",           "Notion"),
    ("billing@digitalocean.com",          "DigitalOcean"),
    ("nytdirect@nytimes.com",             "New York Times"),
    # New providers
    ("billing@openai.com",                "OpenAI"),
    ("billing@billing.openai.com",        "ChatGPT"),
    ("no-reply@anthropic.com",            "Claude"),
    ("billing@billing.anthropic.com",     "Claude"),
    ("no-reply@canva.com",                "Canva"),
    ("info@mail.canva.com",               "Canva"),
    ("no-reply@wix.com",                  "Wix"),
    ("no-reply@udemy.com",                "Udemy"),
    ("no-reply@coursera.org",             "Coursera"),
    ("messages-noreply@linkedin.com",     "LinkedIn Premium"),
    ("reply@e.linkedin.com",              "LinkedIn Premium"),
    ("no-reply@grammarly.com",            "Grammarly"),
    ("info@nordvpn.com",                  "NordVPN"),
    ("no-reply@youtube.com",              "YouTube Premium"),
    ("noreply@store.google.com",          "Google One"),
    ("paypal@paypal.com",                 "PayPal"),
    # Fallback: unknown domain → label extracted from domain
    ("billing@billing.unknownapp.io",     "unknownapp"),
    ("hello@syncspace.co",                "syncspace"),
    ("payments@pixelcraft.ai",            "pixelcraft"),
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


# ── Phase 3.4: Apple product name disambiguation ──────────────────────────────

def test_apple_music_subject_returns_apple_music():
    """Apple sender + 'Apple Music' in subject → 'Apple Music' (not generic 'Apple')."""
    result = resolve_sender("no-reply@apple.com", subject="Your Apple Music subscription receipt - $10.99")
    assert result == "Apple Music", (
        f"Apple sender with 'Apple Music' in subject must resolve to 'Apple Music', got {result!r}"
    )


def test_icloud_subject_returns_icloud_plus():
    """Apple sender + 'iCloud' in subject → 'iCloud+'."""
    result = resolve_sender("no-reply@apple.com", subject="iCloud storage plan renewed - $0.99/month")
    assert result == "iCloud+", (
        f"Apple sender with 'iCloud' in subject must resolve to 'iCloud+', got {result!r}"
    )


def test_app_store_subject_returns_app_store():
    """Apple sender + 'App Store' in subject → 'App Store'."""
    result = resolve_sender("no-reply@email.apple.com", subject="App Store receipt from Apple")
    assert result == "App Store", (
        f"Apple sender with 'App Store' in subject must resolve to 'App Store', got {result!r}"
    )


def test_itunes_subject_returns_apple_music():
    """Apple sender + 'iTunes' in subject → 'Apple Music' (iTunes is legacy Apple Music)."""
    result = resolve_sender("no-reply@apple.com", subject="iTunes invoice - $9.99")
    assert result == "Apple Music", (
        f"Apple sender with 'iTunes' in subject must resolve to 'Apple Music', got {result!r}"
    )


def test_apple_tv_plus_subject():
    """Apple sender + 'Apple TV+' in subject → 'Apple TV+'."""
    result = resolve_sender("no-reply@apple.com", subject="Your Apple TV+ subscription")
    assert result == "Apple TV+", (
        f"Apple sender with 'Apple TV+' in subject must resolve to 'Apple TV+', got {result!r}"
    )


def test_apple_one_subject():
    """Apple sender + 'Apple One' in subject → 'Apple One'."""
    result = resolve_sender("no-reply@apple.com", subject="Apple One subscription renewed")
    assert result == "Apple One", (
        f"Apple sender with 'Apple One' in subject must resolve to 'Apple One', got {result!r}"
    )


def test_generic_apple_subject_returns_apple():
    """Apple sender + unrecognized subject → generic 'Apple'."""
    result = resolve_sender("no-reply@apple.com", subject="Your receipt from Apple")
    assert result == "Apple", (
        f"Apple sender with unrecognized subject must return generic 'Apple', got {result!r}"
    )


def test_apple_no_subject_returns_apple():
    """Apple sender + empty subject → generic 'Apple' (no disambiguation possible)."""
    result = resolve_sender("no-reply@apple.com", subject="")
    assert result == "Apple", (
        f"Apple sender with no subject must return generic 'Apple', got {result!r}"
    )


def test_non_apple_sender_not_affected_by_apple_patterns():
    """Non-Apple sender mentioning 'Apple Music' in an irrelevant context → not affected."""
    # spotify.com is Tier 1 → always returns "Spotify" regardless of subject
    result = resolve_sender("no-reply@spotify.com", subject="Switch from Apple Music to Spotify")
    assert result == "Spotify", (
        f"Non-Apple sender must not be affected by Apple product patterns, got {result!r}"
    )


# ── Phase 3.4: Wolt sender resolution ────────────────────────────────────────

def test_wolt_sender_resolves():
    """wolt.com Tier 1 sender must resolve to 'Wolt+'."""
    result = resolve_sender("noreply@wolt.com")
    assert result == "Wolt+", (
        f"wolt.com sender must resolve to 'Wolt+', got {result!r}"
    )


def test_wolt_mail_sender_resolves():
    """mail.wolt.com sender must resolve to 'Wolt+'."""
    result = resolve_sender("noreply@mail.wolt.com")
    assert result == "Wolt+", (
        f"mail.wolt.com sender must resolve to 'Wolt+', got {result!r}"
    )
