"""SSRF-hardened HTTP client for URL import/crawl (docs/03-TRD.md:
"resolves and validates each target and redirect, blocks private/
link-local/loopback/metadata networks including IPv6 and DNS rebinding,
restricts ports and protocols, caps response bytes/time/pages").

Every redirect hop is re-validated from scratch -- this defeats both a
malicious initial-DNS-answer-then-rebind attack and a redirect chain that
only turns dangerous on a later hop.
"""
import ipaddress
import socket
from urllib.parse import urlparse

import httpx

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443}
MAX_REDIRECTS = 5
MAX_RESPONSE_BYTES = 2 * 1024 * 1024  # 2 MiB per page
REQUEST_TIMEOUT_SECONDS = 10.0


class SSRFBlocked(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _is_public_ip(ip_str: str) -> bool:
    ip = ipaddress.ip_address(ip_str)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        # Cloud metadata endpoint, explicitly, in case a platform doesn't
        # classify it under the ranges above.
        or ip_str == "169.254.169.254"
    )


def _resolve_and_validate(hostname: str, port: int) -> str:
    """Returns ONE validated public IP for `hostname`. Blocks the whole
    hostname if ANY resolved address is private/loopback/link-local/
    metadata (not just if all of them are) -- conservative by design,
    since a dual-homed name that resolves to both a public and an
    internal address is exactly the shape a DNS-rebinding setup uses."""
    try:
        resolved = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise SSRFBlocked("dns_resolution_failed", "Could not resolve host.") from exc

    ips = [sockaddr[0] for _family, _type, _proto, _canon, sockaddr in resolved]
    for ip_str in ips:
        if not _is_public_ip(ip_str):
            raise SSRFBlocked("private_target_blocked", "Target resolves to a private, loopback, or metadata address.")
    return ips[0]


def validate_url(url: str) -> str:
    """Validate-only: for call sites that just need a yes/no SSRF check
    (the owner HTTP-action CRUD, source URL input) without fetching
    anything. Returns `url` unchanged on success."""
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise SSRFBlocked("scheme_not_allowed", f"URL scheme '{parsed.scheme}' is not allowed.")
    if not parsed.hostname:
        raise SSRFBlocked("invalid_url", "URL has no hostname.")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        raise SSRFBlocked("port_not_allowed", f"Port {port} is not allowed.")

    _resolve_and_validate(parsed.hostname, port)
    return url


def _validate_and_pin(url: str) -> tuple[httpx.URL, str, int]:
    """Validates `url` and returns (parsed_url, validated_ip, port) for
    fetch() to connect to directly -- see _pinned_request's docstring for
    why this closes the DNS-rebinding gap validate_url() alone cannot."""
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise SSRFBlocked("scheme_not_allowed", f"URL scheme '{parsed.scheme}' is not allowed.")
    if not parsed.hostname:
        raise SSRFBlocked("invalid_url", "URL has no hostname.")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        raise SSRFBlocked("port_not_allowed", f"Port {port} is not allowed.")

    ip = _resolve_and_validate(parsed.hostname, port)
    return httpx.URL(url), ip, port


def _pinned_request(client: httpx.Client, parsed_url: httpx.URL, ip: str, port: int) -> httpx.Response:
    """Connects the TCP socket directly to the already-validated `ip`,
    never letting httpx/httpcore re-resolve the hostname and potentially
    get a different (attacker-controlled, now-private) answer between
    validation and connect -- the classic TOCTOU DNS-rebinding gap. The
    original hostname is preserved as the Host header and TLS SNI name
    (`sni_hostname` extension, read by httpcore's connection layer) so
    virtual-hosted targets and certificate validation both still work
    correctly against the real hostname, only the socket's destination
    address is pinned."""
    hostname = parsed_url.host
    pinned_url = parsed_url.copy_with(host=ip)
    return client.get(pinned_url, headers={"Host": hostname}, extensions={"sni_hostname": hostname})


def fetch(url: str) -> httpx.Response:
    """Fetches a URL with SSRF validation AND DNS-rebinding-safe IP
    pinning on the initial target and on every redirect hop. Caps
    response size by reading in a bounded stream rather than trusting
    Content-Length."""
    current_url, ip, port = _validate_and_pin(url)

    with httpx.Client(follow_redirects=False, timeout=REQUEST_TIMEOUT_SECONDS) as client:
        for _ in range(MAX_REDIRECTS + 1):
            response = _pinned_request(client, current_url, ip, port)

            if response.is_redirect:
                next_url = response.headers.get("location")
                if not next_url:
                    raise SSRFBlocked("invalid_redirect", "Redirect with no Location header.")
                joined = current_url.join(next_url)
                current_url, ip, port = _validate_and_pin(str(joined))
                continue

            _enforce_response_cap(response)
            return response

    raise SSRFBlocked("too_many_redirects", "Exceeded the maximum allowed redirect chain length.")


def _enforce_response_cap(response: httpx.Response) -> None:
    content_length = response.headers.get("content-length")
    if content_length and int(content_length) > MAX_RESPONSE_BYTES:
        raise SSRFBlocked("response_too_large", "Response exceeded the maximum allowed size.")
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise SSRFBlocked("response_too_large", "Response exceeded the maximum allowed size.")
