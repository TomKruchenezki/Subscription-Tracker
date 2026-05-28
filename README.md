# Subscription Tracker

A privacy-first, local-first Gmail subscription tracker. Reads Gmail metadata only
(sender, subject, date — never body or attachments). Detects recurring subscriptions
and financial events. All data stays in a local SQLite file.

---

## What This App Does

Connects to your Gmail account (read-only), scans email metadata, and automatically
detects subscriptions like Spotify, Netflix, GitHub, etc. Extracts amounts, currencies,
and billing cycles. Displays a dashboard with your monthly spend.

**Key product direction:** Higher recall over perfect precision. Missing a real
subscription is worse than showing a false positive. False positives can be deleted.

---

## Privacy Model

- **`gmail.readonly` scope only** — never writes or modifies Gmail
- **Email bodies are never stored** — `format=metadata` API calls only; body_text is
  ephemeral (in-memory only during forensic scans, never persisted to DB)
- **No raw content stored** — only canonical merchant names and structured financial data
- **Local SQLite only** — no cloud sync, no telemetry, no external data transmission
- **No bank integration** — by design (privacy constraint)
- **No AI/LLM** — deterministic rules only (MVP constraint)

---

## Current Architecture

```
Gmail metadata
  └── email_records table (sender, subject, date, amount, confidence, disposition)
         └── subscriptions table (name, amount, currency, cycle, status)
         └── payment_events table (event type, merchant, amount, currency, date)
```

Detection pipeline stages:
1. **Tier classification** — is the sender a known subscription service (Tier 1) or generic billing processor (Tier 2)?
2. **Pattern analysis** — RECEIPT, RENEWAL, CANCELLATION, REFUND, TRIAL, PROMOTIONAL, NOTIFICATION, NONE
3. **Amount extraction** — regex-based, supports `$`, `₪`, `€`, `£`, `¥` and text like "ILS 12.90"
4. **Cycle detection** — strong patterns (`/year`, `per month`) apply everywhere; weak patterns suppressed on body_text to prevent false ANNUAL/WEEKLY inferences
5. **Confidence scoring** — Tier × Pattern × Amount signals → DETECTED (>0.80), FLAGGED (0.40-0.80), IGNORED (<0.40)

---

## Current Features (Phase 3.4 complete)

### Backend
- **6-pass Gmail scan** — domain-based pass 1 (all modes) + keyword passes 2-6 (deep/forensic)
- **Payment events** with proper semantics: `renewal_charge`, `subscription_charge`, `refund`, `cancellation`, `trial_started`, `trial_ended`, `failed_payment`, `price_change`
- **Native currency** — ILS `₪`, USD `$`, EUR `€`, GBP `£`, JPY `¥` stored and displayed correctly
- **Billing cycle body_text restriction** — weak cycle patterns suppressed for body_text to prevent false ANNUAL/WEEKLY from marketing copy
- **Apple product disambiguation** — "Apple" sender + "Apple Music" in subject → "Apple Music" (not generic "Apple")
- **Wolt/Wolt+** — Tier 1 detection in quick/deep/forensic mode
- **Manual subscription CRUD** — create, update, delete via API
- **Payment event link/unlink** — manually associate payment events with subscriptions
- **needs_attachment_review flag** — marks Tier 1 events where amount is in a PDF attachment

### API Endpoints
- `GET /api/subscriptions` — list subscriptions (filterable by status)
- `POST /api/subscriptions` — manually create a subscription
- `POST /api/subscriptions/{id}/update` — update fields (name, amount, currency, cycle, status)
- `DELETE /api/subscriptions/{id}` — delete a subscription
- `GET /api/subscriptions/{id}` — get subscription + linked email records
- `GET /api/email-records` — list email records (filterable by disposition)
- `GET /api/payment-events` — list payment events (filterable by type, recurring, one-time)
- `POST /api/payment-events/{id}/link` — link payment event to subscription
- `POST /api/payment-events/{id}/unlink` — remove subscription link
- `GET /api/summary` — spending summary with per-currency breakdown
- `POST /api/scan` — run a synchronous scan (quick/deep mode)
- `POST /api/scan/start` — start a background scan (forensic mode)
- `GET /api/scan/status/{scan_id}` — poll background scan progress

### Dashboard
- **SpendingSummary** — monthly cost by currency; shows "—" + "N unconfirmed" when all subs are UNKNOWN; custom date range picker
- **SubscriptionTable** — two sections: Active/Trial (confirmed) vs Unconfirmed Candidates; inline edit/delete/create buttons
- **ReviewQueue** — FLAGGED emails categorized by type (candidates / unknown payments / refunds / cancellations / trials); Confirm and Dismiss per row
- **PaymentEventsTable** — financial event log; 📎 indicator for attachment-pending amounts; Link/Unlink actions

---

## How to Run

### Prerequisites

- Python 3.11+
- Node.js 18+ (for frontend)
- Google account (optional — mock mode works without Gmail)

### Backend

```bash
# Install dependencies
pip install -r requirements.txt

# Mock mode (no Gmail needed — uses built-in mock data)
python main.py --mock

# Gmail mode (requires OAuth setup — see docs/GMAIL_API_PLAN.md)
python main.py
```

The API server starts at `http://localhost:8000`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard at `http://localhost:3000`.

### Environment Variables

Copy `.env.example` to `.env` and configure:

```
DB_PATH=data/subscriptions.db
USE_MOCK=true          # set to false for Gmail mode
GOOGLE_CLIENT_ID=...   # from Google Cloud Console
GOOGLE_CLIENT_SECRET=...
```

---

## Testing

```bash
# Privacy gate (must always pass — blocks all other work)
python -m pytest tests/privacy/ -v

# All unit tests
python -m pytest tests/ -q

# Specific module
python -m pytest tests/unit/test_detector.py -q

# With integration tests (requires --integration flag)
python -m pytest tests/ --integration -q
```

Current: **515 tests passing, 1 skipped** (privacy token test requires live keyring).

### TypeScript check

```bash
cd frontend && npx tsc --noEmit
```

---

## Validation Report

After running a scan, generate a privacy-safe diagnostic report:

```bash
python scripts/validation_report.py
```

Report sections include:
- Subscriptions by status/source
- Email records breakdown
- Provider detection stats
- Billing cycle distribution
- Review Queue analysis
- Payment event semantics
- **Known Provider Coverage** — checks if Spotify, Netflix, Wolt+, etc. are detected
- **Unconfirmed Subscriptions** — UNKNOWN-status entries needing user confirmation
- **Attachment Review Queue** — events where amount is in a PDF (Phase 3.5 queue)
- UI Visibility Checklist — confirms all components and endpoints are present
- Safety Checklist — data quality gate

---

## Scan Modes

| Mode | Speed | Gmail Queries | Use when |
|------|-------|---------------|----------|
| quick | Fast | Pass 1 (domain filter) only | Daily refresh, quick check |
| deep | Medium | Passes 1-4 (domain + invoice/receipt/renewal) | Weekly, first-time setup |
| forensic | Slow (background) | All 6 passes | Initial setup, 2y+ history |

**Recommended first scan:** forensic + 2 years. Then quick + 1 month for regular refreshes.

### Scan Range

Use the preset range buttons (1m, 3m, 6m, 1y, 2y, 5y) or select "Custom range…" to
enter specific From/To dates.

---

## Manual Corrections

False positives and false negatives can be corrected from the dashboard without re-scanning:

| Situation | Fix |
|-----------|-----|
| Subscription is wrong (wrong amount/cycle) | ✏️ Edit button in SubscriptionTable |
| Subscription doesn't exist (false positive) | 🗑️ Delete button |
| Subscription was missed (false negative) | "+ Add subscription" button |
| Review Queue item is a real subscription | ✓ Confirm button → opens pre-filled form |
| Review Queue item is irrelevant | ✕ Dismiss button |
| Payment event linked to wrong subscription | Unlink → Link to correct one |

---

## Provider Coverage

### Tier 1 (auto-detected in quick mode)

Streaming: Netflix, Spotify, YouTube Premium, Apple Music, Apple TV+, Apple One, iCloud+,
Disney+, Amazon Prime Video

Productivity/Cloud: Google One, Google Play, GitHub, Notion, Canva, Figma, Slack, Zoom,
Dropbox, Microsoft 365, DigitalOcean, Heroku, Vercel

AI/SaaS: OpenAI/ChatGPT, Claude/Anthropic, Grammarly, NordVPN, LinkedIn Premium

Food/Delivery: Wolt+

Commerce: PayPal, Substack, New York Times, The Economist

### Tier 2 (billing processors — subject/amount still extracted)

Stripe, Paddle, Chargebee, FastSpring, Recurly, Braintree

### Excluded (never subscription candidates)

Amazon.com (one-time purchases), eBay, Etsy, Walmart, Shopify

---

## Known Limitations

- **Amount in HTML body/PDF** — many receipt emails have amount in HTML body or attached PDF, not in subject. The `needs_attachment_review` flag marks these for future extraction (Phase 3.5).
- **Hebrew/RTL currency** — `₪` extracted correctly; multi-language subjects are supported.
- **No Outlook/IMAP** — Gmail only for now (schema supports other providers).
- **No AI/LLM** — deterministic rules only. Works well for known providers; misses exotic patterns.
- **No bank integration** — by design (privacy constraint). Amount accuracy depends on email metadata.
- **ANNUAL subscriptions** — older than the scan range will be missed. Use forensic + 2y for full coverage.

---

## Roadmap

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Repo scaffold | Complete |
| 1 | Mock data + local detection engine | Complete |
| 2 | Gmail OAuth integration | Complete |
| 3.0 | HTML body extraction fixes | Complete |
| 3.1 | payment_events + native currency + subscription linking | Complete |
| 3.2 | Provider-specific parsers (Hebrew, ILS) | Complete |
| 3.3A/B | Payment event semantics, billing cycle fixes, frontend PaymentEventsTable | Complete |
| **3.4** | **Provider expansion (Wolt+, Apple Music), manual CRUD, review queue UX, custom date range** | **Complete** |
| 3.5 | PDF/attachment amount extraction, reprocessing mode, user corrections table | Planned |
| Future | Multi-account UI, AI-assisted parsing, Outlook/IMAP | Not planned |

---

## Architecture Decisions

**Why not store email body?**
Privacy: email body often contains sensitive content (invoices, personal data). Subject + sender + date is sufficient for 80%+ of subscription detection. Body-based extraction is reserved for forensic mode (ephemeral, never stored).

**Why SQLite?**
Local-first. No cloud dependency. Simple backup (copy the file). Sufficient for personal use scale.

**Why deterministic rules over AI?**
Deterministic rules are auditable, predictable, and privacy-safe. AI/LLM would require sending email metadata to an external API (privacy violation) or running locally (complexity). Documented as a future option if deterministic rules prove insufficient.

**Why POST for update instead of PUT?**
CORS configuration allows GET, POST, DELETE. Using POST with `/update` suffix avoids adding a new method to the CORS whitelist.
