"""
Pre-compiled regex sets for subject-line pattern matching.
Each set matches one signal type: receipt, renewal, trial_end, cancellation, promotional.
"""
import re
from enum import Enum


class PatternType(str, Enum):
    RECEIPT = "RECEIPT"
    RENEWAL = "RENEWAL"
    TRIAL_END = "TRIAL_END"
    CANCELLATION = "CANCELLATION"
    PROMOTIONAL = "PROMOTIONAL"
    NONE = "NONE"


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

_TRIAL_END_PATTERNS = [
    re.compile(r"\btrial\s+(end|expir|over|period)\w*", re.IGNORECASE),
    re.compile(r"\bfree\s+trial\s+(end|expir)\w*", re.IGNORECASE),
    re.compile(r"\btrial\s+is\s+(ending|expiring|almost\s+over)\b", re.IGNORECASE),
    re.compile(r"\btrial\s+period\s+end\w*", re.IGNORECASE),
]

_CANCELLATION_PATTERNS = [
    re.compile(r"\bcancell?ation\b", re.IGNORECASE),
    re.compile(r"\bcancell?ed\b", re.IGNORECASE),
    re.compile(r"\byou.ve\s+cancell?ed\b", re.IGNORECASE),
    re.compile(r"\bsubscription\s+(has\s+been\s+)?cancell?\w+", re.IGNORECASE),
    re.compile(r"\baccess\s+(has\s+been\s+)?removed\b", re.IGNORECASE),
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
    Priority: CANCELLATION > TRIAL_END > RECEIPT > RENEWAL > PROMOTIONAL > NONE.
    """
    for pattern in _CANCELLATION_PATTERNS:
        if pattern.search(subject):
            return PatternType.CANCELLATION

    for pattern in _TRIAL_END_PATTERNS:
        if pattern.search(subject):
            return PatternType.TRIAL_END

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
