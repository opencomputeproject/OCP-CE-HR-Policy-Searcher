"""SSRF guard for externally-supplied URLs.

Leads carry a source_url that comes from community submissions and news
feeds — attacker-influenceable input. Before the server fetches such a
URL (a lead "chase"), reject anything that is not a public http(s)
address, so a crafted lead cannot make the server reach cloud metadata
endpoints (169.254.169.254), localhost, or internal services.

Note: this resolves the hostname and checks the resolved address, which
closes the "public name -> private IP" case. It does not fully close DNS
rebinding (a name that resolves public here but private at connect
time); pinning the resolved IP through to the socket would be the next
step if fetches move to a hardened transport.
"""

import ipaddress
import socket
from typing import Callable
from urllib.parse import urlparse


def _default_resolver(host: str) -> set[str]:
    return {info[4][0] for info in socket.getaddrinfo(host, None)}


def _is_public_ip(ip: ipaddress._BaseAddress) -> bool:
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def is_public_http_url(
    url: str, resolver: Callable[[str], set[str]] = _default_resolver
) -> bool:
    """True only if url is http(s) and its host resolves to public IPs.

    resolver is injectable for testing; it maps a hostname to the set of
    IP strings it resolves to and raises OSError when it cannot resolve.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if not host:
        return False

    # Literal IP: check directly, no DNS.
    try:
        return _is_public_ip(ipaddress.ip_address(host))
    except ValueError:
        pass

    # Hostname: resolve and require every address to be public.
    try:
        addresses = resolver(host)
    except OSError:
        return False
    if not addresses:
        return False
    try:
        return all(_is_public_ip(ipaddress.ip_address(a)) for a in addresses)
    except ValueError:
        return False
