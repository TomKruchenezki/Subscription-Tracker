# Real Gmail Scan Validation

A living document to fill in during each real Gmail scan session.
Compare results against the Pre-Scan Checklist and note any false positives, false negatives, or blocking issues.

**Privacy reminder:** Never paste email subjects or sender addresses into this file. Record service names and scan statistics only.

---

## Pre-Scan Checklist

Fill in before running any Gmail scan. This is your ground-truth reference.

| Service | Approx. amount | Billing cycle | Status | Expected detection |
|---------|---------------|---------------|--------|--------------------|
|         |               |               |        |                    |
|         |               |               |        |                    |
|         |               |               |        |                    |

**Detection key:**
- `DETECTED` — should auto-appear in subscriptions table
- `FLAGGED` — acceptable in Review Queue; needs manual review
- `CANCELLED` — should appear with status=CANCELLED after a historical scan

---

## Scan Sessions

Copy one session block per scan run.

---

### Session — quick + 1m

**Date:**
**Mode:** quick  **Range:** 1m

**Last-scan card numbers:**

| Metric | Value |
|--------|-------|
| Scanned | |
| Detected | |
| Flagged for review | |
| Ignored | |

**Subscriptions table (GMAIL rows only):**

| Service detected | Amount | Cycle | Status | On checklist? |
|------------------|--------|-------|--------|---------------|
|                  |        |       |        |               |

**Review Queue (GMAIL rows only):**

| Count of GMAIL flagged rows | |
| Highest confidence score seen | |
| Lowest confidence score seen | |

**Backend terminal — notable lines:**
```
# Paste relevant log lines here (stats only — no subjects/senders)
# e.g.:
# Collected X unique message IDs across 2 passes
# Fetched metadata for X emails
# Any WARNING lines
```

**Pass criteria check:**
- [ ] No server crash or unhandled exception
- [ ] scanned > 0
- [ ] No HttpError 401/403 in terminal
- [ ] At least 1 checklist item appeared (detected or flagged)
- [ ] Privacy tests still green: `pytest tests/privacy/ -v`

**Issues noted:**

**Safe to advance to deep + 3m?** yes / no

---

### Session — deep + 3m

**Date:**
**Mode:** deep  **Range:** 3m

**Last-scan card numbers:**

| Metric | Value | Delta vs. quick+1m |
|--------|-------|--------------------|
| Scanned | | |
| Detected | | |
| Flagged for review | | |
| Ignored | | |

**New subscriptions (not in quick+1m):**

| Service | Amount | Cycle | Status |
|---------|--------|-------|--------|
|         |        |       |        |

**Dedup check (run this SQLite query):**
```sql
SELECT name, COUNT(*) as cnt FROM subscriptions
WHERE source_provider = 'GMAIL'
GROUP BY name HAVING cnt > 1;
```
Result (rows returned): ____  (expected: 0)

**Backend terminal — notable lines:**
```
```

**Pass criteria check:**
- [ ] No server crash or unhandled exception
- [ ] detected ≥ quick+1m detected count
- [ ] No duplicate subscription rows (dedup query returns 0)
- [ ] No rate-limit errors (HTTP 429)
- [ ] Privacy tests still green

**Issues noted:**

**Safe to advance to deep + 6m?** yes / no

---

### Session — deep + 6m

**Date:**
**Mode:** deep  **Range:** 6m

**Last-scan card numbers:**

| Metric | Value | Delta vs. deep+3m |
|--------|-------|-------------------|
| Scanned | | |
| Detected | | |
| Flagged for review | | |
| Ignored | | |

**Cancelled subscriptions found:**

| Service | cancelled_at populated? | first_charge_date populated? |
|---------|------------------------|------------------------------|
|         |                        |                              |

**SQLite queries to run:**
```sql
-- Source breakdown
SELECT source_provider, disposition, COUNT(*) as cnt
FROM email_records GROUP BY source_provider, disposition;

-- First charge date coverage
SELECT COUNT(*) as has_first_charge FROM subscriptions
WHERE source_provider = 'GMAIL' AND first_charge_date IS NOT NULL;

-- Cancelled subscriptions
SELECT name, status, cancelled_at FROM subscriptions
WHERE source_provider = 'GMAIL' AND status = 'CANCELLED';
```

Results:
```
```

**Pass criteria check:**
- [ ] No server crash
- [ ] 6m results are a superset of 3m results (detected ≥ deep+3m)
- [ ] No duplicate rows
- [ ] No persistent 429 errors
- [ ] Privacy tests still green

**Issues noted:**

**Safe to advance to deep + 1y?** yes / no

---

### Session — deep + 1y

**Date:**
**Mode:** deep  **Range:** 1y

**Last-scan card numbers:**

| Metric | Value | Delta vs. deep+6m |
|--------|-------|-------------------|
| Scanned | | |
| Detected | | |
| Flagged for review | | |
| Ignored | | |

**first_charge_date range:**
- Earliest: ____
- Latest: ____

**New subscriptions (not in 6m scan):**

| Service | Amount | Cycle | Status |
|---------|--------|-------|--------|
|         |        |       |        |

**Issues noted:**

---

## False Positive Log

Record emails that were DETECTED or FLAGGED but are NOT real subscriptions.

| Date | Service/Sender domain | Confidence score | event_type | Likely reason | Action |
|------|-----------------------|-----------------|------------|---------------|--------|
|      |                       |                 |            |               |        |

**Common false positive patterns:**
- One-time purchases (Amazon, eBay, Etsy, Square)
- Promotional / discount emails
- Newsletter signups without a billing event
- Bank transaction confirmation emails

---

## False Negative Log

Record known subscriptions (from checklist) that did NOT appear after the expected scan range.

| Service | Expected by range | Found in detected? | Found in flagged? | Notes |
|---------|------------------|--------------------|-------------------|-------|
|         |                  |                    |                   |       |

**Common false negative causes:**
- Sender domain not in Tier 1 (most common)
- Subject line matches no pass query
- Emails older than scan range
- Low-volume service (only 1–2 emails per year)

---

## Review Queue Inspection Protocol

After each scan, run through these steps at `/review`:

1. **Count GMAIL rows** — visually scan the Source column for green GMAIL badges
2. **Group by confidence band:**
   - 70%+ and FLAGGED: potential detection bug (should have been DETECTED)
   - 40–55%: expected marginal flags — review the `short_evidence` text
   - Below 40%: should not appear (threshold gate); if present, report as blocking bug
3. **Check `event_type` distribution:** if many rows say `unknown_payment` from the same sender, that sender is a Tier 1 candidate
4. **Spot-check `short_evidence`:** does the detection reason make sense for the email?
5. **Note any known services** appearing as FLAGGED instead of DETECTED — these need confidence calibration

---

## Backend Log Reference

**Good signs:**
```
Starting Gmail scan: mode=deep, passes=[1, 2, 3, 4], max=2000
Pass 1 query: from:(netflix.com OR spotify.com OR ...)
Collected 127 unique message IDs across 4 passes
Fetched metadata for 127 emails
Processed abc123: score=0.85 disposition=DETECTED name=Netflix
```

**Warning signs and what they mean:**

| Log line | Meaning | Action |
|----------|---------|--------|
| `WARNING Failed to fetch ... HttpError 429` | Rate limited by Gmail API | Retry with smaller range; backoff is working |
| `WARNING Failed to fetch ... HttpError 401` | OAuth token expired or revoked | Reconnect Gmail at /accounts |
| `WARNING Failed to fetch ... HttpError 403` | Wrong scope or revoked access | Check GCP consent screen; reconnect |
| `Message cap 500 reached at pass 1` | quick mode cap hit (expected) | Normal for quick mode with large mailbox |
| `Processed X: score=0.40 disposition=FLAGGED` | Marginal detection, went to Review Queue | Expected |

**Enabling debug logs** (more detail, only for troubleshooting):
```bash
python main.py --debug
```
DEBUG logs include: per-skipped-message reasons (no From header, unparseable Date).

---

## SQLite Quick Reference

Open the database:
```bash
sqlite3 data/subscriptions.db
```

**Essential validation queries:**
```sql
-- All Gmail subscriptions
SELECT name, amount, billing_cycle, status, source_provider, first_charge_date
FROM subscriptions WHERE source_provider = 'GMAIL'
ORDER BY last_charge_date DESC;

-- Duplicate subscription check (expected: 0 rows)
SELECT name, COUNT(*) as cnt FROM subscriptions
GROUP BY name HAVING cnt > 1;

-- Email counts by source + disposition
SELECT source_provider, disposition, COUNT(*) as cnt
FROM email_records GROUP BY source_provider, disposition;

-- Flagged Gmail emails sorted by confidence
SELECT sender_address, subject, confidence_score, event_type, amount_extracted, short_evidence
FROM email_records
WHERE disposition = 'FLAGGED' AND source_provider = 'GMAIL'
ORDER BY confidence_score DESC;

-- Subscriptions missing charge dates
SELECT name, first_charge_date, last_charge_date FROM subscriptions
WHERE source_provider = 'GMAIL' AND first_charge_date IS NULL;
```

---

## Blocking Bugs

Stop all work and investigate immediately if any of these occur:

| Symptom | Likely cause |
|---------|-------------|
| `HttpError 401` on every message fetch | Refresh token expired or revoked — reconnect at /accounts |
| `HttpError 403` on every message fetch | Scope mismatch or consent revoked — check GCP |
| Duplicate subscription rows (dedup query > 0) | Dedup logic broken — do not widen scan range |
| `scanned=0` with no terminal error | Gmail query returning zero results; check date range and mailbox |
| Server 500 on `/api/scan` | Unhandled exception; read full traceback in terminal |
| Known subscription with amount showing as IGNORED consistently | Scoring threshold issue — check confidence scores in debug log |
| Any `tests/privacy/` test failing | Stop everything; privacy gate must stay green |

---

## Backlog (observe and record, do not fix during validation)

| Observation | Backlog item | Owner |
|-------------|-------------|-------|
| Known subscription sender missing from Tier 1 | Add domain to Tier 1 sender list | subscription-detection-specialist |
| Known service scoring 0.40–0.55 (flagged, not detected) | Confidence floor calibration | subscription-detection-specialist |
| One-time purchase appearing in Review Queue | Domain exclusion or pattern blocker | subscription-detection-specialist |
| Amount extraction failing for a specific receipt format | Parser improvement | email-parser-specialist |
| Hundreds of Review Queue rows after forensic scan | Expected; precision tuning is ongoing | subscription-detection-specialist |
| `first_charge_date` null for old subscriptions | Date extraction from subject text | email-parser-specialist (Phase 3) |
| Scan taking > 30s for deep + 6m | Progress indicator UI | Phase 2 backlog |
| Persistent 429 rate limiting | Reduce concurrency or add longer delays | gmail-integration-specialist |

---

## Safety Criteria: When to Increase Range

Before advancing to the next scan range, **all** of the following must be true:

- [ ] No server crash or unhandled exception at current range
- [ ] `scanned > 0` and results look plausible (known subscriptions visible)
- [ ] No duplicate subscription rows (dedup SQL query returns 0)
- [ ] No `HttpError 401` or `403` in the terminal log
- [ ] No persistent 429 errors (occasional is OK — backoff is working)
- [ ] `pytest tests/privacy/ -v` passes
- [ ] At least one item from the Pre-Scan Checklist was detected or flagged
