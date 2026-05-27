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
