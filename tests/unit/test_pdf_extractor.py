"""
Unit tests for backend/parser/pdf_extractor.py (Phase 3.7).

Exercises the full pipeline: synthetic text PDF → pdfminer.six text extraction →
structured field parsing. Also asserts the privacy guarantee: no raw PDF text leaks
into the returned PdfEvidence.
"""
import re

import pytest

from backend.parser.pdf_extractor import (
    PdfEvidence,
    classify_attachment,
    extract_pdf_fields,
    is_parseable_pdf,
    MAX_PDF_BYTES,
)
from tests.fixtures.pdf_factory import make_text_pdf, make_empty_image_pdf


# ── Attachment classification (metadata only) ───────────────────────────────────

def test_classify_pdf_invoice_by_filename():
    assert classify_attachment("Invoice_Jan2026.pdf", "application/pdf") == "PDF_INVOICE"


def test_classify_pdf_receipt_by_filename():
    assert classify_attachment("receipt.PDF", None) == "PDF_RECEIPT"


def test_classify_generic_pdf():
    assert classify_attachment("statement.pdf", "application/pdf") == "PDF_OTHER"


def test_classify_image_attachment():
    assert classify_attachment("photo.png", "image/png") == "IMAGE"


def test_classify_unsupported_attachment():
    assert classify_attachment("", "") == "UNSUPPORTED"


def test_is_parseable_pdf():
    assert is_parseable_pdf("PDF_INVOICE")
    assert is_parseable_pdf("PDF_RECEIPT")
    assert not is_parseable_pdf("IMAGE")
    assert not is_parseable_pdf("UNSUPPORTED")


# ── Core extraction ─────────────────────────────────────────────────────────────

def test_invoice_extracts_amount_currency_provider_date():
    pdf = make_text_pdf([
        "ACME Cloud Storage",
        "Invoice Number: INV-2026-0042",
        "Invoice Date: January 15, 2026",
        "Your subscription will auto-renew.",
        "Total Amount Due: $9.99",
    ])
    ev = extract_pdf_fields(pdf)
    assert ev.extraction_status == "OK"
    assert ev.amount == 9.99
    assert ev.currency == "USD"
    assert ev.provider == "ACME Cloud Storage"
    assert ev.invoice_date == "2026-01-15"
    assert ev.invoice_number == "INV-2026-0042"


def test_total_preferred_over_subtotal_and_tax():
    pdf = make_text_pdf([
        "ServiceCo",
        "Subtotal: $9.00",
        "Tax: $0.99",
        "Total Amount Due: $9.99",
    ])
    ev = extract_pdf_fields(pdf)
    assert ev.amount == 9.99          # total, not the $9.00 subtotal
    assert ev.tax_amount == 0.99


def test_billing_period_infers_monthly_cycle():
    pdf = make_text_pdf([
        "ACME", "Billing Period: 2026-01-15 to 2026-02-14",
        "subscription", "Total: $9.99",
    ])
    ev = extract_pdf_fields(pdf)
    assert ev.billing_period_start == "2026-01-15"
    assert ev.billing_period_end == "2026-02-14"
    assert ev.inferred_cycle == "MONTHLY"
    assert "cycle_from_period" in ev.evidence_reasons


def test_annual_period_infers_annual_cycle():
    pdf = make_text_pdf([
        "ProTool", "Service Period: 2026-01-01 - 2026-12-31",
        "Auto-renews yearly.", "Amount paid: 120.00 USD",
    ])
    ev = extract_pdf_fields(pdf)
    assert ev.inferred_cycle == "ANNUAL"
    assert ev.amount == 120.00
    assert ev.currency == "USD"


def test_ils_invoice_currency():
    pdf = make_text_pdf(["Spotify Premium", "Total: 19.90 ILS", "monthly subscription"])
    ev = extract_pdf_fields(pdf)
    assert ev.amount == 19.90
    assert ev.currency == "ILS"
    assert ev.inferred_cycle == "MONTHLY"


def test_recurring_wording_contributes_evidence():
    pdf = make_text_pdf(["CloudCo", "This subscription will auto-renew monthly.", "Total: $5.00"])
    ev = extract_pdf_fields(pdf)
    assert ev.has_recurring_evidence() is True
    assert "auto_renew" in ev.subscription_indicators
    assert "recurring_wording_in_pdf" in ev.evidence_reasons


def test_receipt_without_recurring_evidence_is_not_confirmable():
    """A bare receipt (amount, no recurring signal) must not look like a subscription."""
    pdf = make_text_pdf(["Hardware Store", "Receipt", "Total: $45.00"])
    ev = extract_pdf_fields(pdf)
    assert ev.amount == 45.00
    assert ev.has_recurring_evidence() is False
    assert "receipt_one_time_no_recurring" in ev.penalty_reasons
    assert ev.confidence_score < 0.70   # never confirmation-grade on its own


def test_refund_pdf_detected_as_refund():
    pdf = make_text_pdf(["BigCo", "Refund issued to your card", "Total refunded: $20.00"])
    ev = extract_pdf_fields(pdf)
    assert ev.is_refund() is True
    assert "refund_detected" in ev.penalty_reasons


def test_cancellation_pdf_detected():
    pdf = make_text_pdf(["StreamCo", "Cancellation confirmation", "Your plan has been cancelled."])
    ev = extract_pdf_fields(pdf)
    assert "cancellation_detected" in ev.penalty_reasons


# ── Failure modes (must never raise) ─────────────────────────────────────────────

def test_none_bytes_returns_failed():
    ev = extract_pdf_fields(None)
    assert ev.extraction_status == "FAILED"
    assert ev.amount is None


def test_corrupt_bytes_returns_safe_failure():
    ev = extract_pdf_fields(b"\x00\x01\x02 this is not a pdf at all")
    assert ev.extraction_status in ("FAILED", "NO_TEXT")
    assert ev.amount is None


def test_empty_image_pdf_returns_no_text():
    ev = extract_pdf_fields(make_empty_image_pdf())
    assert ev.extraction_status == "NO_TEXT"
    assert "pdf_no_text_image_only" in ev.penalty_reasons


def test_oversized_pdf_returns_failed():
    ev = extract_pdf_fields(b"%PDF-1.4" + b"x" * (MAX_PDF_BYTES + 1))
    assert ev.extraction_status == "FAILED"
    assert "pdf_too_large" in ev.penalty_reasons


# ── Privacy: no raw text leaks into structured fields ────────────────────────────

def test_no_raw_pdf_text_in_evidence_fields():
    """A distinctive body sentence must not appear in any persisted PdfEvidence field."""
    marker = "ZQXMARKERZQX detailed legal terms and conditions apply herein"
    pdf = make_text_pdf([
        "ACME Cloud", "Total: $9.99", "subscription auto-renew", marker,
    ])
    ev = extract_pdf_fields(pdf)
    blob = " ".join([
        ev.provider or "", ev.product_name or "", ev.currency or "",
        ev.invoice_number or "", ev.inferred_cycle or "",
        ev.invoice_date or "", ev.payment_date or "",
        ev.billing_period_start or "", ev.billing_period_end or "",
        " ".join(ev.subscription_indicators),
        " ".join(ev.evidence_reasons),
        " ".join(ev.missing_evidence),
        " ".join(ev.penalty_reasons),
    ])
    assert "ZQXMARKER" not in blob, "raw PDF text leaked into a structured field"


def test_pdf_evidence_dataclass_has_no_raw_text_field():
    """The result type must not expose any raw text / body / html / snippet field."""
    fields = set(PdfEvidence.__dataclass_fields__.keys())
    prohibited = {"text", "raw_text", "body", "html", "snippet", "content", "full_text"}
    assert fields.isdisjoint(prohibited), f"PdfEvidence exposes raw-text field(s): {fields & prohibited}"


def test_reason_tokens_are_short_coded_strings():
    """All *_reasons / *_indicators tokens must be short coded identifiers, not PDF sentences."""
    pdf = make_text_pdf([
        "ACME Cloud", "Billing Period: 2026-01-01 - 2026-12-31",
        "Invoice Number: INV-1", "Auto-renews yearly.", "Total Amount Due: $120.00",
    ])
    ev = extract_pdf_fields(pdf)
    token_re = re.compile(r"^[a-z0-9_]+$")
    for tok in (ev.evidence_reasons + ev.missing_evidence
                + ev.penalty_reasons + ev.subscription_indicators):
        assert token_re.match(tok), f"reason token is not a coded identifier: {tok!r}"
        assert len(tok) <= 40
