"""URL normalization for dedupe keying (WP-42).

Both the news sweep's in-batch dedupe (``src.signals.news.dedupe_items``) and
the lead store's cross-week dedupe (``src.storage.leads._dedupe_key``) key on
a URL. Real-world feeds hand back the same article under enough cosmetic
variants (``http`` vs ``https``, a trailing slash, ``utm_*`` tracking params,
a Google News redirect wrapper) that keying on the raw URL leaves an easy
dedupe hole. :func:`normalize_url` collapses those variants to one canonical
form; unrelated URLs are never merged.

Deliberately best-effort: an unparseable input is returned unchanged rather
than raising - a dedupe key that fails to normalize should still work as a
(less effective) literal key, not crash the sweep.
"""

from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

# Google Analytics campaign params, plus the common click-id trackers
# ("fbclid-style") that ad platforms append. Stripping these means
# "the same article, shared from a different campaign link" normalizes
# to one key instead of one per share.
_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAM_NAMES = {
    "fbclid", "gclid", "msclkid", "twclid", "igshid", "mc_cid", "mc_eid",
}


def _is_tracking_param(name: str) -> bool:
    lower = name.lower()
    return lower.startswith(_TRACKING_PARAM_PREFIXES) or lower in _TRACKING_PARAM_NAMES


def normalize_url(url: str) -> str:
    """Canonicalize a URL for use as a dedupe key.

    - Unwraps a ``news.google.com`` redirect link to its ``url=`` target
      when present (recursively normalized), since that target is the real
      article and the wrapper's opaque ID is not a stable dedupe key.
    - Lowercases scheme and host (URLs are case-sensitive in the path, but
      never in scheme/host).
    - Strips a trailing slash from the path.
    - Drops ``utm_*``/``fbclid``-style tracking query params.
    - Drops the fragment (never part of what identifies the resource here).

    Callers must not treat the result as a redirect target to fetch or as
    the value to store - it is a key, not a URL to use for anything else.
    """
    if not url:
        return url
    try:
        parts = urlsplit(url)
    except ValueError:
        return url

    if parts.hostname == "news.google.com":
        target = dict(parse_qsl(parts.query)).get("url")
        if target:
            return normalize_url(target)

    scheme = parts.scheme.lower()
    # The same article served over http and https is one article. Safe only
    # because this is a dedupe KEY, never a URL anything fetches or stores.
    if scheme == "http":
        scheme = "https"
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/")
    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_tracking_param(k)
    ]
    query = urlencode(query_pairs)
    return urlunsplit((scheme, netloc, path, query, ""))


def translated_url(url: str, target: str = "en") -> str:
    """Build a Google website-translator link for ``url``, rendering the
    page in ``target`` (default English). Used for the "Read in English"
    link on a non-English source (ADR-0009) - never fetched or stored by
    this tool, computed fresh at render time.

    Verified live 2026-09-02 against ``https://www.riksdagen.se/``: the
    direct ``<host-with-dots-as-dashes>.translate.goog`` form built here
    resolves. A GET of
    ``https://www-riksdagen-se.translate.goog/?_x_tr_sl=auto&_x_tr_tl=en
    &_x_tr_hl=en`` returned ``302`` to ``.../sv/?...`` - the same single
    same-origin redirect the untranslated ``https://www.riksdagen.se/``
    itself makes to ``/sv/`` (riksdagen.se's own root/locale redirect, not
    a property of Google's proxy) - and following that one hop landed on
    the translate.goog domain with ``200``. The older
    ``https://translate.google.com/translate?sl=auto&tl=en&u=<url>`` form
    was also probed and confirmed to ``302`` straight to this same direct
    form, confirming it is now just an extra hop in front of it - so the
    direct form is what is built here.

    An existing dash in the host is doubled (translate.goog reserves a
    single dash as the dot-replacement marker) before every dot becomes a
    single dash. The original path and query string are preserved: each
    path segment is percent-encoded (idempotent against a segment that is
    already percent-encoded, so non-ASCII characters survive either way),
    and the translator's own ``_x_tr_*`` params are appended after any
    existing query string rather than replacing it.

    Best-effort like :func:`normalize_url`: a URL with no scheme/host is
    returned unchanged rather than raising, since this only ever feeds a
    display link, never a fetch.
    """
    if not url:
        return url
    parts = urlsplit(url)
    if not parts.scheme or not parts.hostname:
        return url

    host = parts.hostname.replace("-", "--").replace(".", "-")
    netloc = f"{host}.translate.goog"

    path = "/".join(quote(segment, safe="%") for segment in parts.path.split("/")) or "/"

    tr_params = f"_x_tr_sl=auto&_x_tr_tl={target}&_x_tr_hl={target}"
    query = f"{parts.query}&{tr_params}" if parts.query else tr_params

    return urlunsplit(("https", netloc, path, query, ""))
