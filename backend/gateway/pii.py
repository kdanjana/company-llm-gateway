"""Masks personal data before a request reaches the model.

"Mail ravi@quickbite.in or call 98765 43210"  ->  "Mail [EMAIL] or call [PHONE]"

Masked types: EMAIL, CARD (credit/debit card), AADHAAR, PAN, PHONE.
Checksums cut false alarms: a 16-digit order number is only masked as a card if it passes the Luhn check,
a 12-digit number only as Aadhaar if it passes the Verhoeff check (the checks real cards / Aadhaar numbers use).

Known limits (regex-based): names and addresses are not detected; unusual formats can be missed.
The model sees the placeholders, and the answer is not un-masked.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Callable

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
# 13-19 digits, optionally grouped with spaces or dashes ("4111 1111 1111 1111").
CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
# 12 digits, first digit 2-9, optionally grouped 4-4-4.
AADHAAR_RE = re.compile(r"(?<!\d)[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}(?!\d)")
# 5 letters, 4 digits, 1 letter ("ABCDE1234F").
PAN_RE = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
# Indian mobile (optional +91 or 0 in front), or any number written with a +country code.
PHONE_RE = re.compile(r"(?<![\w+])(?:\+91[ -]?|0)?[6-9]\d{4}[ -]?\d{5}(?!\d)|\+\d{1,3}[ -]?\d{6,12}(?!\d)")


def _luhn_ok(digits: str) -> bool:
    total = 0
    for position, char in enumerate(reversed(digits)):
        n = int(char)
        if position % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


# Verhoeff checksum tables (used by Aadhaar numbers).
_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


def _verhoeff_ok(digits: str) -> bool:
    check = 0
    for position, char in enumerate(reversed(digits)):
        check = _D[check][_P[position % 8][int(char)]]
    return check == 0


# Order matters: emails first (they can contain digits), then the longer number formats before phones.
_RULES: list[tuple[str, re.Pattern[str], Callable[[str], bool] | None]] = [
    ("EMAIL", EMAIL_RE, None),
    ("CARD", CARD_RE, _luhn_ok),
    ("AADHAAR", AADHAAR_RE, _verhoeff_ok),
    ("PAN", PAN_RE, None),
    ("PHONE", PHONE_RE, None),
]


def mask_text(text: str) -> tuple[str, Counter]:
    """Returns (masked text, how many items of each type were masked)."""
    counts: Counter = Counter()
    for label, pattern, is_valid in _RULES:

        def replace(match: re.Match[str], label=label, is_valid=is_valid) -> str:
            if is_valid and not is_valid(re.sub(r"\D", "", match.group())):
                return match.group()  # looks like the format but fails the checksum: leave it
            counts[label] += 1
            return f"[{label}]"

        text = pattern.sub(replace, text)
    return text, counts


def mask_request(messages: list[dict], system: str) -> tuple[list[dict], str, int]:
    """Masks every message (user and assistant turns) and the system prompt.
    Returns (masked messages, masked system prompt, total items masked)."""
    total = 0
    masked_messages = []
    for message in messages:
        content, counts = mask_text(message["content"])
        total += sum(counts.values())
        masked_messages.append({"role": message["role"], "content": content})
    masked_system, counts = mask_text(system)
    total += sum(counts.values())
    return masked_messages, masked_system, total
