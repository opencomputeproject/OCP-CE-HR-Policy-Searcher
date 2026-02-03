"""Tests for access denial diagnosis in fetchers."""

from src.crawler.fetchers.http_fetcher import diagnose_denial_from_text


class TestDiagnoseDenialFromText:
    """Tests for diagnose_denial_from_text function."""

    def test_cloudflare_server_header(self):
        """Should detect Cloudflare from Server header."""
        result = diagnose_denial_from_text(403, "", {"server": "cloudflare"})
        assert "Cloudflare bot protection" in result
        assert "403" in result

    def test_akamai_server_header(self):
        """Should detect Akamai from Server header."""
        result = diagnose_denial_from_text(403, "", {"server": "AkamaiGHost"})
        assert "Akamai WAF" in result

    def test_body_access_denied(self):
        """Should detect 'Access Denied' in response body."""
        result = diagnose_denial_from_text(403, "<h1>Access Denied</h1>", {})
        assert "Access Denied" in result

    def test_body_bot_detection(self):
        """Should detect bot detection message in body."""
        result = diagnose_denial_from_text(
            403, "Our systems detected bot detection activity from your IP", {}
        )
        assert "bot detection" in result

    def test_body_rate_limit(self):
        """Should detect rate limit message in body."""
        result = diagnose_denial_from_text(
            429, "You have exceeded the rate limit", {}
        )
        assert "rate limited" in result

    def test_no_clues(self):
        """Should return plain HTTP code when no patterns match."""
        result = diagnose_denial_from_text(403, "<html>error</html>", {})
        assert result == "HTTP 403"

    def test_empty_body(self):
        """Should handle empty body gracefully."""
        result = diagnose_denial_from_text(403, "", {})
        assert result == "HTTP 403"

    def test_server_header_case_insensitive(self):
        """Server header matching should be case-insensitive."""
        result = diagnose_denial_from_text(403, "", {"server": "CLOUDFLARE"})
        assert "Cloudflare" in result

    def test_body_truncated_to_2000(self):
        """Should only check first 2000 chars of body."""
        # Pattern at position > 2000 should not be found
        body = "x" * 2001 + "cloudflare"
        result = diagnose_denial_from_text(403, body, {})
        assert result == "HTTP 403"
