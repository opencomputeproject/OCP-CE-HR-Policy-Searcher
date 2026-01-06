"""Paywall detection."""

import re
from typing import Tuple

PAYWALL_KEYWORDS = [
    "subscribe to continue", "subscription required", "premium content",
    "sign in to read", "member-only", "paywall", "unlock this article",
]

PAYWALL_PATTERNS = [
    r'class="[^"]*paywall[^"]*"',
    r'class="[^"]*subscription[^"]*wall[^"]*"',
    r'id="[^"]*paywall[^"]*"',
]


def detect_paywall(html: str, text: str) -> Tuple[bool, str]:
    html_lower = html.lower()
    text_lower = text.lower()

    for keyword in PAYWALL_KEYWORDS:
        if keyword in text_lower:
            return True, f"Keyword: '{keyword}'"

    for pattern in PAYWALL_PATTERNS:
        if re.search(pattern, html_lower):
            return True, "CSS pattern detected"

    return False, ""
