"""Unit tests for sender_list.py — Tier 1/2/excluded domain lookups."""
import pytest
from backend.detector.sender_list import get_tier, get_processor_name, TIER_1, TIER_2, EXCLUDED, PROCESSOR_DOMAINS


# ── Existing Tier 1 domains ───────────────────────────────────────────────────

@pytest.mark.parametrize("domain, expected_name", [
    ("netflix.com",            "Netflix"),
    ("account.netflix.com",    "Netflix"),
    ("spotify.com",            "Spotify"),
    ("email.spotify.com",      "Spotify"),
    ("zoom.us",                "Zoom"),
    ("github.com",             "GitHub"),
    ("openai.com",             "OpenAI"),
    ("anthropic.com",          "Claude"),
    ("apple.com",              "Apple"),
    ("email.apple.com",        "Apple"),
    ("linkedin.com",           "LinkedIn Premium"),
    ("grammarly.com",          "Grammarly"),
    ("substack.com",           "Substack"),
    ("microsoft.com",          "Microsoft 365"),
])
def test_existing_tier1_domains(domain, expected_name):
    tier, name = get_tier(domain)
    assert tier == 1
    assert name == expected_name


# ── Phase 2.9: Google domain additions ───────────────────────────────────────

def test_google_com_is_tier1():
    """google.com must be Tier 1 after Phase 2.9 (for Google Play receipts)."""
    tier, name = get_tier("google.com")
    assert tier == 1
    assert name == "Google"


def test_play_google_com_is_tier1():
    """play.google.com must be Tier 1 (explicit Google Play entry)."""
    tier, name = get_tier("play.google.com")
    assert tier == 1
    assert name == "Google Play"


def test_noreply_google_com_subdomain_of_google():
    """noreply@google.com has domain google.com — direct Tier 1 match."""
    tier, name = get_tier("google.com")
    assert tier == 1
    assert name == "Google"


def test_payments_google_com_still_tier1():
    """Existing payments.google.com entry must remain Tier 1."""
    tier, name = get_tier("payments.google.com")
    assert tier == 1


def test_store_google_com_still_tier1():
    """Existing store.google.com entry must remain Tier 1."""
    tier, name = get_tier("store.google.com")
    assert tier == 1
    assert name == "Google One"


# ── Tier 2 domains ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("domain", [
    "billing.stripe.com",
    "mail.paddle.com",
    "invoices.chargebee.com",
])
def test_tier2_domains(domain):
    tier, name = get_tier(domain)
    assert tier == 2
    assert name is None


# ── Excluded domains ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("domain", [
    "amazon.com",
    "ebay.com",
    "etsy.com",
])
def test_excluded_domains(domain):
    tier, name = get_tier(domain)
    assert tier == -1
    assert name is None


# ── Unknown domains ───────────────────────────────────────────────────────────

def test_unknown_domain_is_tier0():
    tier, name = get_tier("randomsite.io")
    assert tier == 0
    assert name is None


# ── Subdomain matching ────────────────────────────────────────────────────────

def test_subdomain_of_tier1_matches():
    """Subdomains of Tier 1 domains should resolve to the parent's canonical name."""
    # billing.account.netflix.com → endswith ".netflix.com" → Tier 1
    tier, name = get_tier("billing.account.netflix.com")
    assert tier == 1
    assert name == "Netflix"


# ── Phase 3.4: Wolt/Wolt+ coverage ───────────────────────────────────────────

def test_wolt_com_is_tier1():
    """wolt.com must be Tier 1 — Wolt+ subscription emails come from this domain."""
    tier, name = get_tier("wolt.com")
    assert tier == 1, f"wolt.com must be Tier 1, got {tier}"
    assert name == "Wolt+", f"wolt.com canonical name must be 'Wolt+', got {name!r}"


def test_wolt_mail_subdomain_is_tier1():
    """mail.wolt.com must be Tier 1 (Wolt sends from this subdomain)."""
    tier, name = get_tier("mail.wolt.com")
    assert tier == 1, f"mail.wolt.com must be Tier 1, got {tier}"
    assert name == "Wolt+", f"mail.wolt.com canonical name must be 'Wolt+', got {name!r}"


def test_wolt_fi_is_tier1():
    """wolt.fi (Finnish market) must be Tier 1."""
    tier, name = get_tier("wolt.fi")
    assert tier == 1, f"wolt.fi must be Tier 1, got {tier}"
    assert name == "Wolt+", f"wolt.fi canonical name must be 'Wolt+', got {name!r}"


def test_wolt_de_is_tier1():
    """wolt.de (German market) must be Tier 1."""
    tier, name = get_tier("wolt.de")
    assert tier == 1, f"wolt.de must be Tier 1, got {tier}"
    assert name == "Wolt+", f"wolt.de canonical name must be 'Wolt+', got {name!r}"


def test_wolt_il_is_tier1():
    """wolt.il (Israeli market) must be Tier 1."""
    tier, name = get_tier("wolt.il")
    assert tier == 1, f"wolt.il must be Tier 1, got {tier}"
    assert name == "Wolt+", f"wolt.il canonical name must be 'Wolt+', got {name!r}"


# ── Phase 3.8: Processor domain detection ─────────────────────────────────────

@pytest.mark.parametrize("domain, expected_processor", [
    ("cardcom.co.il",       "Cardcom"),
    ("z-credit.co.il",      "Z-Credit"),
    ("zcredit.co.il",       "Z-Credit"),
    ("morning.co.il",       "Morning"),
    ("icount.co.il",        "Morning"),
    ("ravpass.co.il",       "RavPass"),
    ("grow.me",             "Grow"),
    ("grow.il",             "Grow"),
    ("tranzila.com",        "Tranzila"),
    ("paylink.co.il",       "Paylink"),
    ("meshulam.co.il",      "Meshulam"),
])
def test_processor_domains_detected(domain, expected_processor):
    """get_processor_name() returns canonical processor name for known processor domains."""
    assert get_processor_name(domain) == expected_processor


def test_non_processor_returns_none():
    """get_processor_name() returns None for regular subscription providers."""
    assert get_processor_name("spotify.com") is None
    assert get_processor_name("netflix.com") is None
    assert get_processor_name("unknown-startup.io") is None


def test_processor_domains_not_in_tier1():
    """Processor domains must not be in Tier 1 (they are not subscription providers)."""
    for domain in PROCESSOR_DOMAINS:
        tier, _ = get_tier(domain)
        assert tier != 1, (
            f"Processor domain {domain!r} must not be Tier 1 — "
            f"processors should not be treated as subscription providers"
        )


def test_processor_domains_not_excluded():
    """Processor domains must not be in EXCLUDED — their emails should still be stored."""
    for domain in PROCESSOR_DOMAINS:
        tier, _ = get_tier(domain)
        assert tier != -1, (
            f"Processor domain {domain!r} must not be in EXCLUDED — "
            f"processor emails should be stored (as one-time/unknown), not dropped"
        )


def test_processor_subdomain_match():
    """Subdomains of processor domains are also detected."""
    assert get_processor_name("mail.cardcom.co.il") == "Cardcom"
