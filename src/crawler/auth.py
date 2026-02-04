"""Site authentication for crawling paywalled or login-gated sites.

Coordinates credential application across HTTP and Playwright fetchers.
Supports four auth types: form, basic, cookie, header.
"""

import base64
from urllib.parse import urlparse
from typing import Optional

from ..config.credentials import SiteCredential


class AuthenticationError(Exception):
    """Raised when authentication fails."""


class Authenticator:
    """Manages site credentials and applies authentication to fetchers.

    Holds credentials indexed by domain hostname.  Provides methods to:

    1. Look up whether a domain has credentials.
    2. Perform form-based login via Playwright (once per session).
    3. Return per-request auth headers for HTTP basic / custom header auth.
    4. Return cookies for cookie-based auth.
    """

    def __init__(self, credentials: list[SiteCredential]):
        self._credentials: dict[str, SiteCredential] = {}
        for cred in credentials:
            self._credentials[cred.domain.lower()] = cred

        # Track which form-auth domains have completed login
        self._authenticated_domains: set[str] = set()

    # ------------------------------------------------------------------
    # Lookup helpers
    # ------------------------------------------------------------------

    def get_credential(self, url: str) -> Optional[SiteCredential]:
        """Look up credential for a URL by matching its hostname."""
        hostname = urlparse(url).netloc.lower() if "://" in url else url.lower()
        return self._credentials.get(hostname)

    def has_credential(self, url: str) -> bool:
        """Check whether a URL's domain has stored credentials."""
        return self.get_credential(url) is not None

    def needs_playwright(self, url: str) -> bool:
        """Check whether a URL's credential requires Playwright (form auth)."""
        cred = self.get_credential(url)
        return cred is not None and cred.auth_type == "form"

    @property
    def has_form_credentials(self) -> bool:
        """True if any credential requires form-based auth."""
        return any(c.auth_type == "form" for c in self._credentials.values())

    @property
    def form_credentials(self) -> list[SiteCredential]:
        """Return all form-based credentials."""
        return [c for c in self._credentials.values() if c.auth_type == "form"]

    @property
    def domains(self) -> list[str]:
        """Return all domains with credentials."""
        return list(self._credentials.keys())

    def is_form_authenticated(self, domain: str) -> bool:
        """Check if form auth has already been performed for a domain."""
        return domain.lower() in self._authenticated_domains

    # ------------------------------------------------------------------
    # Form-based login
    # ------------------------------------------------------------------

    async def authenticate_form(
        self, credential: SiteCredential, playwright_context
    ) -> bool:
        """Perform form-based login in a Playwright browser context.

        Opens the login page, fills credentials, submits the form, and
        waits for navigation.  Session cookies persist in the context.

        Args:
            credential: A form-type ``SiteCredential``.
            playwright_context: Playwright ``BrowserContext``.

        Returns:
            True if login navigation completed successfully.

        Raises:
            AuthenticationError: If login fails.
        """
        if credential.auth_type != "form":
            raise AuthenticationError(
                f"authenticate_form called with auth_type='{credential.auth_type}'"
            )

        page = await playwright_context.new_page()
        try:
            await page.goto(
                credential.login_url,
                wait_until="domcontentloaded",
                timeout=15000,
            )

            await page.fill(credential.username_field, credential.username)
            await page.fill(
                credential.password_field,
                credential.password.get_secret_value(),
            )
            await page.click(credential.submit_button)

            # Wait for post-login navigation
            await page.wait_for_load_state("domcontentloaded", timeout=15000)

            self._authenticated_domains.add(credential.domain.lower())
            return True

        except Exception as e:
            raise AuthenticationError(
                f"Form login failed for {credential.domain}: {type(e).__name__}"
            ) from e
        finally:
            await page.close()

    # ------------------------------------------------------------------
    # Per-request auth for HTTP fetcher
    # ------------------------------------------------------------------

    def get_http_auth_headers(self, url: str) -> dict[str, str]:
        """Return extra HTTP headers for a URL based on its credential.

        Handles ``basic`` and ``header`` auth types.  Returns empty dict
        if no credential applies or the type is form/cookie.
        """
        cred = self.get_credential(url)
        if cred is None:
            return {}

        if cred.auth_type == "basic":
            raw = f"{cred.username}:{cred.password.get_secret_value()}"
            encoded = base64.b64encode(raw.encode()).decode()
            return {"Authorization": f"Basic {encoded}"}

        if cred.auth_type == "header":
            return dict(cred.headers) if cred.headers else {}

        return {}

    def get_cookies(self, url: str) -> list[dict]:
        """Return cookies to inject for a URL.

        Returns a list of cookie dicts compatible with Playwright's
        ``context.add_cookies()`` and httpx's cookies API.
        """
        cred = self.get_credential(url)
        if cred is None or cred.auth_type != "cookie":
            return []

        hostname = urlparse(url).netloc.lower() if "://" in url else url.lower()

        cookies = []
        for c in cred.cookies:
            cookie: dict = {
                "name": c.name,
                "value": c.value,
                "domain": c.domain or hostname,
                "path": c.path or "/",
            }
            if c.secure:
                cookie["secure"] = True
            if c.http_only:
                cookie["httpOnly"] = True
            cookies.append(cookie)

        return cookies
