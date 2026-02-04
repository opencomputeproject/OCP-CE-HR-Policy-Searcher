"""Credential loading and validation for paywalled sites.

Reads site credentials from ``config/credentials.yaml`` (if it exists) and
validates them with Pydantic models.  Four auth types are supported:

- **form** -- Playwright fills a login form and persists session cookies.
- **basic** -- HTTP Basic Auth (``Authorization`` header per request).
- **cookie** -- Injects cookies into the browser context / HTTP client.
- **header** -- Adds custom HTTP headers per request (API keys, bearer tokens).

Security notes
--------------
* ``config/credentials.yaml`` is in ``.gitignore`` -- only the ``.example``
  file ships with the repository.
* Passwords use ``pydantic.SecretStr`` so they are never exposed via
  ``repr()`` or serialisation.
* ``SiteCredential.__repr__`` is overridden to show only domain + auth_type.
"""

from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, SecretStr, model_validator


class CookieEntry(BaseModel):
    """A single cookie to inject."""

    name: str
    value: str
    domain: Optional[str] = None
    path: Optional[str] = "/"
    secure: Optional[bool] = False
    http_only: Optional[bool] = False


class SiteCredential(BaseModel):
    """Credential configuration for a single domain."""

    domain: str  # Hostname, e.g. "example.com"
    auth_type: Literal["form", "basic", "cookie", "header"]

    # Form auth fields
    login_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[SecretStr] = None
    username_field: Optional[str] = None
    password_field: Optional[str] = None
    submit_button: Optional[str] = None

    # Cookie auth fields
    cookies: Optional[list[CookieEntry]] = None

    # Header auth fields
    headers: Optional[dict[str, str]] = None

    @model_validator(mode="after")
    def validate_required_fields(self) -> "SiteCredential":
        """Validate that required fields are present for each auth_type."""
        if self.auth_type == "form":
            missing = [
                f
                for f in (
                    "login_url",
                    "username",
                    "password",
                    "username_field",
                    "password_field",
                    "submit_button",
                )
                if getattr(self, f) is None
            ]
            if missing:
                raise ValueError(
                    f"Form auth for '{self.domain}' missing required fields: {missing}"
                )

        elif self.auth_type == "basic":
            if not self.username or not self.password:
                raise ValueError(
                    f"Basic auth for '{self.domain}' requires username and password"
                )

        elif self.auth_type == "cookie":
            if not self.cookies:
                raise ValueError(
                    f"Cookie auth for '{self.domain}' requires at least one cookie entry"
                )

        elif self.auth_type == "header":
            if not self.headers:
                raise ValueError(
                    f"Header auth for '{self.domain}' requires at least one header"
                )

        return self

    def __repr__(self) -> str:
        """Safe repr that never exposes secrets."""
        return f"SiteCredential(domain='{self.domain}', auth_type='{self.auth_type}')"


def load_credentials(
    credentials_path: Optional[Path] = None,
) -> list[SiteCredential]:
    """Load site credentials from YAML file.

    Returns an empty list if the file does not exist.  This is the expected
    default -- most users will not have a credentials file.

    Args:
        credentials_path: Override path (for testing).  Defaults to
            ``config/credentials.yaml``.

    Returns:
        List of validated ``SiteCredential`` objects.

    Raises:
        ValueError: If the YAML contains invalid credential entries.
    """
    path = credentials_path or Path("config/credentials.yaml")

    if not path.exists():
        return []

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    raw_creds = data.get("credentials", [])
    if not raw_creds:
        return []

    credentials: list[SiteCredential] = []
    for entry in raw_creds:
        # Convert password string to SecretStr if present
        if "password" in entry and isinstance(entry["password"], str):
            entry["password"] = SecretStr(entry["password"])
        credentials.append(SiteCredential(**entry))

    return credentials
