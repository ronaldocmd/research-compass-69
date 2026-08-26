"""SSRF protection for the document downloader (RDA-053).

The downloader fetches URLs that originate from external search results
(OpenAlex/Crossref). A malicious or compromised result could point at an
internal address (e.g. ``http://169.254.169.254/`` cloud metadata,
``http://localhost:...``, or a private-network service) and the downloader
would fetch it. This guard validates a URL before it is fetched:

* only ``http``/``https`` schemes are allowed;
* the hostname is resolved and every resolved address must be a public
  (non-blocked) IP.

Blocked ranges cover loopback, private, link-local (including the cloud
metadata address 169.254.169.254), CGNAT, documentation, multicast and
reserved networks, for both IPv4 and IPv6.

The guard is a small, standalone class so it can be unit-tested with a fake
resolver and injected into ``DocumentDownloader`` (which defaults to the
real guard).
"""

import ipaddress
import socket
from urllib.parse import urlparse

from app.services.downloader.exceptions import DownloadError

# IPv4 networks that must never be fetched by the downloader.
_BLOCKED_IPV4_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),        # "this" network / unspecified
    ipaddress.ip_network("10.0.0.0/8"),       # private
    ipaddress.ip_network("100.64.0.0/10"),    # CGNAT
    ipaddress.ip_network("127.0.0.0/8"),      # loopback
    ipaddress.ip_network("169.254.0.0/16"),   # link-local (incl. 169.254.169.254 metadata)
    ipaddress.ip_network("172.16.0.0/12"),    # private
    ipaddress.ip_network("192.0.0.0/24"),     # IETF protocol assignments
    ipaddress.ip_network("192.0.2.0/24"),     # documentation
    ipaddress.ip_network("192.168.0.0/16"),   # private
    ipaddress.ip_network("198.18.0.0/15"),    # benchmarking
    ipaddress.ip_network("198.51.100.0/24"),  # documentation
    ipaddress.ip_network("203.0.113.0/24"),   # documentation
    ipaddress.ip_network("224.0.0.0/4"),      # multicast
    ipaddress.ip_network("240.0.0.0/4"),      # reserved
]

# IPv6 networks that must never be fetched by the downloader.
_BLOCKED_IPV6_NETWORKS = [
    ipaddress.ip_network("::/128"),           # unspecified
    ipaddress.ip_network("::1/128"),          # loopback
    ipaddress.ip_network("::ffff:0:0/96"),    # IPv4-mapped (handled via v4 check)
    ipaddress.ip_network("64:ff9b::/96"),     # NAT64
    ipaddress.ip_network("100::/64"),         # discard-only
    ipaddress.ip_network("2001:db8::/32"),    # documentation
    ipaddress.ip_network("fc00::/7"),         # unique local
    ipaddress.ip_network("fe80::/10"),        # link-local
    ipaddress.ip_network("ff00::/8"),         # multicast
]


class SSRFBlockedError(DownloadError):
    """The URL resolves to an address the downloader is not allowed to fetch."""


class SSRFGuard:
    """Validates that a URL is safe for the downloader to fetch."""

    def __init__(self, resolver=None) -> None:
        """``resolver`` is a callable ``(host) -> list[str]`` of IP strings.

        Defaults to ``socket.getaddrinfo``. Injectable so tests can avoid
        real DNS lookups.
        """
        self._resolver = resolver or self._default_resolve

    def validate(self, url: str) -> None:
        """Raise ``SSRFBlockedError`` if ``url`` must not be fetched."""
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise SSRFBlockedError(
                f"URL scheme {parsed.scheme!r} is not allowed; only http/https"
            )
        host = parsed.hostname
        if not host:
            raise SSRFBlockedError("URL has no host")

        addresses = self._resolver(host)
        if not addresses:
            raise SSRFBlockedError(f"Could not resolve host {host!r}")

        for address in addresses:
            ip = self._parse_ip(address)
            if ip is None:
                continue
            if self._is_blocked(ip):
                raise SSRFBlockedError(
                    f"URL host {host!r} resolves to blocked address {ip}"
                )

    @staticmethod
    def _default_resolve(host: str) -> list[str]:
        try:
            infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except socket.gaierror:
            return []
        return [info[4][0] for info in infos]

    @staticmethod
    def _parse_ip(address: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
        try:
            return ipaddress.ip_address(address)
        except ValueError:
            return None

    @classmethod
    def _is_blocked(cls, ip) -> bool:
        if isinstance(ip, ipaddress.IPv4Address):
            return any(ip in network for network in _BLOCKED_IPV4_NETWORKS)
        if isinstance(ip, ipaddress.IPv6Address):
            # IPv4-mapped IPv6 addresses (::ffff:a.b.c.d) are really IPv4.
            if ip.ipv4_mapped is not None:
                return cls._is_blocked(ip.ipv4_mapped)
            return any(ip in network for network in _BLOCKED_IPV6_NETWORKS)
        return True
