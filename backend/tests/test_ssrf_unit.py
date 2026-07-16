"""Unit tests for app.security.ssrf (M2-R1 blocking #1) -- pure-function
tests against `check_base_url_allowed` directly, complementing the
HTTP-level coverage in tests/test_ai_providers.py. All cases use literal
IPs/well-known hostnames so none of them depend on real DNS resolution
being available in the test sandbox.
"""

from __future__ import annotations

import pytest

from app.security.ssrf import UnsafeBaseUrlError, check_base_url_allowed


def test_none_base_url_is_always_allowed():
    check_base_url_allowed(None, allow_private_network=False)


def test_empty_base_url_is_always_allowed():
    check_base_url_allowed("", allow_private_network=False)


def test_public_ip_is_allowed_by_default():
    check_base_url_allowed("http://8.8.8.8/v1", allow_private_network=False)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:11434/v1",
        "http://10.0.0.5/v1",
        "http://172.16.0.5/v1",
        "http://172.31.255.255/v1",
        "http://192.168.1.20:11434/v1",
        "http://169.254.169.254/latest/meta-data/",
        "http://localhost:11434/v1",
        "http://[::1]:11434/v1",
    ],
)
def test_private_and_loopback_and_link_local_rejected_by_default(url):
    with pytest.raises(UnsafeBaseUrlError):
        check_base_url_allowed(url, allow_private_network=False)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:11434/v1",
        "http://192.168.1.20:11434/v1",
        "http://169.254.169.254/latest/meta-data/",
        "http://localhost:11434/v1",
    ],
)
def test_allow_private_network_flag_opts_in(url):
    check_base_url_allowed(url, allow_private_network=True)


def test_url_with_no_hostname_is_rejected():
    with pytest.raises(UnsafeBaseUrlError):
        check_base_url_allowed("not-a-url", allow_private_network=False)


def test_public_hostname_that_fails_to_resolve_is_not_treated_as_unsafe():
    # A hostname (not a literal IP) that the sandbox's DNS cannot resolve --
    # this must never raise, per app/security/ssrf.py's "best-effort DNS"
    # comment: failing closed here would make the endpoint flaky wherever
    # DNS is unavailable, which is exactly a test sandbox.
    check_base_url_allowed(
        "http://this-host-name-should-never-resolve.invalid/v1", allow_private_network=False
    )
