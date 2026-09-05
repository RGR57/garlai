from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit, urlunsplit


def _normalized_url(url: str) -> tuple[str, str, str, str, str]:
    if not isinstance(url, str) or not url.strip():
        raise ValueError("Navigation URL must be a non-empty string.")
    parsed = urlsplit(url.strip())
    if not parsed.scheme or not parsed.hostname:
        raise ValueError("Navigation URL must include a scheme and host.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Navigation URL must not embed credentials.")
    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower()
    port = parsed.port
    netloc = host if port is None else f"{host}:{port}"
    return scheme, host, netloc, parsed.path or "/", parsed.query


def _reject_non_public_host(host: str) -> None:
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise ValueError("Navigation to local hostnames is not permitted.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if not address.is_global:
        raise ValueError("Navigation to non-public IP addresses is not permitted.")


class ProductionNavigationPolicy:
    """Public HTTPS browser navigation policy for production runtime use."""

    def validate(self, url: str) -> str:
        scheme, host, netloc, path, query = _normalized_url(url)
        if scheme != "https":
            raise ValueError("Production browser navigation requires HTTPS.")
        _reject_non_public_host(host)
        return urlunsplit((scheme, netloc, path, query, ""))

    def validate_resolved_addresses(self, addresses: tuple[str, ...]) -> None:
        if not addresses:
            raise ValueError("Navigation host did not resolve to an address.")
        for address in addresses:
            try:
                parsed = ipaddress.ip_address(address)
            except ValueError as exc:
                raise ValueError("Navigation host resolved to an invalid address.") from exc
            if not parsed.is_global:
                raise ValueError("Navigation host resolved to a non-public address.")


class LocalFixtureNavigationPolicy:
    """Test-only exact-origin exception for one deterministic loopback fixture."""

    def __init__(self, origin: str) -> None:
        scheme, host, netloc, path, query = _normalized_url(origin)
        if scheme != "http" or host != "127.0.0.1" or path != "/" or query:
            raise ValueError("Local fixture origin must be an exact http://127.0.0.1:<port> origin.")
        if ":" not in netloc:
            raise ValueError("Local fixture origin must include an explicit port.")
        self._origin = f"{scheme}://{netloc}"

    def validate(self, url: str) -> str:
        scheme, _host, netloc, path, query = _normalized_url(url)
        origin = f"{scheme}://{netloc}"
        if origin != self._origin:
            raise ValueError("Navigation is outside the exact local fixture origin.")
        return urlunsplit((scheme, netloc, path, query, ""))
