"""SSRF guard for admin-configured outbound URLs (07-SECURITY.md section 5;
M2-R1 blocking #1).

`ai_provider_configs.base_url` is admin-settable and is later used as the
target of a *server-side* HTTP call carrying a decrypted provider API key
(app/ocr/providers.py's `OpenAICompatibleProvider`). Without a guard, a
compromised/careless admin account (or a supply-chain-poisoned admin UI)
could point `base_url` at an internal service -- e.g. the cloud metadata
endpoint `169.254.169.254`, a Kubernetes/Docker control-plane IP, or an
internal admin panel on RFC1918 space -- and use the OCR pipeline as an SSRF
proxy that also happily attaches an `Authorization: Bearer <api_key>` header
to the request.

At the same time, 04-AI-OCR.md sections 2/5 explicitly document pointing
`base_url` at a local Ollama instance (a private-network address by
definition, e.g. `http://192.168.1.20:11434/v1` or `http://localhost:11434/v1`)
as a supported, privacy-preserving deployment mode. So this is *not* a blanket
ban on private addresses -- it is opt-in: `AiProviderConfig.allow_private_network`
(default `False`) must be explicitly set `True` for a config whose `base_url`
resolves to a private/loopback/link-local/reserved address to be accepted.

The check runs once, at config create/update time (not per-request) --
resolving the hostname is a one-time admin-config-time guard, not a
request-time SSRF filter (that would need to also defend against DNS
rebinding between check-time and call-time, which is out of scope here per
the task brief's "create/update 時解析 host" wording).
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

_LOCAL_HOSTNAMES = {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}


class UnsafeBaseUrlError(ValueError):
    """Raised when `base_url` resolves to a private/reserved network and
    `allow_private_network` was not explicitly set."""


def _is_private_or_reserved(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _hostname_of(base_url: str) -> str:
    parsed = urlsplit(base_url)
    hostname = parsed.hostname
    if not hostname:
        raise UnsafeBaseUrlError(
            f"base_url '{base_url}' has no parseable hostname; refusing to save it"
        )
    return hostname


def check_base_url_allowed(base_url: str | None, *, allow_private_network: bool) -> None:
    """Raises `UnsafeBaseUrlError` if `base_url` points at a private/reserved
    network and `allow_private_network` is not set. A `None`/empty
    `base_url` (provider has no configurable endpoint, e.g. Anthropic/Google)
    is always fine -- there's nothing to check."""
    if not base_url:
        return

    hostname = _hostname_of(base_url)

    if allow_private_network:
        return

    # Literal IP in the URL (http://169.254.169.254/... etc) -- no DNS lookup
    # needed, and this also covers the cloud-metadata address explicitly
    # called out by the task brief (169.254.169.254 is link-local).
    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None

    if literal_ip is not None:
        if _is_private_or_reserved(literal_ip):
            raise UnsafeBaseUrlError(
                f"base_url host '{hostname}' is a private/reserved address; "
                "set allow_private_network=true to allow it (e.g. a local Ollama instance)"
            )
        return

    lowered = hostname.lower()
    if lowered in _LOCAL_HOSTNAMES or lowered.endswith(".local"):
        raise UnsafeBaseUrlError(
            f"base_url host '{hostname}' is a loopback/local hostname; "
            "set allow_private_network=true to allow it (e.g. a local Ollama instance)"
        )

    # Best-effort DNS resolution. A hostname that fails to resolve right now
    # (offline dev box, DNS hiccup, ...) is not treated as unsafe -- it simply
    # isn't a private-network hit *yet*; failing closed here would make this
    # endpoint flaky in exactly the environments (sandboxes, CI) where it
    # matters least.
    try:
        infos = socket.getaddrinfo(hostname, None)
    except OSError:
        return

    for info in infos:
        addr = info[4][0]
        try:
            resolved_ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if _is_private_or_reserved(resolved_ip):
            raise UnsafeBaseUrlError(
                f"base_url host '{hostname}' resolves to a private/reserved address "
                f"({addr}); set allow_private_network=true to allow it "
                "(e.g. a local Ollama instance)"
            )
