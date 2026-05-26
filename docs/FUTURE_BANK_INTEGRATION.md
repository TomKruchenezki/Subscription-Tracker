# Future Bank Integration

**Status: NOT MVP — Do not implement any bank integration code.**

This document is planning-only. No bank connection code exists or should exist anywhere
in the codebase. This file captures the design intent so that future architectural
decisions do not inadvertently foreclose the option.

---

## Why Bank Integration Is Not in MVP

**Higher security surface:**
Bank API tokens (Plaid, Teller) grant access to full transaction history, account balances,
and in some configurations account numbers. This is a significantly higher trust requirement
than a Gmail read-only token, which exposes only email metadata.

**Privacy design complexity:**
Bank transaction descriptions often contain merchant names, location codes, and reference
numbers that qualify as PII. Handling these requires more careful data minimization design
than the Gmail metadata approach.

**MVP proves value without it:**
The Gmail-based approach can detect 80%+ of subscription charges from email receipts alone.
Adding bank data is an enhancement, not a foundation requirement.

**Explicit rule:**
No code path in the application may import Plaid, Teller, or any bank API client library
until a separate product milestone is approved and a full privacy review is completed.

---

## When to Revisit

Bank integration becomes worth revisiting when:
1. The Gmail detection approach has been in production and its recall ceiling is understood
2. Users are actively asking for detection of subscriptions that don't send email receipts
3. A privacy-preserving design for bank data has been specified and reviewed

This milestone would require its own product spec, privacy review, and roadmap entry.

---

## Future Design Principles (If Implemented)

These are the constraints any future bank integration must satisfy:

**Read-only access only.**
Use Plaid `transactions:read` or Teller transactions endpoint. Never request transfer,
payment, or account management scopes.

**Data minimization.**
Store only: `amount`, `date`, `merchant_name`, `category` (as resolved by the bank API).
Do not store full transaction descriptions if they contain location codes or reference
numbers that qualify as PII.

**Separate opt-in consent.**
Bank connection requires a distinct, explicit user action separate from Gmail authorization.
The UI must clearly explain what bank data will be collected and stored before the user
authorizes.

**Encrypted token storage.**
Bank API tokens use the same encrypted-at-rest approach as Gmail tokens, with an
additional encryption layer given the higher sensitivity.

**No credential storage.**
Bank login credentials (username/password) must never be stored. OAuth-based bank
connections (Plaid Link, Teller Connect) are the only acceptable method.

**Separate deletion path.**
`--delete-all` must revoke the bank connection and delete all bank-sourced records
independently of the Gmail data.

---

## Plaid vs Teller Comparison (For Future Evaluation)

| Property | Plaid | Teller |
|---|---|---|
| Bank coverage | Very broad (US, CA, EU) | US only |
| Auth model | OAuth via Plaid Link | Direct bank OAuth |
| Transaction data | `transactions` product | Transactions API |
| Privacy model | Aggregator (Plaid sees data) | Direct (no intermediary) |
| Pricing | Per-item monthly fee | Usage-based |
| Maturity | Established, well-documented | Newer, simpler API |

No decision is made here. This comparison is for future planning reference.

---

## Architecture Consideration

The `backend/sources/` directory is intentionally designed as a source abstraction layer.
Current sources: `mock.py`, `gmail.py`. A future bank source would follow the same pattern:

```python
# backend/sources/plaid.py  (future — does not exist yet)
class PlaidSource:
    def fetch_transactions(self, since: datetime) -> List[TransactionRecord]:
        ...
```

`TransactionRecord` would be a separate dataclass from `EmailMetadata`, feeding into
a parallel detection path rather than reusing the email detection pipeline.

Cross-source deduplication (same subscription detected from both email receipt and bank
charge) would be a feature of Phase 4+, not implicit in the data model.
