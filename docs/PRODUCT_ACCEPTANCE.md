# Product Acceptance

Rules for deciding when a feature/phase is actually *done*. `CLAUDE.md` keeps the one-line
version; this is the detail. Invoke the `product-acceptance-reviewer` agent before marking
any feature-phase complete.

---

## User-visible acceptance criteria (every product feature)

Every feature must specify **where the user sees it in the app**. If a change is intentionally
backend-only (e.g. a schema migration or internal refactor), say so explicitly and confirm that
scope with the user. "The validation report shows it" is **not** sufficient unless the feature
is explicitly scoped as backend-only.

## Product acceptance gate (before marking a phase complete)

Answer all four:

1. **What changed for the user?** — be specific: which screen / section.
2. **Which API endpoint or UI component exposes it?**
3. **How can the user verify it** without running a script or reading code?
4. **Is `validation_report.py` the only visible evidence?** If yes, is that accepted scope?

## No invisible feature completion

A phase is **not** complete if its new capability exists only in backend code, the DB schema,
or `validation_report.py` output — unless the phase was explicitly scoped as backend-only and
the user confirmed that scope *before* implementation began.

## Detection features must be explainable and correctable

A detection feature is not complete unless the user can:

1. See **why** an item was detected/flagged — `decision_reason`, `evidence_summary`.
2. See **what is missing** for full confidence — `missing_evidence`.
3. See **what to do** — `suggested_action`.
4. **Correct** false positives/negatives — and corrections persist across future scans and reprocessing.

### Attachment / PDF detection (Phase 3.7)

Additionally not complete unless: the user can see **why the attachment mattered**; can correct
the detected provider/product/status; **raw PDF text is never stored** (only structured fields +
coded reason tokens); and **reprocessing respects the user's correction**.
