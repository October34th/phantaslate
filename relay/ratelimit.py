"""
Phantaslate Relay — anonymous rate limiting
===========================================

Enforces a daily character cap without accounts, cookies, or durable identity.

Design constraints this satisfies:

  * No raw IP address is ever stored. IPs are hashed with a secret and a
    day-index before use, so a stored key cannot be reversed to an address
    and cannot be correlated across days.
  * Nothing is written to disk. Counters live in memory and vanish on restart.
  * No CAPTCHAs, no accounts, no per-person history.

Two identifiers, checked together:

  install token   the extension's own anonymous ID. Carries the user-facing
                  cap (default 20,000 chars/day). Trivially reset by
                  reinstalling — that's fine, it's not the abuse defence.
  hashed IP       carries a higher ceiling (default 5x). This is what actually
                  catches someone cycling install tokens in a loop. The
                  multiplier exists because IPs are shared: offices,
                  universities, and mobile carriers put many real users behind
                  one address, and a 1:1 cap would punish them.

Both are checked before either is charged, so a rejected request consumes
nothing.

Configuration (all optional except the salt secret in production):

  PHANTASLATE_SALT_SECRET   secret for identity hashing. If unset, a random
                            one is generated at boot — which means counters
                            reset on every deploy. Set it in production.
  PHANTASLATE_DAILY_CHARS   per-install daily cap (default 20000)
  PHANTASLATE_IP_MULTIPLIER per-IP ceiling as a multiple of the above (default 5)
  PHANTASLATE_MAX_TRACKED   max distinct identities held in memory (default 200000)
"""

import hashlib
import os
import secrets
import time
from dataclasses import dataclass
from typing import Dict, Optional

WINDOW_SECONDS = 86_400  # one day

# A per-process secret. Set PHANTASLATE_SALT_SECRET in production so that a
# redeploy doesn't hand everyone a fresh quota.
_SECRET = os.environ.get("PHANTASLATE_SALT_SECRET") or secrets.token_hex(32)


def _config() -> tuple:
    """Read caps at call time so they can be changed without a code edit."""
    daily = int(os.environ.get("PHANTASLATE_DAILY_CHARS", "20000"))
    multiplier = int(os.environ.get("PHANTASLATE_IP_MULTIPLIER", "5"))
    max_tracked = int(os.environ.get("PHANTASLATE_MAX_TRACKED", "200000"))
    return daily, multiplier, max_tracked


def _day_index(now: float) -> int:
    return int(now // WINDOW_SECONDS)


def _identity(raw: str, kind: str, day: int) -> str:
    """
    Hash an identifier with the process secret and the current day index.

    The day index is part of the input, so yesterday's hash of the same IP is
    a completely different string from today's. That is what makes the
    "cannot be correlated across time periods" claim true rather than
    aspirational.
    """
    material = f"{_SECRET}|{kind}|{day}|{raw}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:32]


@dataclass
class _Counter:
    chars: int
    day: int


@dataclass
class Verdict:
    allowed: bool
    limit: int
    remaining: int
    reset_at: int          # unix seconds when the window rolls over
    scope: str             # "install" or "network" — which cap was hit


class RateLimiter:
    def __init__(self) -> None:
        self._counts: Dict[str, _Counter] = {}
        self._last_sweep = 0.0

    # -- internals ---------------------------------------------------------

    def _sweep(self, day: int, now: float) -> None:
        """Drop counters from previous days. Cheap, and keeps memory bounded."""
        if now - self._last_sweep < 300:  # at most every 5 minutes
            return
        self._last_sweep = now
        stale = [k for k, c in self._counts.items() if c.day != day]
        for k in stale:
            del self._counts[k]

    def _used(self, key: str, day: int) -> int:
        c = self._counts.get(key)
        if c is None or c.day != day:
            return 0
        return c.chars

    def _charge(self, key: str, day: int, chars: int, max_tracked: int) -> None:
        c = self._counts.get(key)
        if c is None or c.day != day:
            if len(self._counts) >= max_tracked:
                # Memory guard. Under a flood we stop tracking new identities
                # rather than growing without bound. Existing counters keep
                # working; new ones go uncounted until the next sweep.
                return
            self._counts[key] = _Counter(chars=chars, day=day)
        else:
            c.chars += chars

    # -- public API --------------------------------------------------------

    def check_and_consume(
        self,
        ip: str,
        install_token: Optional[str],
        chars: int,
    ) -> Verdict:
        """
        Decide whether a request of `chars` characters may proceed, and if so
        charge it against both identities. Call this BEFORE the upstream model
        request — the whole point is to not spend money on rejected traffic.
        """
        now = time.time()
        day = _day_index(now)
        reset_at = (day + 1) * WINDOW_SECONDS
        daily, multiplier, max_tracked = _config()

        self._sweep(day, now)

        ip_cap = daily * multiplier
        ip_key = _identity(ip, "ip", day)

        # A missing token is treated as its own bucket keyed by IP, so a
        # caller can't dodge the install cap simply by omitting the header.
        token_raw = install_token or f"anon:{ip}"
        token_key = _identity(token_raw, "install", day)

        ip_used = self._used(ip_key, day)
        token_used = self._used(token_key, day)

        # Check both before charging either.
        if token_used + chars > daily:
            return Verdict(
                allowed=False,
                limit=daily,
                remaining=max(0, daily - token_used),
                reset_at=reset_at,
                scope="install",
            )

        if ip_used + chars > ip_cap:
            return Verdict(
                allowed=False,
                limit=ip_cap,
                remaining=max(0, ip_cap - ip_used),
                reset_at=reset_at,
                scope="network",
            )

        self._charge(token_key, day, chars, max_tracked)
        self._charge(ip_key, day, chars, max_tracked)

        return Verdict(
            allowed=True,
            limit=daily,
            remaining=max(0, daily - (token_used + chars)),
            reset_at=reset_at,
            scope="install",
        )


limiter = RateLimiter()


def client_ip(request) -> str:
    """
    Extract the caller's address.

    On Render the app sits behind a proxy, so request.client.host is the
    proxy. X-Forwarded-For's first entry is the original client. This value
    is hashed immediately by the caller and never stored or logged raw.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
