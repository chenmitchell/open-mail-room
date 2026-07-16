"""In-memory login rate limiter / lockout.

Not distributed -- fine for the single-container deployment target of this
project (see 01-REQUIREMENTS.md section 6, "single-host docker compose").
Tracks failed login attempts per key (typically `f"{ip}:{email}"`) in a
sliding window and locks the key out once `max_attempts` failures happen
within `lockout_minutes`.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict


class LoginRateLimiter:
    def __init__(self, max_attempts: int = 5, lockout_minutes: int = 15) -> None:
        self.max_attempts = max_attempts
        self.lockout_seconds = lockout_minutes * 60
        self._failures: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> None:
        window_start = now - self.lockout_seconds
        self._failures[key] = [t for t in self._failures[key] if t >= window_start]

    def is_locked(self, key: str) -> bool:
        with self._lock:
            now = time.time()
            self._prune(key, now)
            return len(self._failures[key]) >= self.max_attempts

    def record_failure(self, key: str) -> None:
        with self._lock:
            now = time.time()
            self._prune(key, now)
            self._failures[key].append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def remaining_lockout_seconds(self, key: str) -> int:
        with self._lock:
            now = time.time()
            self._prune(key, now)
            attempts = self._failures[key]
            if len(attempts) < self.max_attempts:
                return 0
            oldest_relevant = attempts[-self.max_attempts]
            unlock_at = oldest_relevant + self.lockout_seconds
            return max(0, int(unlock_at - now))


_singleton: LoginRateLimiter | None = None

# Per-IP spray guard (M0-R1 blocking #6): the per-account limiter above is
# keyed on (ip, email), so an attacker hammering many different email
# addresses from a single IP never trips any *one* of those per-account
# counters even though they're clearly attacking. 03-API-SPEC.md section 1
# requires an independent "5 times/minute/IP" limit regardless of which
# email is targeted.
_IP_MAX_ATTEMPTS = 5
_IP_LOCKOUT_MINUTES = 1  # 60 seconds

_ip_singleton: LoginRateLimiter | None = None


def get_login_rate_limiter() -> LoginRateLimiter:
    """Process-wide per-(ip,email) limiter, lazily built from current Settings.

    Lazy construction (rather than a module-level singleton) means it reads
    LOGIN_MAX_ATTEMPTS/LOGIN_LOCKOUT_MINUTES set by tests *before* the first
    login attempt in that test, instead of freezing values at import time.
    """
    global _singleton
    if _singleton is None:
        from app.config import get_settings

        settings = get_settings()
        _singleton = LoginRateLimiter(
            max_attempts=settings.login_max_attempts,
            lockout_minutes=settings.login_lockout_minutes,
        )
    return _singleton


def get_ip_rate_limiter() -> LoginRateLimiter:
    """Process-wide per-IP limiter: 5 failed attempts / 60 seconds.

    Independent of the per-account limiter above -- exists specifically to
    stop credential-spraying (many emails, one IP), which the per-account
    limiter cannot see because its key includes the email.
    """
    global _ip_singleton
    if _ip_singleton is None:
        _ip_singleton = LoginRateLimiter(
            max_attempts=_IP_MAX_ATTEMPTS, lockout_minutes=_IP_LOCKOUT_MINUTES
        )
    return _ip_singleton


def reset_login_rate_limiter() -> None:
    """Test helper: drop both singletons so they get rebuilt from Settings."""
    global _singleton, _ip_singleton
    _singleton = None
    _ip_singleton = None


# Pickup-code lookup rate limiting (M1-R1 suggestion: "pickup_code 比對用
# hmac.compare_digest+失敗計數"), mirroring the login limiter's two-tier
# shape above: one counter keyed on the exact (ip, code) pair being tried,
# and one keyed on the IP alone so a single client can't sweep through many
# *different* codes fast enough to dodge the per-code counter.
_PICKUP_CODE_MAX_ATTEMPTS = 5
_PICKUP_CODE_LOCKOUT_MINUTES = 15

_PICKUP_CODE_IP_MAX_ATTEMPTS = 20
_PICKUP_CODE_IP_LOCKOUT_MINUTES = 15

_pickup_code_singleton: LoginRateLimiter | None = None
_pickup_code_ip_singleton: LoginRateLimiter | None = None


def get_pickup_code_rate_limiter() -> LoginRateLimiter:
    """Per (ip, pickup_code) limiter for POST /pickup/lookup."""
    global _pickup_code_singleton
    if _pickup_code_singleton is None:
        _pickup_code_singleton = LoginRateLimiter(
            max_attempts=_PICKUP_CODE_MAX_ATTEMPTS,
            lockout_minutes=_PICKUP_CODE_LOCKOUT_MINUTES,
        )
    return _pickup_code_singleton


def get_pickup_code_ip_rate_limiter() -> LoginRateLimiter:
    """Per-IP limiter across all pickup codes tried from that IP."""
    global _pickup_code_ip_singleton
    if _pickup_code_ip_singleton is None:
        _pickup_code_ip_singleton = LoginRateLimiter(
            max_attempts=_PICKUP_CODE_IP_MAX_ATTEMPTS,
            lockout_minutes=_PICKUP_CODE_IP_LOCKOUT_MINUTES,
        )
    return _pickup_code_ip_singleton


def reset_pickup_code_rate_limiters() -> None:
    """Test helper: drop both pickup-code singletons so they rebuild fresh."""
    global _pickup_code_singleton, _pickup_code_ip_singleton
    _pickup_code_singleton = None
    _pickup_code_ip_singleton = None


# Inbound channel-webhook rate limiting (M3-R1 blocking #1/#2): LINE/Telegram
# deliver every inbound event (signature/secret failures *and* legitimate
# binding-code guesses) through a shared pair of endpoints
# (`POST /webhooks/line`, `POST /webhooks/telegram`). Independently of the
# per-code failed-attempt budget in app/notify/binding_codes.py, a per-IP
# counter here bounds how many requests any one source can throw at either
# endpoint per minute -- every request counts (not just failures), mirroring
# the "reused rate_limit 模式" instruction rather than inventing a new
# primitive.
_WEBHOOK_IP_MAX_ATTEMPTS = 30
_WEBHOOK_IP_LOCKOUT_MINUTES = 1

_webhook_ip_singletons: dict[str, LoginRateLimiter] = {}


def get_webhook_ip_rate_limiter(channel: str) -> LoginRateLimiter:
    """Process-wide per-IP limiter for the inbound channel webhook `channel`
    ('line' | 'telegram'), independent of the per-code attempt budget."""
    limiter = _webhook_ip_singletons.get(channel)
    if limiter is None:
        limiter = LoginRateLimiter(
            max_attempts=_WEBHOOK_IP_MAX_ATTEMPTS, lockout_minutes=_WEBHOOK_IP_LOCKOUT_MINUTES
        )
        _webhook_ip_singletons[channel] = limiter
    return limiter


def reset_webhook_ip_rate_limiters() -> None:
    """Test helper: drop every channel-webhook IP-limiter singleton."""
    _webhook_ip_singletons.clear()


# SETUP-WIZARD bootstrap rate limiting: POST /api/v1/setup runs before any
# admin account or session exists, so unlike every other mutating endpoint
# it cannot be protected by RBAC, and it is deliberately exempt from CSRF
# (see app/api/v1/setup.py's module docstring -- same reasoning as
# /auth/login). A per-IP attempt counter is the only abuse guard: it bounds
# how many times a single source can hit the endpoint (whether it succeeds,
# 409s because an admin already exists, or 400s on a weak password),
# mirroring the shape of every other limiter in this module.
_SETUP_IP_MAX_ATTEMPTS = 10
_SETUP_IP_LOCKOUT_MINUTES = 15

_setup_ip_singleton: LoginRateLimiter | None = None


def get_setup_rate_limiter() -> LoginRateLimiter:
    """Process-wide per-IP limiter for POST /api/v1/setup."""
    global _setup_ip_singleton
    if _setup_ip_singleton is None:
        _setup_ip_singleton = LoginRateLimiter(
            max_attempts=_SETUP_IP_MAX_ATTEMPTS, lockout_minutes=_SETUP_IP_LOCKOUT_MINUTES
        )
    return _setup_ip_singleton


def reset_setup_rate_limiter() -> None:
    """Test helper: drop the setup-endpoint limiter singleton."""
    global _setup_ip_singleton
    _setup_ip_singleton = None
