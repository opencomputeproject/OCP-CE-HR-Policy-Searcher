"""Tests for src.core.urls.normalize_url (WP-42 dedupe hardening) and
src.core.urls.translated_url (WP-9a / ADR-0009 read-in-English link)."""

import pytest

from src.core.urls import normalize_url, translated_url


class TestBasicNormalization:
    @pytest.mark.small
    def test_lowercases_scheme_and_host(self):
        assert normalize_url("HTTPS://Example.COM/Path") == "https://example.com/Path"

    @pytest.mark.small
    def test_strips_trailing_slash(self):
        assert normalize_url("https://example.com/path/") == "https://example.com/path"

    @pytest.mark.small
    def test_root_path_has_no_trailing_slash(self):
        assert normalize_url("https://example.com/") == "https://example.com"

    @pytest.mark.small
    def test_drops_fragment(self):
        assert normalize_url("https://example.com/path#section") == "https://example.com/path"

    @pytest.mark.small
    def test_empty_string_returned_unchanged(self):
        assert normalize_url("") == ""


class TestTrackingParams:
    @pytest.mark.small
    def test_strips_utm_params(self):
        url = "https://example.com/a?utm_source=x&utm_medium=y&utm_campaign=z"
        assert normalize_url(url) == "https://example.com/a"

    @pytest.mark.small
    def test_strips_fbclid(self):
        assert normalize_url("https://example.com/a?fbclid=abc123") == "https://example.com/a"

    @pytest.mark.small
    def test_strips_known_click_id_trackers(self):
        for param in ("gclid", "msclkid", "twclid", "igshid", "mc_cid", "mc_eid"):
            assert normalize_url(f"https://example.com/a?{param}=abc") == "https://example.com/a"

    @pytest.mark.small
    def test_keeps_non_tracking_query_params(self):
        assert normalize_url("https://example.com/a?id=42") == "https://example.com/a?id=42"

    @pytest.mark.small
    def test_mixed_tracking_and_real_params_keeps_only_real(self):
        url = "https://example.com/a?id=42&utm_source=x"
        assert normalize_url(url) == "https://example.com/a?id=42"


class TestGoogleNewsUnwrap:
    @pytest.mark.small
    def test_unwraps_url_param_when_present(self):
        wrapped = "https://news.google.com/url?url=https://real-site.example/article&extra=1"
        assert normalize_url(wrapped) == "https://real-site.example/article"

    @pytest.mark.small
    def test_leaves_opaque_wrapper_unchanged_when_no_url_param(self):
        # Modern Google News RSS links carry an opaque base64 id with no
        # decodable target - normalize_url cannot recover the real article,
        # so it falls back to normalizing the wrapper URL itself.
        opaque = "https://news.google.com/rss/articles/CBMiXkFVX3lxTA?oc=5"
        result = normalize_url(opaque)
        assert result.startswith("https://news.google.com/rss/articles/")

    @pytest.mark.small
    def test_unwrapped_target_is_itself_normalized(self):
        wrapped = "https://news.google.com/url?url=https://real-site.example/a/&utm_source=x"
        assert normalize_url(wrapped) == "https://real-site.example/a"


class TestVariantsCollapseToSameKey:
    @pytest.mark.small
    def test_http_https_trailing_slash_and_utm_all_collapse(self):
        variants = [
            "https://example.com/story",
            "https://example.com/story/",
            "HTTPS://EXAMPLE.COM/story",
            "https://example.com/story?utm_source=newsletter",
            "https://example.com/story/?utm_source=newsletter&utm_medium=email",
        ]
        keys = {normalize_url(v) for v in variants}
        assert len(keys) == 1

    @pytest.mark.small
    def test_unrelated_urls_never_collapse(self):
        a = normalize_url("https://example.com/story-a")
        b = normalize_url("https://example.com/story-b")
        assert a != b

    @pytest.mark.small
    def test_http_and_https_collapse_to_one_key(self):
        """The same article over http and https is one article - safe only
        because the result is a dedupe key, never fetched or stored."""
        assert normalize_url("http://example.gov/policy") == normalize_url(
            "https://example.gov/policy"
        )


class TestTranslatedUrl:
    """src.core.urls.translated_url: the direct <host>.translate.goog form,
    verified live 2026-09-02 (see the function's own docstring for the
    evidence). Computed at render time only - never stored (ADR-0009)."""

    @pytest.mark.small
    def test_round_trips_query_string(self):
        url = "https://www.riksdagen.se/sv/dokument?rm=2025&doktyp=bet"
        assert translated_url(url) == (
            "https://www-riksdagen-se.translate.goog/sv/dokument"
            "?rm=2025&doktyp=bet&_x_tr_sl=auto&_x_tr_tl=en&_x_tr_hl=en"
        )

    @pytest.mark.small
    def test_non_ascii_path_is_percent_encoded(self):
        url = "https://www.example.dk/ø/å-politik"
        assert translated_url(url) == (
            "https://www-example-dk.translate.goog/%C3%B8/%C3%A5-politik"
            "?_x_tr_sl=auto&_x_tr_tl=en&_x_tr_hl=en"
        )

    @pytest.mark.small
    def test_already_percent_encoded_path_is_not_double_encoded(self):
        url = "https://www.example.dk/%C3%B8"
        result = translated_url(url)
        assert result == (
            "https://www-example-dk.translate.goog/%C3%B8"
            "?_x_tr_sl=auto&_x_tr_tl=en&_x_tr_hl=en"
        )

    @pytest.mark.small
    def test_existing_host_dash_is_doubled(self):
        result = translated_url("https://open-data.example-gov.dk/")
        assert result.startswith("https://open--data-example--gov-dk.translate.goog/")

    @pytest.mark.small
    def test_root_path_with_no_query_string(self):
        assert translated_url("https://www.riksdagen.se/") == (
            "https://www-riksdagen-se.translate.goog/"
            "?_x_tr_sl=auto&_x_tr_tl=en&_x_tr_hl=en"
        )

    @pytest.mark.small
    def test_target_language_is_configurable(self):
        result = translated_url("https://example.com/", target="fr")
        assert "_x_tr_sl=auto&_x_tr_tl=fr&_x_tr_hl=fr" in result

    @pytest.mark.small
    def test_empty_url_returned_unchanged(self):
        assert translated_url("") == ""

    @pytest.mark.small
    def test_unparseable_url_returned_unchanged(self):
        assert translated_url("not a url") == "not a url"
