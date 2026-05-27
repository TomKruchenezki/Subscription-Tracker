"""Unit tests for sender_list.py — Tier 1/2/excluded domain lookups."""
import pytest
from backend.detector.sender_list import get_tier, TIER_1, TIER_2, EXCLUDED


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
