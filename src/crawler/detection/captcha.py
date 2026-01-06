"""CAPTCHA detection."""

from typing import Tuple

CAPTCHA_INDICATORS = [
    "recaptcha", "hcaptcha", "cloudflare", "turnstile",
    "verify you are human", "prove you're not a robot",
    "security check", "checking your browser",
]


def detect_captcha(html: str) -> Tuple[bool, str]:
    html_lower = html.lower()

    for indicator in CAPTCHA_INDICATORS:
        if indicator in html_lower:
            return True, f"Detected: {indicator}"

    return False, ""
