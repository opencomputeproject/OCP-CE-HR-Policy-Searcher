"""Unit tests for credential loading and validation."""

import pytest
import yaml
from pydantic import SecretStr, ValidationError

from src.config.credentials import CookieEntry, SiteCredential, load_credentials


# ---------------------------------------------------------------------------
# SiteCredential model validation
# ---------------------------------------------------------------------------


class TestSiteCredentialFormAuth:
    """Test form-type credential validation."""

    def test_valid_form_credential(self):
        cred = SiteCredential(
            domain="example.com",
            auth_type="form",
            login_url="https://example.com/login",
            username="user",
            password=SecretStr("pass"),
            username_field="#user",
            password_field="#pass",
            submit_button="button[type=submit]",
        )
        assert cred.auth_type == "form"
        assert cred.domain == "example.com"

    def test_form_missing_login_url_raises(self):
        with pytest.raises(ValidationError, match="login_url"):
            SiteCredential(
                domain="example.com",
                auth_type="form",
                username="user",
                password=SecretStr("pass"),
                username_field="#user",
                password_field="#pass",
                submit_button="button",
            )

    def test_form_missing_password_raises(self):
        with pytest.raises(ValidationError, match="password"):
            SiteCredential(
                domain="example.com",
                auth_type="form",
                login_url="https://example.com/login",
                username="user",
                username_field="#user",
                password_field="#pass",
                submit_button="button",
            )

    def test_form_missing_selectors_raises(self):
        with pytest.raises(ValidationError, match="username_field"):
            SiteCredential(
                domain="example.com",
                auth_type="form",
                login_url="https://example.com/login",
                username="user",
                password=SecretStr("pass"),
                password_field="#pass",
                submit_button="button",
            )


class TestSiteCredentialBasicAuth:
    """Test basic-type credential validation."""

    def test_valid_basic_credential(self):
        cred = SiteCredential(
            domain="internal.example.com",
            auth_type="basic",
            username="user",
            password=SecretStr("pass"),
        )
        assert cred.auth_type == "basic"

    def test_basic_missing_username_raises(self):
        with pytest.raises(ValidationError, match="username and password"):
            SiteCredential(
                domain="example.com",
                auth_type="basic",
                password=SecretStr("pass"),
            )

    def test_basic_missing_password_raises(self):
        with pytest.raises(ValidationError, match="username and password"):
            SiteCredential(
                domain="example.com",
                auth_type="basic",
                username="user",
            )


class TestSiteCredentialCookieAuth:
    """Test cookie-type credential validation."""

    def test_valid_cookie_credential(self):
        cred = SiteCredential(
            domain="portal.example.com",
            auth_type="cookie",
            cookies=[CookieEntry(name="session", value="abc123")],
        )
        assert cred.auth_type == "cookie"
        assert len(cred.cookies) == 1

    def test_cookie_empty_list_raises(self):
        with pytest.raises(ValidationError, match="at least one cookie"):
            SiteCredential(
                domain="example.com",
                auth_type="cookie",
                cookies=[],
            )

    def test_cookie_none_raises(self):
        with pytest.raises(ValidationError, match="at least one cookie"):
            SiteCredential(
                domain="example.com",
                auth_type="cookie",
            )


class TestSiteCredentialHeaderAuth:
    """Test header-type credential validation."""

    def test_valid_header_credential(self):
        cred = SiteCredential(
            domain="api.legiscan.com",
            auth_type="header",
            headers={"X-API-Key": "test_key"},
        )
        assert cred.auth_type == "header"
        assert cred.headers["X-API-Key"] == "test_key"

    def test_header_missing_headers_raises(self):
        with pytest.raises(ValidationError, match="at least one header"):
            SiteCredential(
                domain="example.com",
                auth_type="header",
            )

    def test_header_empty_dict_raises(self):
        with pytest.raises(ValidationError, match="at least one header"):
            SiteCredential(
                domain="example.com",
                auth_type="header",
                headers={},
            )


class TestSiteCredentialGeneral:
    """General SiteCredential tests."""

    def test_invalid_auth_type_raises(self):
        with pytest.raises(ValidationError):
            SiteCredential(
                domain="example.com",
                auth_type="oauth",
            )

    def test_repr_does_not_expose_secrets(self):
        cred = SiteCredential(
            domain="example.com",
            auth_type="basic",
            username="user",
            password=SecretStr("super_secret_password"),
        )
        repr_str = repr(cred)
        assert "super_secret_password" not in repr_str
        assert "example.com" in repr_str
        assert "basic" in repr_str

    def test_password_is_secret_str(self):
        cred = SiteCredential(
            domain="example.com",
            auth_type="basic",
            username="user",
            password=SecretStr("secret"),
        )
        assert isinstance(cred.password, SecretStr)
        assert cred.password.get_secret_value() == "secret"
        assert "secret" not in str(cred.password)


# ---------------------------------------------------------------------------
# CookieEntry model
# ---------------------------------------------------------------------------


class TestCookieEntry:
    """Test CookieEntry model."""

    def test_required_fields(self):
        cookie = CookieEntry(name="session", value="abc")
        assert cookie.name == "session"
        assert cookie.value == "abc"

    def test_defaults(self):
        cookie = CookieEntry(name="s", value="v")
        assert cookie.path == "/"
        assert cookie.secure is False
        assert cookie.http_only is False
        assert cookie.domain is None

    def test_custom_values(self):
        cookie = CookieEntry(
            name="s", value="v",
            domain=".example.com", path="/app",
            secure=True, http_only=True,
        )
        assert cookie.domain == ".example.com"
        assert cookie.path == "/app"
        assert cookie.secure is True
        assert cookie.http_only is True


# ---------------------------------------------------------------------------
# load_credentials()
# ---------------------------------------------------------------------------


class TestLoadCredentials:
    """Test the load_credentials function."""

    def test_missing_file_returns_empty(self, tmp_path):
        result = load_credentials(tmp_path / "nonexistent.yaml")
        assert result == []

    def test_empty_file_returns_empty(self, tmp_path):
        f = tmp_path / "creds.yaml"
        f.write_text("", encoding="utf-8")
        result = load_credentials(f)
        assert result == []

    def test_empty_credentials_key_returns_empty(self, tmp_path):
        f = tmp_path / "creds.yaml"
        f.write_text("credentials: []\n", encoding="utf-8")
        result = load_credentials(f)
        assert result == []

    def test_loads_valid_basic_credential(self, tmp_path):
        f = tmp_path / "creds.yaml"
        f.write_text(yaml.dump({
            "credentials": [{
                "domain": "example.com",
                "auth_type": "basic",
                "username": "user",
                "password": "pass",
            }]
        }), encoding="utf-8")
        result = load_credentials(f)
        assert len(result) == 1
        assert result[0].domain == "example.com"
        assert result[0].auth_type == "basic"
        assert result[0].password.get_secret_value() == "pass"

    def test_loads_valid_header_credential(self, tmp_path):
        f = tmp_path / "creds.yaml"
        f.write_text(yaml.dump({
            "credentials": [{
                "domain": "api.example.com",
                "auth_type": "header",
                "headers": {"X-API-Key": "test123"},
            }]
        }), encoding="utf-8")
        result = load_credentials(f)
        assert len(result) == 1
        assert result[0].headers["X-API-Key"] == "test123"

    def test_loads_multiple_credentials(self, tmp_path):
        f = tmp_path / "creds.yaml"
        f.write_text(yaml.dump({
            "credentials": [
                {"domain": "a.com", "auth_type": "basic", "username": "u", "password": "p"},
                {"domain": "b.com", "auth_type": "header", "headers": {"X": "Y"}},
            ]
        }), encoding="utf-8")
        result = load_credentials(f)
        assert len(result) == 2

    def test_invalid_entry_raises(self, tmp_path):
        f = tmp_path / "creds.yaml"
        f.write_text(yaml.dump({
            "credentials": [{
                "domain": "example.com",
                "auth_type": "basic",
                # Missing username and password
            }]
        }), encoding="utf-8")
        with pytest.raises((ValidationError, ValueError)):
            load_credentials(f)
