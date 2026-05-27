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
    # google.com is too broad for general mail, but these billing subdomains are safe
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
    Returns (0, None) for excluded domains to signal explicit rejection.
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
