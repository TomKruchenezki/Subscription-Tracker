# Subscription Detection Rules

All detection logic in the MVP is **deterministic** — regex patterns, known sender lists,
and a weighted scoring formula. No ML, no LLMs, no probabilistic models.

Every rule documented here must have a corresponding test case in
`tests/unit/test_detector.py` and a fixture in `data/mock/mock_emails.json`.

---

## Detection Pipeline

Emails flow through five stages in order. Each stage produces a confidence delta.
The final confidence score determines the disposition.

```
Stage 1: Sender Domain Lookup  → +0.0 to +0.6
Stage 2: Subject Pattern Match → +0.0 to +0.3 (or −0.3 for promotions)
Stage 3: Parser Outputs        → +0.0 to +0.1
Stage 4: Confidence Scoring    → sum of deltas, clamped to [0.0, 1.0]
Stage 5: Threshold Decision    → DETECTED | FLAGGED | IGNORED
```

**Disposition thresholds** (configurable via env vars):

| Score range | Disposition | Action |
|---|---|---|
| `>= AUTO_DETECT_THRESHOLD` (default 0.70) | DETECTED | Auto-added to subscriptions |
| `>= REVIEW_THRESHOLD` (default 0.40) | FLAGGED | Queued for user review |
| `< REVIEW_THRESHOLD` | IGNORED | Discarded, not stored |

---

## Stage 1: Known Sender Domains

### Tier 1 — High Confidence (+0.60)

Tier 1 senders are well-known subscription services with consistent billing email patterns.
A Tier 1 match alone is enough to reach the FLAGGED threshold.

**Streaming:**
- `netflix.com`, `spotify.com`, `hulu.com`, `disneyplus.com`
- `hbomax.com`, `max.com`, `peacocktv.com`
- `primevideo.com`, `appleid.apple.com`, `email.apple.com` (Apple billing)
- `youtube.com` (for YouTube Premium)

**SaaS / Productivity:**
- `github.com`, `notion.so`, `figma.com`, `slack.com`
- `dropbox.com`, `zoom.us`, `adobe.com`, `atlassian.com`
- `1password.com`, `lastpass.com`, `bitwarden.com`
- `linear.app`, `airtable.com`, `monday.com`

**News / Media:**
- `nytimes.com`, `wsj.com`, `theatlantic.com`
- `substack.com`, `medium.com`

**Cloud / Infrastructure:**
- `aws.amazon.com`, `billing.google.com`, `azure.microsoft.com`
- `digitalocean.com`, `vercel.com`, `render.com`

### Tier 2 — Moderate Confidence (+0.30)

Generic patterns for senders not in Tier 1 but exhibiting billing-like domain patterns:
- Sender domain contains: `billing`, `invoices`, `receipts`, `payments`, `noreply`
  AND the top-level domain is `.com`, `.io`, or `.co`
- Example: `billing@someapp.io` → Tier 2 match

### No Match (+0.00)

Sender domain not in Tier 1 and not matching Tier 2 patterns.

---

## Stage 2: Subject Line Pattern Matching

Patterns are evaluated in order. The highest-confidence matching pattern wins;
promotional patterns are evaluated last and subtract confidence.

### Receipt Patterns (+0.30)

```python
RECEIPT_PATTERNS = [
    r"your (monthly|annual|weekly|yearly) (subscription|membership|plan)",
    r"receipt for .{1,60} subscription",
    r"payment receipt",
    r"invoice #\s*\d+",
    r"payment confirmation",
    r"billing (summary|statement|receipt)",
    r"we.ve charged your",
    r"thank you for (your payment|subscribing)",
]
```

### Renewal Patterns (+0.25)

```python
RENEWAL_PATTERNS = [
    r"your .{1,60} (subscription|membership) renews",
    r"upcoming (renewal|charge)",
    r"(membership|subscription) renewed",
    r"auto.?renew(al)?",
    r"your (plan|membership) has been renewed",
]
```

### Trial End Patterns (+0.20)

Trial end notifications signal an imminent subscription charge even if no payment has
occurred yet. They are treated as high-value subscription signals.

```python
TRIAL_END_PATTERNS = [
    r"(free trial|trial period) (ends|ending|expired|has ended)",
    r"your trial is (almost over|ending soon)",
    r"convert(ing)? to a paid (plan|subscription)",
]
```

### Cancellation Patterns (+0.20, triggers status update)

Cancellations are detected so an existing subscription's status can be set to CANCELLED.
They do NOT create new subscription records.

```python
CANCELLATION_PATTERNS = [
    r"(subscription|membership) (has been |)cancelled",
    r"(subscription|membership) cancellation (confirmed|confirmation)",
    r"you.ve cancelled",
    r"we.ve cancelled your",
]
```

### Promotional Exclusion (−0.30)

Marketing emails use billing-adjacent language but are not billing events.
These patterns subtract confidence even if other signals are present.

```python
PROMOTIONAL_PATTERNS = [
    r"(free trial|special offer|limited time)",
    r"\d+\s*%\s*off",
    r"upgrade (now|today|your plan)",
    r"(deal|discount|promo|coupon|sale)",
    r"don.t miss out",
    r"try .{1,40} free",
]
```

---

## Stage 3: Parser Output Deltas

These deltas are added after the parser (`backend/parser/`) runs on the email metadata.

| Parser output | Confidence delta |
|---|---|
| Amount successfully extracted | +0.10 |
| Amount extracted but out of range ($0.99–$999.99) | +0.00 (no credit, no penalty) |
| Billing cycle detected (MONTHLY / ANNUAL / WEEKLY) | +0.05 |
| Both amount AND cycle detected | +0.10 (caps at amount-only delta, not additive) |

**Why the cap:** Parser signals are corroborating evidence, not independent signals.
Adding amount (+0.10) and cycle (+0.05) separately would over-weight parser output
relative to the sender and subject signals. The cap is intentional — do not remove it.

---

## Stage 4: Confidence Score Formula

```python
def calculate_confidence(
    sender_delta: float,    # 0.0, 0.30, or 0.60
    subject_delta: float,   # -0.30 to +0.30
    parser_delta: float,    # 0.0 to +0.10
) -> float:
    raw = sender_delta + subject_delta + parser_delta
    return max(0.0, min(1.0, raw))
```

**Example calculations:**

| Scenario | Sender | Subject | Parser | Score | Disposition |
|---|---|---|---|---|---|
| Netflix receipt with amount | +0.60 | +0.30 | +0.10 | **1.00** | DETECTED |
| Tier 2 billing domain + renewal | +0.30 | +0.25 | +0.05 | **0.60** | FLAGGED |
| Tier 1 domain + promotional email | +0.60 | −0.30 | +0.00 | **0.30** | IGNORED |
| Unknown domain + "invoice #1234" | +0.00 | +0.30 | +0.10 | **0.40** | FLAGGED |

---

## Stage 5: Threshold Decision

| Score | `AUTO_DETECT_THRESHOLD` = 0.70 | `REVIEW_THRESHOLD` = 0.40 | Action |
|---|---|---|---|
| 0.85 | Above | Above | Create or update `subscriptions` record; create `email_records` row with `disposition=DETECTED` |
| 0.55 | Below | Above | Create `email_records` row with `disposition=FLAGGED`; no subscription record yet |
| 0.25 | Below | Below | Discard; no database writes |

---

## Amount Extraction Rules

Handled by `backend/parser/amount_extractor.py`.

**Primary regex** (US dollar format):
```python
r"\$(\d{1,5}(?:\.\d{2})?)"
```

**Secondary regex** (amount + explicit currency code):
```python
r"(\d{1,5}(?:\.\d{2})?)\s*(USD|EUR|GBP|CAD|AUD|JPY)"
```

**Post-extraction validation:**
- Valid range: $0.99 – $999.99 (covers all plausible subscription prices)
- Amounts outside this range are stored as `None` (parser returns `None`, not an error)
- If multiple amounts appear in the subject, the first match is used; ambiguity is
  logged at DEBUG level

---

## Billing Cycle Detection

Handled by `backend/parser/cycle_detector.py`.

| Keyword(s) in subject | Detected cycle |
|---|---|
| `monthly`, `per month`, `/mo`, `/month` | `MONTHLY` |
| `annual`, `annually`, `yearly`, `per year`, `/yr`, `/year` | `ANNUAL` |
| `weekly`, `per week`, `/wk` | `WEEKLY` |
| No match | `UNKNOWN` |

Rule: Never infer cycle from amount alone. If no keyword is found, emit `UNKNOWN`.

---

## Known Ambiguous Cases

These cases require explicit handling in the detection logic:

| Case | Handling |
|---|---|
| Amazon order confirmation from `amazon.com` | Add `amazon.com` to a one-time purchase exclusion list in `sender_list.py`; only match `primevideo.com` or `music.amazon.com` for subscriptions |
| Trial end notification (no payment yet) | Treat as subscription signal; mark `status=ACTIVE`, note trial in category metadata |
| Cancellation confirmation | Find existing subscription record by sender domain + name; update `status=CANCELLED`. Do NOT create a new subscription record. |
| Same service, multiple email domains | Map all known billing domains to the same canonical service name in `sender_resolver.py` |
| Duplicate email (re-scanned) | Match on `gmail_message_id`; skip if `email_records` row already exists |

---

## Adding New Detection Rules

Checklist before adding a new sender domain or subject pattern:

1. Add the rule to this document first
2. Add at least one mock email to `data/mock/mock_emails.json` that exercises the rule
3. Add the corresponding `expected_outcome` entry to `data/mock/expected_detections.json`
4. Add a parametrized test case in `tests/unit/test_detector.py`
5. Implement the rule in code
6. Run `pytest tests/unit/test_detector.py` — all cases must pass
7. Invoke `subscription-detection-specialist` agent for rule design review
8. Invoke `privacy-security-reviewer` agent if the rule changes what data is stored
