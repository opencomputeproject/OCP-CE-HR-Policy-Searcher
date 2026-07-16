"""Tests for SSRF guard on externally-supplied URLs."""

from src.core.url_safety import is_public_http_url


def _resolver(mapping):
    def resolve(host):
        if host not in mapping:
            raise OSError(f"cannot resolve {host}")
        return mapping[host]
    return resolve


class TestScheme:
    def test_rejects_non_http_schemes(self):
        assert not is_public_http_url("ftp://example.com/x")
        assert not is_public_http_url("file:///etc/passwd")
        assert not is_public_http_url("gopher://example.com")
        assert not is_public_http_url("javascript:alert(1)")

    def test_rejects_missing_host(self):
        assert not is_public_http_url("http:///nohost")
        assert not is_public_http_url("not a url")


class TestLiteralIPs:
    def test_rejects_loopback(self):
        assert not is_public_http_url("http://127.0.0.1/admin")
        assert not is_public_http_url("http://[::1]/")

    def test_rejects_private_ranges(self):
        assert not is_public_http_url("http://10.0.0.5/")
        assert not is_public_http_url("http://192.168.1.1/")
        assert not is_public_http_url("http://172.16.0.1/")

    def test_rejects_cloud_metadata_endpoint(self):
        # The classic SSRF target for cloud credential theft.
        assert not is_public_http_url("http://169.254.169.254/latest/meta-data/")

    def test_rejects_unspecified(self):
        assert not is_public_http_url("http://0.0.0.0/")

    def test_allows_public_literal_ip(self):
        assert is_public_http_url("http://8.8.8.8/")


class TestHostnameResolution:
    def test_rejects_hostname_resolving_to_private(self):
        # DNS rebinding style: a public-looking host that points inward.
        resolve = _resolver({"evil.example.com": {"10.0.0.5"}})
        assert not is_public_http_url("http://evil.example.com/x", resolver=resolve)

    def test_rejects_when_any_resolved_ip_is_private(self):
        resolve = _resolver({"mixed.example.com": {"93.184.216.34", "127.0.0.1"}})
        assert not is_public_http_url("http://mixed.example.com/", resolver=resolve)

    def test_allows_public_hostname(self):
        resolve = _resolver({"example.com": {"93.184.216.34"}})
        assert is_public_http_url("https://example.com/policy", resolver=resolve)

    def test_rejects_unresolvable_host(self):
        resolve = _resolver({})
        assert not is_public_http_url("http://nope.invalid/", resolver=resolve)
