"""
Tier 1: known subscription service domains with canonical names.
Tier 2: billing-related domains not in Tier 1 (still plausible subscriptions).
EXCLUDED: one-time purchase or ambiguous domains — never detect as subscriptions.
"""

# Maps sender domain → canonical subscription name
TIER_1: dict[str, str] = {
    # ── Streaming ──────────────────────────────────────────────────────────────
    "netflix.com": "Netflix",
    "account.netflix.com": "Netflix",
    "spotify.com": "Spotify",
    "email.spotify.com": "Spotify",
    "hulu.com": "Hulu",
    "disneyplus.com": "Disney+",
    "mail.disneyplus.com": "Disney+",
    "max.com": "Max",
    "hbomax.com": "Max",
    "youtube.com": "YouTube Premium",
    # Amazon Prime Video is subscription; amazon.com itself is excluded (one-time purchases)
    "primevideo.com": "Amazon Prime Video",
    "amazon.co.uk": "Amazon Prime Video",

    # ── Productivity / SAAS ────────────────────────────────────────────────────
    "github.com": "GitHub",
    "copilot.github.com": "GitHub Copilot",
    "notion.so": "Notion",
    "mail.notion.so": "Notion",
    "figma.com": "Figma",
    "mail.figma.com": "Figma",
    "zoom.us": "Zoom",
    "slack.com": "Slack",
    "atlassian.com": "Atlassian",
    "1password.com": "1Password",
    "linear.app": "Linear",
    "vercel.com": "Vercel",
    "monday.com": "Monday.com",
    "airtable.com": "Airtable",
    "canva.com": "Canva",
    "mail.canva.com": "Canva",
    "wix.com": "Wix",
    "mail.wix.com": "Wix",
    "grammarly.com": "Grammarly",
    "mails.grammarly.com": "Grammarly",

    # ── AI services ────────────────────────────────────────────────────────────
    "openai.com": "OpenAI",
    "billing.openai.com": "ChatGPT",
    "anthropic.com": "Claude",
    "billing.anthropic.com": "Claude",

    # ── Cloud / Storage ────────────────────────────────────────────────────────
    "dropbox.com": "Dropbox",
    "bitwarden.com": "Bitwarden",
    "nordvpn.com": "NordVPN",
    "info.nordvpn.com": "NordVPN",
    "digitalocean.com": "DigitalOcean",
    "substack.com": "Substack",
    "nytimes.com": "New York Times",

    # ── Apple ──────────────────────────────────────────────────────────────────
    # appleid.apple.com and email.apple.com for billing receipts
    "appleid.apple.com": "Apple",
    "email.apple.com": "Apple",
    "apple.com": "Apple",

    # ── Google services ────────────────────────────────────────────────────────
    # google.com is safe to add as Tier 1 because Phase 2.8 weights (0.25 base)
    # require billing language to reach DETECTED. google.com + NONE = 0.25 → IGNORED.
    # google.com + RECEIPT + amount = 0.85 → DETECTED. This allows Google Play receipts
    # (from noreply@google.com) to be detected correctly.
    "google.com": "Google",
    "play.google.com": "Google Play",
    "store.google.com": "Google One",
    "payments.google.com": "Google",
    "notifications.google.com": "Google",

    # ── Microsoft ──────────────────────────────────────────────────────────────
    "microsoft.com": "Microsoft 365",
    "office.com": "Microsoft 365",

    # ── Adobe ──────────────────────────────────────────────────────────────────
    "adobe.com": "Adobe Creative Cloud",
    "mail.adobe.com": "Adobe Creative Cloud",

    # ── Education ──────────────────────────────────────────────────────────────
    "udemy.com": "Udemy",
    "mail.udemy.com": "Udemy",
    "coursera.org": "Coursera",
    "mail.coursera.org": "Coursera",

    # ── Professional ───────────────────────────────────────────────────────────
    "linkedin.com": "LinkedIn Premium",
    "e.linkedin.com": "LinkedIn Premium",
    "mcee.linkedin.com": "LinkedIn Premium",

    # ── Food / Delivery subscriptions ─────────────────────────────────────────
    # Wolt+ is a recurring delivery subscription. Food order receipts from wolt.com
    # are also Tier 1 so they are classified and surfaced (is_one_time_candidate for
    # individual orders; Wolt+ renewal subject lines → is_recurring_candidate).
    "wolt.com":      "Wolt+",
    "mail.wolt.com": "Wolt+",
    "wolt.fi":       "Wolt+",   # Finland
    "wolt.de":       "Wolt+",   # Germany
    "wolt.at":       "Wolt+",   # Austria
    "wolt.il":       "Wolt+",   # Israel

    # ── Payment (own subscription receipts) ────────────────────────────────────
    "paypal.com": "PayPal",
}

# Maps sender domain → canonical name; lower confidence than Tier 1
TIER_2: set[str] = {
    "billing.stripe.com",
    "mail.paddle.com",
    "invoices.chargebee.com",
    "billing.recurly.com",
    "notify.gumroad.com",
    "lemonsqueezy.com",
    "fastspring.com",
    # paypal.com moved to Tier 1 (sends its own subscription receipts)
}

# ── Payment processor domains ─────────────────────────────────────────────────
# Emails from these domains originate from a payment gateway / invoicing platform,
# not from a subscription provider. The actual merchant is determined from the PDF
# structured fields or the email subject — not from the sender domain.
#
# Rules applied in detector.py when sender domain is in PROCESSOR_DOMAINS:
#   - email_records.payment_processor = canonical processor name
#   - email_records.is_processor_email = 1
#   - Without strong recurring evidence → event_type = "one_time_charge" / "unknown_payment"
#   - Row is stored (never IGNORED) but hidden from subscription Review Queue
# Maps domain → canonical processor name
PROCESSOR_DOMAINS: dict[str, str] = {
    # ── Israeli payment processors ───────────────────────────────────────────
    "cardcom.co.il":      "Cardcom",
    "mail.cardcom.co.il": "Cardcom",
    "z-credit.co.il":     "Z-Credit",
    "zcredit.co.il":      "Z-Credit",
    "morning.co.il":      "Morning",        # formerly iCount
    "icount.co.il":       "Morning",        # iCount (rebranded as Morning)
    "ravpass.co.il":      "RavPass",
    "grow.me":            "Grow",
    "grow.il":            "Grow",
    "invoices.grow.me":   "Grow",
    "priority.co.il":     "Priority",       # Priority ERP invoicing
    "tranzila.com":       "Tranzila",
    "paylink.co.il":      "Paylink",
    "meshulam.co.il":     "Meshulam",
    # ── Global invoice / billing platforms (non-subscription receipts) ────────
    # stripe.com / paddle.com etc. are in TIER_2 (they also send real subscription
    # receipts). Only add here if the domain exclusively sends one-time invoices.
    "invoices.bill.com":  "Bill.com",
    "mail.quickbooks.com": "QuickBooks",
    "invoice.payoneer.com": "Payoneer",
}


# Domains excluded from subscription detection entirely
EXCLUDED: set[str] = {
    "amazon.com",      # One-time purchases — use primevideo.com for Prime
    "ebay.com",
    "etsy.com",
    "shopify.com",
    "fedex.com",
    "ups.com",
    "usps.com",
    "dhl.com",
}


def get_tier(domain: str) -> tuple[int, str | None]:
    """
    Returns (tier, canonical_name).
    tier 1 = known subscription service
    tier 2 = billing-adjacent but unconfirmed
    tier 0 = no match
    Returns (-1, None) for excluded domains to signal explicit rejection.
    """
    domain = domain.lower()

    if domain in EXCLUDED:
        return (-1, None)  # Explicitly excluded

    if domain in TIER_1:
        return (1, TIER_1[domain])

    # Check if any Tier 1 entry is a suffix of the domain (e.g. subdomain matching)
    for known_domain, name in TIER_1.items():
        if domain.endswith("." + known_domain):
            return (1, name)

    if domain in TIER_2:
        return (2, None)

    return (0, None)


def get_processor_name(domain: str) -> str | None:
    """Return the canonical processor name if domain is a known payment processor, else None."""
    domain = domain.lower()
    if domain in PROCESSOR_DOMAINS:
        return PROCESSOR_DOMAINS[domain]
    for known_domain, name in PROCESSOR_DOMAINS.items():
        if domain.endswith("." + known_domain):
            return name
    return None
