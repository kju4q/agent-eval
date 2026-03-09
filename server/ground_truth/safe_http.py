from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx


class EgressPolicyError(RuntimeError):
    pass


def safe_request(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    allowed_hosts: set[str],
    **kwargs,
) -> httpx.Response:
    _enforce_url_policy(url, allowed_hosts=allowed_hosts)
    return client.request(method, url, **kwargs)


def _enforce_url_policy(url: str, *, allowed_hosts: set[str]) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise EgressPolicyError("Only https egress is allowed.")
    hostname = parsed.hostname
    if not hostname:
        raise EgressPolicyError("Missing hostname for egress request.")
    host = hostname.lower()

    if not any(host == allowed or host.endswith(f".{allowed}") for allowed in allowed_hosts):
        raise EgressPolicyError(f"Host '{hostname}' is not in egress allowlist.")

    if _looks_private_host(hostname):
        raise EgressPolicyError(f"Host '{hostname}' resolves to a private or reserved address.")


def _looks_private_host(hostname: str) -> bool:
    try:
        ip = ipaddress.ip_address(hostname)
        return _ip_disallowed(ip)
    except ValueError:
        pass

    try:
        infos = socket.getaddrinfo(hostname, None)
    except OSError:
        # If DNS lookup fails, block rather than silently bypassing checks.
        return True

    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if _ip_disallowed(ip):
            return True
    return False


def _ip_disallowed(ip: ipaddress._BaseAddress) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )

