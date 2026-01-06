"""JS requirement detection."""

from typing import Tuple

JS_INDICATORS = [
    "please enable javascript", "javascript is required",
    "this page requires javascript",
]

FRAMEWORK_PLACEHOLDERS = [
    '<div id="root"></div>',
    '<div id="app"></div>',
    '<div id="__next"></div>',
]


def detect_js_required(html: str, text: str) -> Tuple[bool, str]:
    html_lower = html.lower()
    text_lower = text.lower()

    for indicator in JS_INDICATORS:
        if indicator in text_lower or indicator in html_lower:
            return True, f"Message: '{indicator}'"

    for placeholder in FRAMEWORK_PLACEHOLDERS:
        if placeholder.lower() in html_lower and len(text.strip()) < 500:
            return True, f"Empty framework: {placeholder}"

    return False, ""
