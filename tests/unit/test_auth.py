"""Unit tests for the Authenticator class."""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from src.config.credentials import CookieEntry, SiteCredential
from src.crawler.auth import AuthenticationError, Authenticator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _basic_cred(domain="internal.example.com"):
    return SiteCredential(
        domain=domain,
        auth_type="basic",
        username="user",
        password=SecretStr("pass"),
    )


def _header_cred(domain="api.legiscan.com"):
    return SiteCredential(
        domain=domain,
        auth_type="header",
        headers={"X-API-Key": "test_key_123"},
    )


def _cookie_cred(domain="portal.example.com"):
    return SiteCredential(
        domain=domain,
        auth_type="cookie",
        cookies=[
            CookieEntry(name="session_id", value="abc123"),
            CookieEntry(name="auth_token", value="xyz789"),
        ],
    )


def _form_cred(domain="example.com"):
    return SiteCredential(
        domain=domain,
        auth_type="form",
        login_url="https://example.com/login",
        username="admin",
        password=SecretStr("secret"),
        username_field="#username",
        password_field="#password",
        submit_button="button[type=submit]",
    )


# ---------------------------------------------------------------------------
# Lookup tests
# ---------------------------------------------------------------------------


class TestAuthenticatorLookup:
    """Test credential lookup by URL hostname."""

    def test_get_credential_by_url(self):
        auth = Authenticator([_basic_cred()])
        cred = auth.get_credential("https://internal.example.com/page")
        assert cred is not None
        assert cred.domain == "internal.example.com"

    def test_get_credential_returns_none_for_unknown(self):
        auth = Authenticator([_basic_cred()])
        assert auth.get_credential("https://other.com/page") is None

    def test_get_credential_by_hostname_string(self):
        auth = Authenticator([_basic_cred()])
        cred = auth.get_credential("internal.example.com")
        assert cred is not None

    def test_has_credential_true(self):
        auth = Authenticator([_basic_cred()])
        assert auth.has_credential("https://internal.example.com/x") is True

    def test_has_credential_false(self):
        auth = Authenticator([_basic_cred()])
        assert auth.has_credential("https://other.com/x") is False

    def test_case_insensitive_lookup(self):
        auth = Authenticator([_basic_cred("Example.COM")])
        assert auth.get_credential("https://example.com/page") is not None

    def test_needs_playwright_for_form(self):
        auth = Authenticator([_form_cred()])
        assert auth.needs_playwright("https://example.com/page") is True

    def test_needs_playwright_false_for_basic(self):
        auth = Authenticator([_basic_cred()])
        assert auth.needs_playwright("https://internal.example.com/page") is False

    def test_needs_playwright_false_for_unknown(self):
        auth = Authenticator([_basic_cred()])
        assert auth.needs_playwright("https://other.com/page") is False


class TestAuthenticatorProperties:
    """Test Authenticator properties."""

    def test_has_form_credentials_true(self):
        auth = Authenticator([_form_cred(), _basic_cred()])
        assert auth.has_form_credentials is True

    def test_has_form_credentials_false(self):
        auth = Authenticator([_basic_cred(), _header_cred()])
        assert auth.has_form_credentials is False

    def test_form_credentials_list(self):
        auth = Authenticator([_form_cred(), _basic_cred()])
        assert len(auth.form_credentials) == 1
        assert auth.form_credentials[0].auth_type == "form"

    def test_domains_list(self):
        auth = Authenticator([_basic_cred(), _header_cred()])
        assert set(auth.domains) == {"internal.example.com", "api.legiscan.com"}

    def test_empty_authenticator(self):
        auth = Authenticator([])
        assert auth.has_form_credentials is False
        assert auth.form_credentials == []
        assert auth.domains == []

    def test_is_form_authenticated_initially_false(self):
        auth = Authenticator([_form_cred()])
        assert auth.is_form_authenticated("example.com") is False


# ---------------------------------------------------------------------------
# HTTP auth headers
# ---------------------------------------------------------------------------


class TestGetHttpAuthHeaders:
    """Test per-request HTTP auth header generation."""

    def test_basic_auth_header(self):
        auth = Authenticator([_basic_cred()])
        headers = auth.get_http_auth_headers("https://internal.example.com/page")

        expected = base64.b64encode(b"user:pass").decode()
        assert headers == {"Authorization": f"Basic {expected}"}

    def test_custom_headers(self):
        auth = Authenticator([_header_cred()])
        headers = auth.get_http_auth_headers("https://api.legiscan.com/api")
        assert headers == {"X-API-Key": "test_key_123"}

    def test_empty_for_form_auth(self):
        auth = Authenticator([_form_cred()])
        headers = auth.get_http_auth_headers("https://example.com/page")
        assert headers == {}

    def test_empty_for_cookie_auth(self):
        auth = Authenticator([_cookie_cred()])
        headers = auth.get_http_auth_headers("https://portal.example.com/page")
        assert headers == {}

    def test_empty_for_unknown_domain(self):
        auth = Authenticator([_basic_cred()])
        headers = auth.get_http_auth_headers("https://other.com/page")
        assert headers == {}


# ---------------------------------------------------------------------------
# Cookies
# ---------------------------------------------------------------------------


class TestGetCookies:
    """Test cookie generation for cookie-auth domains."""

    def test_returns_cookie_list(self):
        auth = Authenticator([_cookie_cred()])
        cookies = auth.get_cookies("https://portal.example.com/page")
        assert len(cookies) == 2
        assert cookies[0]["name"] == "session_id"
        assert cookies[0]["value"] == "abc123"
        assert cookies[1]["name"] == "auth_token"

    def test_default_domain_from_hostname(self):
        auth = Authenticator([_cookie_cred()])
        cookies = auth.get_cookies("https://portal.example.com/page")
        assert cookies[0]["domain"] == "portal.example.com"

    def test_custom_cookie_domain(self):
        cred = SiteCredential(
            domain="portal.example.com",
            auth_type="cookie",
            cookies=[CookieEntry(name="s", value="v", domain=".example.com")],
        )
        auth = Authenticator([cred])
        cookies = auth.get_cookies("https://portal.example.com/page")
        assert cookies[0]["domain"] == ".example.com"

    def test_default_path(self):
        auth = Authenticator([_cookie_cred()])
        cookies = auth.get_cookies("https://portal.example.com/page")
        assert cookies[0]["path"] == "/"

    def test_empty_for_non_cookie_auth(self):
        auth = Authenticator([_basic_cred()])
        cookies = auth.get_cookies("https://internal.example.com/page")
        assert cookies == []

    def test_empty_for_unknown_domain(self):
        auth = Authenticator([_cookie_cred()])
        cookies = auth.get_cookies("https://other.com/page")
        assert cookies == []


# ---------------------------------------------------------------------------
# Form-based login (mocked Playwright)
# ---------------------------------------------------------------------------


class TestAuthenticateForm:
    """Test form-based authentication with mocked Playwright."""

    @pytest.mark.asyncio
    async def test_form_login_fills_and_submits(self):
        """authenticate_form fills fields and clicks submit."""
        mock_page = AsyncMock()
        mock_context = AsyncMock()
        mock_context.new_page.return_value = mock_page

        auth = Authenticator([_form_cred()])
        cred = auth.form_credentials[0]

        result = await auth.authenticate_form(cred, mock_context)

        assert result is True
        mock_page.goto.assert_called_once_with(
            "https://example.com/login",
            wait_until="domcontentloaded",
            timeout=15000,
        )
        mock_page.fill.assert_any_call("#username", "admin")
        mock_page.fill.assert_any_call("#password", "secret")
        mock_page.click.assert_called_once_with("button[type=submit]")
        mock_page.wait_for_load_state.assert_called_once()
        mock_page.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_form_login_marks_authenticated(self):
        """After successful login, is_form_authenticated returns True."""
        mock_context = AsyncMock()
        mock_context.new_page.return_value = AsyncMock()

        auth = Authenticator([_form_cred()])
        cred = auth.form_credentials[0]

        await auth.authenticate_form(cred, mock_context)

        assert auth.is_form_authenticated("example.com") is True

    @pytest.mark.asyncio
    async def test_form_login_failure_raises(self):
        """Failed form login raises AuthenticationError."""
        mock_page = AsyncMock()
        mock_page.goto.side_effect = Exception("Connection refused")
        mock_context = AsyncMock()
        mock_context.new_page.return_value = mock_page

        auth = Authenticator([_form_cred()])
        cred = auth.form_credentials[0]

        with pytest.raises(AuthenticationError, match="example.com"):
            await auth.authenticate_form(cred, mock_context)

    @pytest.mark.asyncio
    async def test_form_login_closes_page_on_failure(self):
        """Page is closed even if login fails."""
        mock_page = AsyncMock()
        mock_page.goto.side_effect = Exception("timeout")
        mock_context = AsyncMock()
        mock_context.new_page.return_value = mock_page

        auth = Authenticator([_form_cred()])
        cred = auth.form_credentials[0]

        with pytest.raises(AuthenticationError):
            await auth.authenticate_form(cred, mock_context)

        mock_page.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_form_login_not_marked_on_failure(self):
        """Failed login does not mark domain as authenticated."""
        mock_page = AsyncMock()
        mock_page.goto.side_effect = Exception("timeout")
        mock_context = AsyncMock()
        mock_context.new_page.return_value = mock_page

        auth = Authenticator([_form_cred()])
        cred = auth.form_credentials[0]

        with pytest.raises(AuthenticationError):
            await auth.authenticate_form(cred, mock_context)

        assert auth.is_form_authenticated("example.com") is False

    @pytest.mark.asyncio
    async def test_wrong_auth_type_raises(self):
        """authenticate_form rejects non-form credentials."""
        mock_context = AsyncMock()
        auth = Authenticator([_basic_cred()])

        with pytest.raises(AuthenticationError, match="auth_type='basic'"):
            await auth.authenticate_form(_basic_cred(), mock_context)
