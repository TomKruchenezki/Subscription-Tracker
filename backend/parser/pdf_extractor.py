"""
backend/parser/pdf_extractor.py — Phase 3.7

Safe, transient PDF receipt/invoice parsing.

PRIVACY (non-negotiable):
  - PDF bytes and the extracted text are used ONLY in memory, ONLY for the duration
    of a single extract_pdf_fields() call.
  - This module NEVER returns, stores, or logs raw PDF text or raw bytes.
  - Only the structured PdfEvidence dataclass (amounts, dates, ISO cycle, and SHORT
    CODED reason tokens) leaves this module. Callers persist only those fields.
  - No network calls — pdfminer.six is a local parser.

The text is treated as a transactional billing document. Amount/currency extraction
and billing-cycle detection reuse the existing parsers (amount_extractor, cycle_detector)
so behavior stays consistent with subject/body parsing.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO

from backend.parser.amount_extractor import extract_amount
from backend.parser.cycle_detector import detect_cycle

logger = logging.getLogger(__name__)

PARSER_VERSION = "pdf-1.0"

# Bounds: skip oversized attachments; cap scanned text (memory + regex cost + privacy surface).
MAX_PDF_BYTES = 10 * 1024 * 1024   # 10 MB
_MAX_TEXT_CHARS = 20_000


# ── Structured result (ephemeral; only these fields are ever persisted) ─────────

@dataclass
class PdfEvidence:
    """Structured PDF-derived evidence. NEVER carries raw PDF text.

    extraction_status: OK | NO_TEXT | NO_FIELDS | FAILED
    *_indicators / *_reasons are SHORT CODED TOKENS, never PDF sentences.
    """
    extraction_status: str = "FAILED"
    provider: str | None = None
    product_name: str | None = None
    amount: float | None = None
    currency: str | None = None
    invoice_date: str | None = None
    payment_date: str | None = None
    billing_period_start: str | None = None
    billing_period_end: str | None = None
    inferred_cycle: str | None = None
    tax_amount: float | None = None
    invoice_number: str | None = None
    subscription_indicators: list[str] = field(default_factory=list)
    evidence_reasons: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    penalty_reasons: list[str] = field(default_factory=list)
    confidence_score: float = 0.0
    parser_version: str = PARSER_VERSION

    def has_recurring_evidence(self) -> bool:
        """True when the PDF shows recurring/subscription signals (not a bare receipt)."""
        if self.inferred_cycle and self.inferred_cycle != "UNKNOWN":
            return True
        return any(
            t in self.subscription_indicators
            for t in ("auto_renew", "subscription", "recurring", "renews")
        )

    def is_refund(self) -> bool:
        return "refund_detected" in self.penalty_reasons


# ── Attachment classification (metadata only — no content needed) ───────────────

_PDF_MIME = "application/pdf"
_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".bmp", ".tiff")


def classify_attachment(filename: str | None, mime_type: str | None) -> str:
    """Return detected_attachment_type from filename + mime_type only.

    One of: PDF_INVOICE | PDF_RECEIPT | PDF_OTHER | IMAGE | OTHER | UNSUPPORTED
    """
    fn = (filename or "").lower()
    mt = (mime_type or "").lower()

    is_pdf = mt == _PDF_MIME or fn.endswith(".pdf")
    if is_pdf:
        if re.search(r"invoice|fattura|rechnung|facture|חשבונית", fn):
            return "PDF_INVOICE"
        if re.search(r"receipt|recibo|quittung|קבלה", fn):
            return "PDF_RECEIPT"
        return "PDF_OTHER"

    if mt.startswith("image/") or fn.endswith(_IMAGE_EXTS):
        return "IMAGE"

    if mt or fn:
        return "OTHER"
    return "UNSUPPORTED"


def is_parseable_pdf(detected_type: str) -> bool:
    """True for PDF types we attempt to text-parse (images need OCR — not in scope)."""
    return detected_type in ("PDF_INVOICE", "PDF_RECEIPT", "PDF_OTHER")


# ── Field-extraction regexes (run on transient text) ────────────────────────────

# Lines that name a payable total. We run extract_amount() on each matching line.
_TOTAL_LINE_RE = re.compile(
    r"grand\s+total|amount\s+(?:due|paid|charged|payable)|total\s+(?:due|paid|amount|charged)?"
    r"|balance\s+due|you\s+(?:paid|were\s+charged)|total\b"
    r'|סה"?כ|סך\s+הכל|לתשלום',
    re.IGNORECASE,
)
_TAX_LINE_RE = re.compile(r"\b(?:tax|vat|gst)\b|מע\"?מ", re.IGNORECASE)

_INVOICE_NO_RE = re.compile(
    r"(?:invoice|receipt|order|confirmation)\s*(?:#|no\.?|number|num|id)\s*[:\-]?\s*"
    r"([A-Za-z0-9][A-Za-z0-9\-]{3,})",
    re.IGNORECASE,
)

_INVOICE_DATE_RE = re.compile(
    r"(?:invoice\s+date|date\s+of\s+invoice|issued?(?:\s+on)?|invoice\s+issued|תאריך\s+חשבונית)"
    r"\s*[:\-]?\s*(.+?)(?:\n|$)",
    re.IGNORECASE,
)
_PAYMENT_DATE_RE = re.compile(
    r"(?:date\s+paid|payment\s+date|paid\s+on|charged\s+on|date\s+of\s+payment|תאריך\s+תשלום)"
    r"\s*[:\-]?\s*(.+?)(?:\n|$)",
    re.IGNORECASE,
)
_PERIOD_RE = re.compile(
    r"(?:billing|service|subscription|coverage|plan)\s+period\s*[:\-]?\s*(.+?)(?:\n|$)"
    r"|(?:for\s+the\s+period)\s*[:\-]?\s*(.+?)(?:\n|$)",
    re.IGNORECASE,
)

# Provider/product heuristics. The first plausible non-label line of an invoice is
# almost always the merchant name. An explicit "Plan: X" label gives the product.
_PROVIDER_SKIP_RE = re.compile(
    r"invoice|receipt|date|total|amount|subtotal|\btax\b|vat|period|number|paid|charged"
    r"|חשבונית|קבלה|סה\"?כ|תאריך",
    re.IGNORECASE,
)
_PRODUCT_LABEL_RE = re.compile(
    r"(?:plan|product|description|item)\s*[:\-]\s*(.+?)(?:\n|$)", re.IGNORECASE
)

# A single date token in common invoice formats.
_DATE_TOKEN_RE = re.compile(
    r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})"                              # 2026-01-15 / 2026/1/5
    r"|(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})"                           # 15/01/2026 or 01/15/26
    r"|([A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4})"                    # January 15, 2026 / Jan 15 2026
    r"|(\d{1,2}\s+[A-Za-z]{3,9}\.?\s+\d{4})",                     # 15 January 2026
)

# Separator between two period dates. The bare ASCII hyphen must have surrounding
# whitespace so it does NOT split inside ISO dates like "2026-01-15".
_PERIOD_SPLIT_RE = re.compile(
    r"\s*(?:–|—)\s*|\s+(?:to|through|until|עד)\s+|\s+-\s+", re.IGNORECASE
)

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Subscription / recurring indicators (coded).
_INDICATOR_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"auto[\s-]?renew|automatically\s+renew|renews?\s+(?:on|automatically)|next\s+(?:billing|payment|charge)|הוראת\s+קבע|חידוש\s+אוטומטי", re.IGNORECASE), "auto_renew"),
    (re.compile(r"\bsubscription\b|\bמנוי\b", re.IGNORECASE), "subscription"),
    (re.compile(r"\brecurring\b", re.IGNORECASE), "recurring"),
    (re.compile(r"\bmembership\b", re.IGNORECASE), "membership"),
]
_REFUND_RE = re.compile(r"\brefund(?:ed)?\b|credit\s+note|\bזיכוי\b|\bהחזר\b", re.IGNORECASE)
_CANCEL_RE = re.compile(r"\bcancell?(?:ation|ed)?\b|\bביטול\b", re.IGNORECASE)
_TRIAL_RE = re.compile(r"\bfree\s+trial\b|\btrial\s+period\b|\btrial\b|\bתקופת\s+ניסיון\b", re.IGNORECASE)


# ── Transient text extraction (private; result must not be persisted/logged) ────

def _extract_text_transient(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes IN MEMORY for transient use only.

    The returned text MUST NOT be stored, logged, or returned by callers — it is
    consumed entirely within extract_pdf_fields() and then discarded.
    """
    from pdfminer.high_level import extract_text  # local import keeps dep optional at import time
    text = extract_text(BytesIO(pdf_bytes)) or ""
    return text[:_MAX_TEXT_CHARS]


def _parse_date_token(token: str) -> str | None:
    """Best-effort parse of a single date token → ISO 'YYYY-MM-DD', or None."""
    token = (token or "").strip().strip(".,")
    if not token:
        return None
    m = _DATE_TOKEN_RE.search(token)
    if not m:
        return None
    raw = next((g for g in m.groups() if g), None)
    if not raw:
        return None
    raw = raw.strip().rstrip(",")

    # ISO-ish: YYYY-MM-DD / YYYY/MM/DD
    iso = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", raw)
    if iso:
        y, mo, d = (int(x) for x in iso.groups())
        return _safe_iso(y, mo, d)

    # Numeric DD/MM/YYYY or MM/DD/YYYY (ambiguous — prefer DD/MM, fall back to MM/DD)
    num = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})$", raw)
    if num:
        a, b, y = (int(x) for x in num.groups())
        if y < 100:
            y += 2000
        # Prefer day-first (international/Israeli); if day>12 it must be DD/MM.
        if a > 12 and b <= 12:
            return _safe_iso(y, b, a)
        if b > 12 and a <= 12:
            return _safe_iso(y, a, b)
        # Both <= 12: ambiguous — assume DD/MM (most invoices outside the US).
        return _safe_iso(y, b, a)

    # "Month DD, YYYY" / "Mon DD YYYY"
    mdy = re.match(r"^([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})$", raw)
    if mdy:
        mon = _MONTHS.get(mdy.group(1)[:3].lower())
        if mon:
            return _safe_iso(int(mdy.group(3)), mon, int(mdy.group(2)))

    # "DD Month YYYY"
    dmy = re.match(r"^(\d{1,2})\s+([A-Za-z]{3,9})\.?\s+(\d{4})$", raw)
    if dmy:
        mon = _MONTHS.get(dmy.group(2)[:3].lower())
        if mon:
            return _safe_iso(int(dmy.group(3)), mon, int(dmy.group(1)))

    return None


def _safe_iso(year: int, month: int, day: int) -> str | None:
    try:
        return datetime(year, month, day).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _infer_cycle_from_period(start_iso: str | None, end_iso: str | None) -> str | None:
    """Infer billing cycle from the length of a billing period (strong invoice signal)."""
    if not (start_iso and end_iso):
        return None
    try:
        s = datetime.strptime(start_iso, "%Y-%m-%d")
        e = datetime.strptime(end_iso, "%Y-%m-%d")
    except ValueError:
        return None
    days = (e - s).days
    if days <= 0:
        return None
    if days <= 10:
        return "WEEKLY"
    if 24 <= days <= 40:
        return "MONTHLY"
    if 80 <= days <= 100:
        return "QUARTERLY"
    if 350 <= days <= 380:
        return "ANNUAL"
    return None


def _extract_total(text: str) -> tuple[float | None, str | None, bool]:
    """Return (amount, currency, labeled). Prefers amounts on 'total/amount due' lines."""
    labeled: list[tuple[float, str | None]] = []
    any_line: list[tuple[float, str | None]] = []
    for line in text.splitlines():
        amt, cur = extract_amount(line)            # line occupies the 'subject' slot
        if amt is None:
            continue
        any_line.append((amt, cur))
        if _TOTAL_LINE_RE.search(line) and not _TAX_LINE_RE.search(line):
            labeled.append((amt, cur))
    if labeled:
        amt, cur = max(labeled, key=lambda c: c[0])   # the total is the largest labeled amount
        return amt, cur, True
    if any_line:
        amt, cur = max(any_line, key=lambda c: c[0])
        return amt, cur, False
    return None, None, False


def _extract_tax(text: str) -> float | None:
    for line in text.splitlines():
        if _TAX_LINE_RE.search(line):
            amt, _ = extract_amount(line)
            if amt is not None:
                return amt
    return None


def _first_date_after(label_re: re.Pattern, text: str) -> str | None:
    m = label_re.search(text)
    if not m:
        return None
    tail = next((g for g in m.groups() if g), "")
    return _parse_date_token(tail)


def _extract_period(text: str) -> tuple[str | None, str | None]:
    m = _PERIOD_RE.search(text)
    if not m:
        return None, None
    tail = next((g for g in m.groups() if g), "")
    parts = _PERIOD_SPLIT_RE.split(tail, maxsplit=1)
    if len(parts) == 2:
        return _parse_date_token(parts[0]), _parse_date_token(parts[1])
    return None, None


def _guess_provider(text: str) -> str | None:
    """First plausible non-label line — usually the merchant/company name on an invoice."""
    for line in text.splitlines():
        s = line.strip()
        if not s or _PROVIDER_SKIP_RE.search(s):
            continue
        if len(re.findall(r"[A-Za-z֐-׿]", s)) < 2:  # need real letters (Latin/Hebrew)
            continue
        if len(s) > 60:
            continue
        return s
    return None


def _guess_product(text: str) -> str | None:
    """Product/plan name from an explicit 'Plan:'/'Description:' label, if present."""
    m = _PRODUCT_LABEL_RE.search(text)
    if m:
        val = m.group(1).strip()
        if 1 < len(val) <= 60:
            return val
    return None


# ── Public entry point ──────────────────────────────────────────────────────────

def extract_pdf_fields(pdf_bytes: bytes | None) -> PdfEvidence:
    """Parse a PDF's bytes into structured PdfEvidence. Never raises; never keeps text.

    Returns a PdfEvidence with extraction_status:
      OK        — at least an amount, billing period, or strong indicator was found
      NO_FIELDS — text was present but nothing useful was extracted
      NO_TEXT   — no extractable text (likely a scanned/image PDF; OCR not in scope)
      FAILED    — bytes missing/oversized or pdfminer raised
    """
    ev = PdfEvidence()

    if not pdf_bytes:
        ev.extraction_status = "FAILED"
        ev.penalty_reasons.append("no_attachment_bytes")
        return ev
    if len(pdf_bytes) > MAX_PDF_BYTES:
        ev.extraction_status = "FAILED"
        ev.penalty_reasons.append("pdf_too_large")
        return ev

    try:
        text = _extract_text_transient(pdf_bytes)
    except Exception as exc:  # pdfminer can raise on malformed/encrypted PDFs
        logger.warning("PDF text extraction failed: %s", type(exc).__name__)
        ev.extraction_status = "FAILED"
        ev.penalty_reasons.append("pdf_parse_exception")
        return ev

    if not text or not text.strip():
        ev.extraction_status = "NO_TEXT"
        ev.missing_evidence.append("no_extractable_text")
        ev.penalty_reasons.append("pdf_no_text_image_only")
        return ev

    # ── Amount + currency ──────────────────────────────────────────────────────
    amount, currency, labeled = _extract_total(text)
    if amount is not None:
        ev.amount = amount
        ev.currency = currency
        ev.evidence_reasons.append("amount_in_pdf")
        if labeled:
            ev.evidence_reasons.append("labeled_total_in_pdf")
        if currency:
            ev.evidence_reasons.append("currency_in_pdf")
    else:
        ev.missing_evidence.append("no_amount_in_pdf")

    ev.tax_amount = _extract_tax(text)
    if ev.tax_amount is not None:
        ev.evidence_reasons.append("tax_found")

    # ── Provider / product (merchant name + plan label) ──────────────────────────
    ev.provider = _guess_provider(text)
    if ev.provider:
        ev.evidence_reasons.append("provider_in_pdf")
    ev.product_name = _guess_product(text)

    # ── Dates + billing period ───────────────────────────────────────────────────
    ev.invoice_date = _first_date_after(_INVOICE_DATE_RE, text)
    if ev.invoice_date:
        ev.evidence_reasons.append("invoice_date_found")
    ev.payment_date = _first_date_after(_PAYMENT_DATE_RE, text)
    if ev.payment_date:
        ev.evidence_reasons.append("payment_date_found")

    ev.billing_period_start, ev.billing_period_end = _extract_period(text)
    if ev.billing_period_start and ev.billing_period_end:
        ev.evidence_reasons.append("billing_period_found")

    # ── Invoice number ───────────────────────────────────────────────────────────
    inv = _INVOICE_NO_RE.search(text)
    if inv:
        ev.invoice_number = inv.group(1)
        ev.evidence_reasons.append("invoice_number_found")

    # ── Billing cycle (period-based is strongest; else keyword detection) ─────────
    period_cycle = _infer_cycle_from_period(ev.billing_period_start, ev.billing_period_end)
    if period_cycle:
        ev.inferred_cycle = period_cycle
        ev.evidence_reasons.append("cycle_from_period")
    else:
        # Treat PDF text like a snippet (weak cycle keywords allowed with billing context).
        cycle = detect_cycle("", snippet=text)
        if cycle != "UNKNOWN":
            ev.inferred_cycle = cycle
            ev.evidence_reasons.append("cycle_in_pdf")
    if not ev.inferred_cycle:
        ev.missing_evidence.append("no_cycle_in_pdf")

    # ── Recurring / refund / cancellation / trial indicators ──────────────────────
    for pattern, token in _INDICATOR_PATTERNS:
        if pattern.search(text):
            ev.subscription_indicators.append(token)
    if ev.subscription_indicators:
        ev.evidence_reasons.append("recurring_wording_in_pdf")
    else:
        ev.missing_evidence.append("no_recurring_wording")

    if _REFUND_RE.search(text):
        ev.penalty_reasons.append("refund_detected")
    if _CANCEL_RE.search(text):
        ev.penalty_reasons.append("cancellation_detected")
    if _TRIAL_RE.search(text):
        ev.subscription_indicators.append("trial")
        ev.penalty_reasons.append("trial_detected")

    # Receipt-only penalty: amount present but no recurring evidence at all.
    if ev.amount is not None and not ev.has_recurring_evidence() and not ev.is_refund():
        ev.penalty_reasons.append("receipt_one_time_no_recurring")

    # ── Status + confidence ───────────────────────────────────────────────────────
    found_useful = bool(
        ev.amount is not None
        or (ev.billing_period_start and ev.billing_period_end)
        or ev.subscription_indicators
        or ev.invoice_number
    )
    ev.extraction_status = "OK" if found_useful else "NO_FIELDS"
    ev.confidence_score = _score(ev)

    # text goes out of scope here — never persisted, never returned
    return ev


def _score(ev: PdfEvidence) -> float:
    """Rough 0..1 confidence from how many strong structured fields were found."""
    score = 0.0
    if ev.amount is not None:
        score += 0.40
    if ev.inferred_cycle:
        score += 0.20
    if ev.billing_period_start and ev.billing_period_end:
        score += 0.15
    if ev.has_recurring_evidence():
        score += 0.15
    if ev.invoice_date or ev.payment_date:
        score += 0.05
    if ev.invoice_number:
        score += 0.05
    if ev.is_refund():
        score = min(score, 0.30)  # a refund is not subscription confidence
    return round(min(score, 1.0), 2)
