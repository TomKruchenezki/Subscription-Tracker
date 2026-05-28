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
    NOTIFICATION   = "NOTIFICATION"
    NONE           = "NONE"


_FAILED_PAYMENT_PATTERNS = [
    re.compile(r"\bpayment\s+(failed|unsuccessful|declined|could\s+not\s+be\s+processed)\b", re.IGNORECASE),
    re.compile(r"\bfailed\s+payment\b", re.IGNORECASE),
    re.compile(r"\b(your\s+)?(card|payment\s+method)\s+(was\s+)?declined\b", re.IGNORECASE),
    re.compile(r"\bunable\s+to\s+(process|charge)\s+(your\s+)?(payment|card)\b", re.IGNORECASE),
    re.compile(r"\baction\s+required.{0,30}payment\b", re.IGNORECASE),
    re.compile(r"\bbilling\s+(failed|unsuccessful)\b", re.IGNORECASE),
    # Hebrew
    re.compile(r"\bהתשלום\s+נכשל\b"),          # payment failed
    re.compile(r"\bאמצעי\s+התשלום\s+נדחה\b"),   # payment method declined
]

_REFUND_PATTERNS = [
    re.compile(r"\brefund\w*\b", re.IGNORECASE),
    re.compile(r"\bwe.ve\s+issued\s+a\s+refund\b", re.IGNORECASE),
    re.compile(r"\byour\s+refund\b", re.IGNORECASE),
    re.compile(r"\bcredit\s+issued\b", re.IGNORECASE),
    re.compile(r"\bamount\s+refunded\b", re.IGNORECASE),
    # Hebrew
    re.compile(r"\bהחזר\b"),                    # refund
    re.compile(r"\bזיכוי\b"),                    # credit
]

_CANCELLATION_PATTERNS = [
    re.compile(r"\bcancell?ation\b", re.IGNORECASE),
    re.compile(r"\bcancell?ed\b", re.IGNORECASE),
    re.compile(r"\byou.ve\s+cancell?ed\b", re.IGNORECASE),
    re.compile(r"\bsubscription\s+(has\s+been\s+)?cancell?\w+", re.IGNORECASE),
    re.compile(r"\baccess\s+(has\s+been\s+)?removed\b", re.IGNORECASE),
    # Hebrew
    re.compile(r"\bביטול\b"),                    # cancellation
    re.compile(r"\bבוטל\b"),                     # cancelled
]

_TRIAL_END_PATTERNS = [
    re.compile(r"\btrial\s+(end|expir|over|period)\w*", re.IGNORECASE),
    re.compile(r"\bfree\s+trial\s+(end|expir)\w*", re.IGNORECASE),
    re.compile(r"\btrial\s+is\s+(ending|expiring|almost\s+over)\b", re.IGNORECASE),
    re.compile(r"\btrial\s+period\s+end\w*", re.IGNORECASE),
    # Hebrew
    re.compile(r"\bניסיון\s+(?:מסתיים|יסתיים|מסתיים\s+בקרוב)\b"),   # trial ending/will end
    re.compile(r"\bתקופת\s+ניסיון\s+(?:מסתיימת?|מסתיים)\b"),         # trial period ending
]

_TRIAL_STARTED_PATTERNS = [
    re.compile(r"\byour\s+(free\s+)?trial\s+(has\s+)?(started|begun|activated)\b", re.IGNORECASE),
    re.compile(r"\bwelcome\s+to\s+your\s+(free\s+)?trial\b", re.IGNORECASE),
    re.compile(r"\btrial\s+(is\s+now\s+)?active\b", re.IGNORECASE),
    re.compile(r"\bfree\s+trial\s+started\b", re.IGNORECASE),
    re.compile(r"\byou.ve\s+started\s+(a\s+)?(\w+\s+)?trial\b", re.IGNORECASE),
    # Hebrew
    re.compile(r"\bניסיון\s+חינם\b"),            # free trial
    re.compile(r"\bתקופת\s+ניסיון\b"),            # trial period
]

_PRICE_CHANGE_PATTERNS = [
    re.compile(r"\bprice\s+(change|increase|update|adjustment)\b", re.IGNORECASE),
    re.compile(r"\bwe.re\s+(updating|changing|raising)\s+(our\s+)?price\w*\b", re.IGNORECASE),
    re.compile(r"\bnew\s+price\b", re.IGNORECASE),
    re.compile(r"\bsubscription\s+price\s+will\b", re.IGNORECASE),
    re.compile(r"\brate\s+change\b", re.IGNORECASE),
    # Hebrew
    re.compile(r"\bשינוי\s+(?:ב)?מחיר\b"),          # price change
    re.compile(r"\b(?:עלייה|עלית)\s+(?:ב)?תשלום\b"),# payment increase
    re.compile(r"\bמחיר\s+חדש\b"),                  # new price
]

_RECEIPT_PATTERNS = [
    re.compile(r"\breceipt\b", re.IGNORECASE),
    re.compile(r"\binvoice\b", re.IGNORECASE),
    re.compile(r"\bpayment\s+(confirmation|received|successful|processed|complete[d]?)\b", re.IGNORECASE),
    re.compile(r"\byour\s+(order|purchase|charge)\b", re.IGNORECASE),
    re.compile(r"\bthank\s+you\s+for\s+(your\s+)?(payment|purchase|subscription)\b", re.IGNORECASE),
    re.compile(r"\bbilling\s+(confirmation|statement)\b", re.IGNORECASE),
    re.compile(r"\bcharged\b", re.IGNORECASE),
    # Hebrew
    re.compile(r"\bקבלה\b"),                     # receipt
    re.compile(r"\bחשבונית\b"),                  # invoice
    re.compile(r"\bחויבת\b"),                    # you were charged
    re.compile(r"\bעסקה\b"),                     # transaction
    re.compile(r"\bחיוב\b"),                     # charge/billing
    re.compile(r"\bתשלום\b"),                    # payment
    re.compile(r"\bכרטיסך\s+חויב\b"),           # your card was charged
    re.compile(r"\bאישור\s+תשלום\b"),            # payment confirmation
    re.compile(r"\bהתשלום\s+התקבל\b"),           # payment received
    re.compile(r"\bהוראת\s+קבע\b"),             # standing order / direct debit
]

_RENEWAL_PATTERNS = [
    re.compile(r"\brenew(al|s|ing|ed)?\b", re.IGNORECASE),
    re.compile(r"\bsubscription\s+(renew|expir|upcom)\w*", re.IGNORECASE),
    re.compile(r"\bcoming\s+up\b", re.IGNORECASE),
    re.compile(r"\bnext\s+(billing|payment|charge)\b", re.IGNORECASE),
    re.compile(r"\brenews\s+(on|in)\b", re.IGNORECASE),
    re.compile(r"\bauto[\s-]?renew\b", re.IGNORECASE),
    # Hebrew
    re.compile(r"\bחידוש\s+מנוי\b"),             # subscription renewal
    re.compile(r"\bהתחדש\b"),                    # renewed
    re.compile(r"\bמנוי\b"),                     # subscription (general signal)
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
    # Upgrade / offer-price language — "for only $X", "just $X/month", etc.
    # Signals a promotional email, not a billing receipt.
    # Priority: RECEIPT > PROMOTIONAL, so a genuine "Your receipt — only $X charged"
    # still matches RECEIPT first and is unaffected.
    re.compile(r"\bfor\s+only\s+[$€£₪¥₹]", re.IGNORECASE),
    re.compile(r"\bonly\s+[$€£₪¥₹]\d", re.IGNORECASE),
    re.compile(r"\bjust\s+[$€£₪¥₹]\d", re.IGNORECASE),
    re.compile(r"\bstarting\s+(?:at|from)\s+[$€£₪¥₹]", re.IGNORECASE),
    re.compile(r"\bget\s+\w+\s+for\s+(?:just\s+)?[$€£₪¥₹]", re.IGNORECASE),
    # Hebrew promotional / discount language
    re.compile(r"\bמבצע\b"),                     # sale / special offer
    re.compile(r"\bהנחה\b"),                     # discount
    re.compile(r"\bקופון\b"),                    # coupon
    re.compile(r"\bחינם\s+ל(?:חודש|שבוע|שנה)\b"),  # free for month/week/year
    re.compile(r"\bהצעה\s+מיוחדת\b"),            # special offer
    re.compile(r"\bחסוך\b|\bחסכי\b"),            # save (imperative m/f)
]

_NOTIFICATION_PATTERNS = [
    # Social/professional network notifications (never billing)
    re.compile(r"\bappeared\s+in\b.{0,40}\bsearch(es)?\b", re.IGNORECASE),
    re.compile(r"\bprofile\b.{0,20}\bview(s|ed)?\b", re.IGNORECASE),
    re.compile(r"\bpeople\s+you\s+may\s+know\b", re.IGNORECASE),
    re.compile(r"\bconnection\s+request\b", re.IGNORECASE),
    re.compile(r"\b(endorsed|liked|commented\s+on|shared)\s+your\b", re.IGNORECASE),
    re.compile(r"\bjob\s+(alert|recommendation|posting)\b", re.IGNORECASE),
    # Policy/legal updates (never billing)
    re.compile(r"\buser\s+agreement\b", re.IGNORECASE),
    re.compile(r"\bprivacy\s+polic(y|ies)\b", re.IGNORECASE),
    re.compile(r"\bterms\s+of\s+service\b", re.IGNORECASE),
    re.compile(r"\bterms\s+and\s+conditions\b", re.IGNORECASE),
    # Security/account alerts (never billing on their own)
    re.compile(r"\bsign[\-\s]?in\s+(from\s+a?\s*new|attempt)\b", re.IGNORECASE),
    re.compile(r"\bnew\s+device\s+sign[\-\s]?in\b", re.IGNORECASE),
    re.compile(r"\bverify\s+your\s+email\b", re.IGNORECASE),
    re.compile(r"\b(password\s+reset|reset\s+(your\s+)?password)\b", re.IGNORECASE),
    re.compile(r"\bsecurity\s+(alert|code|verification)\b", re.IGNORECASE),
    # Travel/one-time receipts (not recurring subscriptions)
    re.compile(r"\be[\-\s]?ticket\b", re.IGNORECASE),
    re.compile(r"\bboarding\s+pass\b", re.IGNORECASE),
    re.compile(r"\bflight\s+(itinerary|confirmation|booking)\b", re.IGNORECASE),
    re.compile(r"\bhotel\s+(confirmation|reservation)\b", re.IGNORECASE),
    re.compile(r"\breservation\s+confirmation\b", re.IGNORECASE),
    # Grammarly non-billing emails (writing stats/reports — not receipts)
    re.compile(r"\bwriting\s+(report|stats?|insights?|highlights?|activity|score|goals?)\b", re.IGNORECASE),
    re.compile(r"\bweekly\s+(writing|grammar|progress)\b", re.IGNORECASE),
    re.compile(r"\b(grammar|writing|spelling)\s+(score|goals?)\b", re.IGNORECASE),
    # LinkedIn non-billing emails (career digests, job alerts — not billing)
    re.compile(r"\bweekly\s+(job|career)\s+(alerts?|digest|picks?|recommendations?)\b", re.IGNORECASE),
    re.compile(r"\bmonthly\s+(career|job)\s+(digest|newsletter|recap|summary)\b", re.IGNORECASE),
    re.compile(r"\b(top\s+)?(jobs?|career|opportunities)\s+(for\s+you|this\s+week|recommended)\b", re.IGNORECASE),
    re.compile(r"\byour\s+(network\s+)?(digest|roundup|weekly|recap)\b", re.IGNORECASE),
    # Zoom non-billing emails (webinar invites, product tips)
    re.compile(r"\bzoom\s+(tips?|updates?|news|webinar|feature)\b", re.IGNORECASE),
    re.compile(r"\b(webinar|virtual\s+event)\s+(invite|invitation|registration|reminder)\b", re.IGNORECASE),
    re.compile(r"\bjoin\s+(our\s+)?(free\s+)?(webinar|event|online\s+session)\b", re.IGNORECASE),
    # Job alerts and recruiting (LinkedIn, Wix, etc.)
    re.compile(r"\bjob\s+(opening|opportunity)\b", re.IGNORECASE),
    re.compile(r"\b(new\s+)?(job|career)\s+opportunit", re.IGNORECASE),
    re.compile(r"\bnow\s+hiring\b", re.IGNORECASE),
    re.compile(r"\bopen\s+(role|position)\b", re.IGNORECASE),
    re.compile(r"\b(recruiter|recruiting)\s+(message|outreach|reached)\b", re.IGNORECASE),
    re.compile(r"\b(junior|senior|lead|staff|principal|mid[\s-]level)\s+\w+\s+"
               r"(engineer|developer|manager|analyst|designer)\b", re.IGNORECASE),
    re.compile(r"\b(full[\s-]?stack|front[\s-]?end|back[\s-]?end)\s+"
               r"(developer|engineer)\b", re.IGNORECASE),
    # LinkedIn invitations and social signals
    re.compile(r"\bwants\s+to\s+connect\b", re.IGNORECASE),
    re.compile(r"\binvitation\s+to\s+connect\b", re.IGNORECASE),
    re.compile(r"\bi['’]d\s+like\s+to\s+(add|connect)\b", re.IGNORECASE),
    re.compile(r"\b(has\s+)?accepted\s+your\s+invitation\b", re.IGNORECASE),
    re.compile(r"\b(application|candidacy)\s+(was\s+)?(viewed|received|reviewed)\b", re.IGNORECASE),
    # Newsletter / content digest (Substack, etc.)
    re.compile(r"\bnew\s+post\s+(from|by|in)\b", re.IGNORECASE),
    re.compile(r"\bnew\s+issue\s+(of|from)\b", re.IGNORECASE),
    re.compile(r"\b(has\s+)?(published|posted|sent)\s+(a\s+)?new\s+"
               r"(post|essay|issue|article|story)\b", re.IGNORECASE),
    re.compile(r"\bmonthly\s+newsletter\b", re.IGNORECASE),
    re.compile(r"\bweekly\s+newsletter\b", re.IGNORECASE),
    # App install and product update prompts
    re.compile(r"\bget\s+the\s+\w+\s+app\b", re.IGNORECASE),
    re.compile(r"\bdownload\s+the\b.{0,20}\bapp\b", re.IGNORECASE),
    re.compile(r"\binstall\s+the\s+app\b", re.IGNORECASE),
    # Exam / schedule notifications (Wix, etc.)
    re.compile(r"\b(exam|test|assessment)\s+schedule\b", re.IGNORECASE),
    re.compile(r"\benter\s+exam\b", re.IGNORECASE),
    # LinkedIn job counts / job search results
    re.compile(r"\b\d+\s+new\s+jobs?\b", re.IGNORECASE),           # "3 new jobs in your area"
    re.compile(r"\bjobs?\s+(matching|in\s+your|for\s+you)\b", re.IGNORECASE),
    # Substack / newsletter content format not caught by existing patterns
    re.compile(r"\b(latest|new)\s+(post|essay|article|issue)\s+from\b", re.IGNORECASE),
    re.compile(r"'s\s+(latest|new)\s+(post|essay|article|newsletter|issue)\b", re.IGNORECASE),
    # Zoom meeting invitations (distinct from webinar patterns already above)
    re.compile(r"\bzoom\s+(meeting|call|session)\s*(invite|invitation|scheduled|reminder)?\b",
               re.IGNORECASE),
    re.compile(r"\binvit(ed|ation)\s+to\s+(a\s+)?zoom\b", re.IGNORECASE),
    # Hebrew non-billing notifications
    re.compile(r"\bדרושים\b"),                   # jobs wanted / hiring ad
    re.compile(r"\bניוזלטר\b"),                  # newsletter (loan word)
    re.compile(r"\bעדכון\s+(?:חשוב|בנושא|על)\b"),    # important update / update on topic
    re.compile(r"\bהזמנה\s+ל(?:אירוע|כנס|וובינר)\b"),  # invitation to event/conference/webinar
    re.compile(r"\bפרסומת\b|\bמודעה\b"),         # advertisement / ad
    re.compile(r"\bהתרעה\b"),                    # alert / warning (non-billing security alert)
]


def match_pattern(subject: str) -> PatternType:
    """
    Returns the strongest matching pattern type.
    Priority: FAILED_PAYMENT > REFUND > CANCELLATION > TRIAL_END > TRIAL_STARTED
              > PRICE_CHANGE > RECEIPT > RENEWAL > PROMOTIONAL > NOTIFICATION > NONE
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

    for pattern in _NOTIFICATION_PATTERNS:
        if pattern.search(subject):
            return PatternType.NOTIFICATION

    return PatternType.NONE
