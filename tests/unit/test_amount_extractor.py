import pytest
from backend.parser.amount_extractor import extract_amount


@pytest.mark.parametrize("subject, expected_amount, expected_currency", [
    ("Your Netflix subscription: $15.49",         15.49,   "USD"),
    ("Spotify receipt: 9.99 USD",                 9.99,    "USD"),
    ("Charged £8.99",                             8.99,    "GBP"),
    ("Annual plan: $99.00/year",                  99.00,   "USD"),
    ("Renewal: €12.99 EUR",                       12.99,   "EUR"),
    ("Amount: $0.99",                             0.99,    "USD"),
    ("Invoice: $999.99",                          999.99,  "USD"),
    # Cap raised to $9,999.99 — annual enterprise plans are valid
    ("Invoice: $1500.00",                         1500.00, "USD"),
    ("Annual plan: $9999.99",                     9999.99, "USD"),
    # Promotional — no amount extracted
    ("50% off your next month",                   None,    None),
    ("Save 30% on your plan",                     None,    None),
    # No amount
    ("Your free trial has ended",                 None,    None),
    # Multi-amount subject — first valid match used
    ("Receipt: $9.99 and $4.99 charged",          9.99,    "USD"),
])
def test_extract_amount(subject, expected_amount, expected_currency):
    amount, currency = extract_amount(subject)
    assert amount == expected_amount
    assert currency == expected_currency


def test_extract_amount_falls_back_to_snippet():
    """When subject has no amount, snippet is used as fallback."""
    amount, currency = extract_amount(
        subject="חידוש מנוי Spotify",
        snippet="Spotify charged $9.99 for one month",
    )
    assert amount == pytest.approx(9.99)
    assert currency == "USD"


def test_extract_amount_subject_wins_over_snippet():
    """When subject has an amount, it takes precedence over snippet."""
    amount, currency = extract_amount(
        subject="Your receipt: $15.49",
        snippet="charged $9.99 extra",
    )
    assert amount == pytest.approx(15.49)


def test_extract_amount_html_entities_stripped():
    """HTML entities in snippets are unescaped before extraction."""
    amount, currency = extract_amount(
        subject="Receipt",
        snippet="You were charged $9.99 &amp; tax",
    )
    assert amount == pytest.approx(9.99)
    assert currency == "USD"


def test_ils_amount_extracted():
    """Israeli Shekel (₪) is recognised from subject."""
    amount, currency = extract_amount("חיוב ₪49.90")
    assert amount == pytest.approx(49.90)
    assert currency == "ILS"


def test_ils_amount_from_snippet():
    """Israeli Shekel in snippet is recognised as fallback."""
    amount, currency = extract_amount(
        subject="חיוב חודשי",
        snippet="₪49.90 נגבו מהכרטיס שלך",
    )
    assert amount == pytest.approx(49.90)
    assert currency == "ILS"


def test_ils_code_extracted():
    """ILS currency code variant is recognised."""
    amount, currency = extract_amount("49.90 ILS monthly charge")
    assert amount == pytest.approx(49.90)
    assert currency == "ILS"


def test_extract_amount_falls_back_to_body_text():
    """When subject and snippet have no amount, body_text is used as last resort."""
    amount, currency = extract_amount(
        subject="חידוש מנוי",
        snippet="Thank you for your continued subscription.",
        body_text="You have been charged ₪49.90 for your monthly plan.",
    )
    assert amount == pytest.approx(49.90)
    assert currency == "ILS"


def test_subject_wins_over_body_text():
    """Subject amount always wins over body_text amount."""
    amount, currency = extract_amount(
        subject="Your receipt: $15.49",
        body_text="charged $9.99 extra",
    )
    assert amount == pytest.approx(15.49)
    assert currency == "USD"


def test_snippet_wins_over_body_text():
    """Snippet amount wins over body_text when subject has none."""
    amount, currency = extract_amount(
        subject="Your subscription renewal",
        snippet="Spotify charged $9.99 for one month",
        body_text="You paid $4.99 last time",
    )
    assert amount == pytest.approx(9.99)
    assert currency == "USD"


def test_body_text_used_when_subject_and_snippet_empty():
    """body_text is used when both subject and snippet yield nothing."""
    amount, currency = extract_amount(
        subject="Your account update",
        snippet=None,
        body_text="Total charge: $29.00 USD for annual plan",
    )
    assert amount == pytest.approx(29.00)
    assert currency == "USD"


# ── Non-monetary context guards (Phase 2.7) ───────────────────────────────────

def test_rejects_amount_near_profile_views():
    """Numbers near 'profile views' are not monetary amounts."""
    amount, currency = extract_amount("30 people viewed your profile this week")
    assert amount is None
    assert currency is None


def test_rejects_amount_near_writing_suggestions():
    """Numbers near 'writing suggestions' are not monetary amounts."""
    amount, currency = extract_amount("72 writing suggestions corrected this week")
    assert amount is None
    assert currency is None


def test_rejects_amount_near_search_count():
    """Numbers near 'searches' are not monetary amounts."""
    amount, currency = extract_amount("You appeared in 3 searches this week")
    assert amount is None
    assert currency is None


def test_rejects_amount_near_connections():
    """Numbers near 'connections' are not monetary amounts."""
    amount, currency = extract_amount("You have 500 connections on LinkedIn")
    assert amount is None
    assert currency is None


def test_rejects_writing_stats_in_snippet():
    """Non-monetary guard applies to snippet text as well."""
    amount, currency = extract_amount(
        subject="Your Grammarly Weekly Writing Report",
        snippet="72 advanced writing suggestions this week",
    )
    assert amount is None
    assert currency is None


def test_non_monetary_in_snippet_does_not_block_subject():
    """Non-monetary text in snippet does not suppress amount from subject."""
    amount, currency = extract_amount(
        subject="Charge: $12.00",
        snippet="30 connections viewed your profile",
    )
    assert amount == pytest.approx(12.00)
    assert currency == "USD"


def test_payment_amount_is_accepted():
    """Plain payment amount (no non-monetary context) is accepted normally."""
    amount, currency = extract_amount("Your payment: $15.49 has been processed")
    assert amount == pytest.approx(15.49)
    assert currency == "USD"


def test_rejects_booking_reference_number():
    """Booking reference numbers are not monetary amounts."""
    amount, currency = extract_amount("Booking confirmation #38291749")
    assert amount is None
    assert currency is None
