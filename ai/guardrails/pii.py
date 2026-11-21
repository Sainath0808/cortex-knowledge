"""PII detection and redaction (regex-based).

Applied before user text is logged or sent to external providers. Regex
covers structured PII (emails, phones, SSNs, cards); free-text PII (names,
addresses) would need an NER model — documented as a known limitation.
"""
import re
from dataclasses import dataclass

PII_PATTERNS: dict[str, re.Pattern] = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    "phone": re.compile(r"\b(?:\+?1[ -.]?)?\(?\d{3}\)?[ -.]?\d{3}[ -.]?\d{4}\b"),
}


@dataclass
class RedactionResult:
    text: str
    found: dict[str, int]


def redact(text: str) -> RedactionResult:
    found: dict[str, int] = {}
    redacted = text
    for label, pattern in PII_PATTERNS.items():
        matches = pattern.findall(redacted)
        if matches:
            found[label] = len(matches)
            redacted = pattern.sub(f"[REDACTED_{label.upper()}]", redacted)
    return RedactionResult(text=redacted, found=found)
