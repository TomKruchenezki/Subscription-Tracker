---
name: scan-diagnosis
description: Analyzes validation_report output or scan screenshots to identify false positives, false negatives, currency/cycle errors, missing amounts, and recommend next phase.
---

# Scan Diagnosis Skill

You are analyzing the output of `python scripts/validation_report.py` or a screenshot
of the dashboard after a real Gmail scan. Produce a structured diagnosis.

## Step 1 — Parse the Report

Identify and record:
- Total emails scanned, detected, flagged, ignored
- Number of ACTIVE, UNKNOWN, CANCELLED subscriptions
- Subscriptions with missing amounts (status UNKNOWN instead of ACTIVE)
- Review Queue size and confidence band distribution
- Payment events count by event_type (if present)

## Step 2 — False Positive Analysis

For each item in DETECTED or FLAGGED that looks suspicious:
- Service name + confidence score
- Why it is likely a false positive (no billing language, one-time purchase, notification email)
- Recommended fix: add NOTIFICATION pattern, PROMOTIONAL pattern, or domain exclusion

## Step 3 — False Negative Analysis

Cross-reference known subscriptions against detected results:
- Which expected subscriptions are missing entirely?
- Are they in the Review Queue (FLAGGED) or completely absent from email_records?
- Likely causes: sender not in Tier 1, subject doesn't match any pattern, date range too narrow

## Step 4 — Currency and Cycle Errors

For each DETECTED subscription:
- Is the currency correct? (ILS subscriptions showing USD = Bug 2 regression)
- Is the billing cycle correct? (ANNUAL for a known monthly subscription = cycle detector mismatch)
- Is the amount realistic? ($1.07/mo for Spotify is a symptom of ILS→USD + ANNUAL corruption)

## Step 5 — Missing Amount / Product / Provider

- Which subscriptions have NULL amount? (status will show UNKNOWN instead of ACTIVE)
- Are canonical names correct? ("Google" vs "Google One" vs "Google Play")
- Are any senders scoring Tier 0 when they should be Tier 1?

## Step 6 — Recommend Next Phase

Based on the above:
- State the top 1–2 problems worth addressing next
- Identify which phase in `docs/NEXT_STEPS.md` addresses them
- If a new problem is found that is not in NEXT_STEPS.md, describe it clearly for the backlog
