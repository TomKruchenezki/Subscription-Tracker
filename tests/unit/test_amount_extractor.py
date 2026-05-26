import pytest
from backend.parser.amount_extractor import extract_amount


@pytest.mark.parametrize("subject, expected_amount, expected_currency", [
    ("Your Netflix subscription: $15.49",         15.49, "USD"),
    ("Spotify receipt: 9.99 USD",                 9.99,  "USD"),
    ("Charged £8.99",                             8.99,  "GBP"),
    ("Annual plan: $99.00/year",                  99.00, "USD"),
    ("Renewal: €12.99 EUR",                       12.99, "EUR"),
    ("Amount: $0.99",                             0.99,  "USD"),
    ("Invoice: $999.99",                          999.99,"USD"),
    # Promotional — no amount extracted
    ("50% off your next month",                   None,  None),
    ("Save 30% on your plan",                     None,  None),
    # Out of range
    ("Invoice: $1500.00",                         None,  None),
    # No amount
    ("Your free trial has ended",                 None,  None),
    # Multi-amount subject — first valid match used
    ("Receipt: $9.99 and $4.99 charged",          9.99,  "USD"),
])
def test_extract_amount(subject, expected_amount, expected_currency):
    amount, currency = extract_amount(subject)
    assert amount == expected_amount
    assert currency == expected_currency
