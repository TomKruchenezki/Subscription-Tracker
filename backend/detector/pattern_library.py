"""
Pre-compiled regex sets for subject-line pattern matching.
Each set matches one signal type: receipt, renewal, trial, cancellation, etc.
"""
import re
from enum import Enum


class PatternType(str, Enum):
    RECEIPT        = "RECEIPT"
    RENEWAL        = "RENEWAL"
    TRIAL_END      = "TRIAL_END"
    TRIAL_STARTED  = "TRIAL_STARTED"
    CANCELLATION   = "CANCELLATION"
    FAILED_PAYMENT = "FAILED_PAYMENT"
    REFUND         = "REFUND"
    PRICE_CHANGE   = "PRICE_CHANGE"
    PROMOTIONAL    = "PROMOTIONAL"
    NONE           = "NONE"


_FAILED_PAYMENT_PATTERNS = [
    re.compile(r"\bpayment\s+(failed|unsuccessful|declined|could\s+not\s+be\s+processed)\b", re.IGNORECASE),
    re.compile(r"\bfailed\s+payment\b", re.IGNORECASE),
    re.compile(r"\b(your\s+)?(card|payment\s+method)\s+(was\s+)?declined\b", re.IGNORECASE),
    re.compile(r"\bunable\s+to\s+(process|charge)\s+(your\s+)?(payment|card)\b", re.IGNORECASE),
    re.compile(r"\baction\s+required.{0,30}payment\b", re.IGNORECASE),
    re.compile(r"\bbilling\s+(failed|unsuccessful)\b", re.IGNORECASE),
]

_REFUND_PATTERNS = [
    re.compile(r"\brefund\w*\b", re.IGNORECASE),
    re.compile(r"\bwe.ve\s+issued\s+a\s+refund\b", re.IGNORECASE),
    re.compile(r"\byour\s+refund\b", re.IGNORECASE),
    re.compile(r"\bcredit\s+issued\b", re.IGNORECASE),
    re.compile(r"\bamount\s+refunded\b", re.IGNORECASE),
]

_CANCELLATION_PATTERNS = [
    re.compile(r"\bcancell?ation\b", re.IGNORECASE),
    re.compile(r"\bcancell?ed\b", re.IGNORECASE),
    re.compile(r"\byou.ve\s+cancell?ed\b", re.IGNORECASE),
    re.compile(r"\bsubscription\s+(has\s+been\s+)?cancell?\w+", re.IGNORECASE),
    re.compile(r"\baccess\s+(has\s+been\s+)?removed\b", re.IGNORECASE),
]

_TRIAL_END_PATTERNS = [
    re.compile(r"\btrial\s+(end|expir|over|period)\w*", re.IGNORECASE),
    re.compile(r"\bfree\s+trial\s+(end|expir)\w*", re.IGNORECASE),
    re.compile(r"\btrial\s+is\s+(ending|expiring|almost\s+over)\b", re.IGNORECASE),
    re.compile(r"\btrial\s+period\s+end\w*", re.IGNORECASE),
]

_TRIAL_STARTED_PATTERNS = [
    re.compile(r"\byour\s+(free\s+)?trial\s+(has\s+)?(started|begun|activated)\b", re.IGNORECASE),
    re.compile(r"\bwelcome\s+to\s+your\s+(free\s+)?trial\b", re.IGNORECASE),
    re.compile(r"\btrial\s+(is\s+now\s+)?active\b", re.IGNORECASE),
    re.compile(r"\bfree\s+trial\s+started\b", re.IGNORECASE),
    re.compile(r"\byou.ve\s+started\s+(a\s+)?(\w+\s+)?trial\b", re.IGNORECASE),
]

_PRICE_CHANGE_PATTERNS = [
    re.compile(r"\bprice\s+(change|increase|update|adjustment)\b", re.IGNORECASE),
    re.compile(r"\bwe.re\s+(updating|changing|raising)\s+(our\s+)?price\w*\b", re.IGNORECASE),
    re.compile(r"\bnew\s+price\b", re.IGNORECASE),
    re.compile(r"\bsubscription\s+price\s+will\b", re.IGNORECASE),
    re.compile(r"\brate\s+change\b", re.IGNORECASE),
]

_RECEIPT_PATTERNS = [
    re.compile(r"\breceipt\b", re.IGNORECASE),
    re.compile(r"\binvoice\b", re.IGNORECASE),
    re.compile(r"\bpayment\s+(confirmation|received|successful)\b", re.IGNORECASE),
    re.compile(r"\byour\s+(order|purchase|charge)\b", re.IGNORECASE),
    re.compile(r"\bthank\s+you\s+for\s+(your\s+)?(payment|purchase|subscription)\b", re.IGNORECASE),
    re.compile(r"\bbilling\s+(confirmation|statement)\b", re.IGNORECASE),
    re.compile(r"\bcharged\b", re.IGNORECASE),
]

_RENEWAL_PATTERNS = [
    re.compile(r"\brenew(al|s|ing|ed)?\b", re.IGNORECASE),
    re.compile(r"\bsubscription\s+(renew|expir|upcom)\w*", re.IGNORECASE),
    re.compile(r"\bcoming\s+up\b", re.IGNORECASE),
    re.compile(r"\bnext\s+(billing|payment|charge)\b", re.IGNORECASE),
    re.compile(r"\brenews\s+(on|in)\b", re.IGNORECASE),
    re.compile(r"\bauto[\s-]?renew\b", re.IGNORECASE),
]

_PROMOTIONAL_PATTERNS = [
    re.compile(r"\b\d+%\s+off\b", re.IGNORECASE),
    re.compile(r"\bspecial\s+offer\b", re.IGNORECASE),
    re.compile(r"\btry\s+\w+\s+free\b", re.IGNORECASE),
    re.compile(r"\bfree\s+for\s+\d+\s+(day|month|week)\w*", re.IGNORECASE),
    re.compile(r"\bflash\s+sale\b", re.IGNORECASE),
    re.compile(r"\bexclusive\s+(deal|offer|discount)\b", re.IGNORECASE),
    re.compile(r"\bupgrade\s+(now|today|your)\b", re.IGNORECASE),
    re.compile(r"\bdon.t\s+miss\s+out\b", re.IGNORECASE),
    re.compile(r"\blimited\s+time\b", re.IGNORECASE),
    re.compile(r"\bfirst\s+month\s+free\b", re.IGNORECASE),
    re.compile(r"\b(get|save)\s+\d+%\b", re.IGNORECASE),
]


def match_pattern(subject: str) -> PatternType:
    """
    Returns the strongest matching pattern type.
    Priority: FAILED_PAYMENT > REFUND > CANCELLATION > TRIAL_END > TRIAL_STARTED
              > PRICE_CHANGE > RECEIPT > RENEWAL > PROMOTIONAL > NONE
    """
    for pattern in _FAILED_PAYMENT_PATTERNS:
        if pattern.search(subject):
            return PatternType.FAILED_PAYMENT

    for pattern in _REFUND_PATTERNS:
        if pattern.search(subject):
            return PatternType.REFUND

    for pattern in _CANCELLATION_PATTERNS:
        if pattern.search(subject):
            return PatternType.CANCELLATION

    for pattern in _TRIAL_END_PATTERNS:
        if pattern.search(subject):
            return PatternType.TRIAL_END

    for pattern in _TRIAL_STARTED_PATTERNS:
        if pattern.search(subject):
            return PatternType.TRIAL_STARTED

    for pattern in _PRICE_CHANGE_PATTERNS:
        if pattern.search(subject):
            return PatternType.PRICE_CHANGE

    for pattern in _RECEIPT_PATTERNS:
        if pattern.search(subject):
            return PatternType.RECEIPT

    for pattern in _RENEWAL_PATTERNS:
        if pattern.search(subject):
            return PatternType.RENEWAL

    for pattern in _PROMOTIONAL_PATTERNS:
        if pattern.search(subject):
            return PatternType.PROMOTIONAL

    return PatternType.NONE
