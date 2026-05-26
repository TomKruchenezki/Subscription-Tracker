"""
Tier 1: known subscription service domains with canonical names.
Tier 2: billing-related domains not in Tier 1 (still plausible subscriptions).
EXCLUDED: one-time purchase or ambiguous domains — never detect as subscriptions.
"""

# Maps sender domain → canonical subscription name
TIER_1: dict[str, str] = {
    "netflix.com": "Netflix",
    "account.netflix.com": "Netflix",
    "spotify.com": "Spotify",
    "email.spotify.com": "Spotify",
    "github.com": "GitHub",
    "copilot.github.com": "GitHub Copilot",
    "notion.so": "Notion",
    "mail.notion.so": "Notion",
    "figma.com": "Figma",
    "mail.figma.com": "Figma",
    "zoom.us": "Zoom",
    "adobe.com": "Adobe Creative Cloud",
    "mail.adobe.com": "Adobe Creative Cloud",
    "digitalocean.com": "DigitalOcean",
    "nytimes.com": "New York Times",
    "substack.com": "Substack",
    "hulu.com": "Hulu",
    "dropbox.com": "Dropbox",
    "slack.com": "Slack",
    "atlassian.com": "Atlassian",
    "1password.com": "1Password",
    "linear.app": "Linear",
    "disneyplus.com": "Disney+",
    "mail.disneyplus.com": "Disney+",
    "vercel.com": "Vercel",
    "bitwarden.com": "Bitwarden",
    "monday.com": "Monday.com",
    "airtable.com": "Airtable",
    "max.com": "Max",
    "hbomax.com": "Max",
    # Amazon Prime Video is subscription; amazon.com itself is excluded (one-time purchases)
    "primevideo.com": "Amazon Prime Video",
    "amazon.co.uk": "Amazon Prime Video",
    # Apple billing-specific subdomains only (not apple.com — too broad)
    "appleid.apple.com": "Apple",
    "email.apple.com": "Apple",
    "microsoft.com": "Microsoft 365",
    "office.com": "Microsoft 365",
}

# Maps sender domain → canonical name; lower confidence than Tier 1
TIER_2: set[str] = {
    "billing.stripe.com",
    "mail.paddle.com",
    "invoices.chargebee.com",
    "billing.recurly.com",
    "notify.gumroad.com",
    "lemonsqueezy.com",
    "paypal.com",
    "fastspring.com",
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
