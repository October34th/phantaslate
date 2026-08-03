"""
Phantaslate Relay — anonymous rate limiting
===========================================

Enforces usage limits without accounts, cookies, or durable identity.

Design constraints this satisfies:

  * No raw IP address is ever stored. IPs are normalised, then hashed with a
    secret and a day-index, so a stored key cannot be reversed to an address
    and cannot be correlated across days.
  * Nothing is written to disk. Counters live in memory and vanish on restart.
  * No CAPTCHAs, no accounts, no per-person history.

THREE LAYERS, IN ORDER OF WHAT THEY ACTUALLY PROTECT
---------------------------------------------------

1. GLOBAL DAILY BUDGET — the cost control.
   A hard ceiling on total spend per day, enforced mechanically. This is the
   only layer that actually bounds the bill, because it needs no assumption
   about how many users exist. Business plan v4.0 §5.

2. PER-CALLER CAP — the fairness control.
   Keeps one person from crowding out everyone else. It is NOT a cost
   mechanism: a per-user cap multiplied by an unknown user count is still
   unknown. Treating it as cost control was the flaw v4.0 exists to correct.

3. PER-IP CEILING — the "many addresses, not one" control.
   Deliberately loose. A maxed-out network under this ceiling costs about nine
   cents; set tight enough to matter financially it would lock out a school's
   shared wifi while a proxy-rotating abuser never encounters it at all.

Two callers share this limiter, on equal terms as of v4.0:

  extension   install token, 30,000 chars/day (PHANTASLATE_DAILY_CHARS)
  website     session token, 30,000 chars/day (PHANTASLATE_WEB_DAILY_CHARS)

Their buckets are namespaced separately, so one person using both surfaces
does not have the two allowances charged against each other. Note the
consequence: because the ceilings stack, a single address can reach
2 x (30,000 x 25) = 1,500,000 characters a day across both surfaces. That is
covered by layer 1, which is the point of having layer 1.

Both per-caller and per-IP are checked before either is charged, so a rejected
request consumes nothing.

Configuration (all optional except the salt secret in production):

  PHANTASLATE_SALT_SECRET      secret for identity hashing. If unset, a random
                               one is generated at boot — which means quotas
                               reset on every deploy. Set it in production.
  PHANTASLATE_DAILY_CHARS      per-install daily cap, extension (default 30000)
  PHANTASLATE_WEB_DAILY_CHARS  per-session daily cap, website (default 30000)
  PHANTASLATE_IP_MULTIPLIER    per-IP ceiling as a multiple of the effective
                               daily cap (default 25)
  PHANTASLATE_DAILY_BUDGET_USD global daily spend ceiling (default 2.00)
  PHANTASLATE_COST_PER_MCHARS  assumed provider cost per million characters
                               (default 0.12, DeepSeek deepseek-v4-flash)
  PHANTASLATE_MAX_TRACKED      max distinct identities held in memory
                               (default 500000, roughly 80 MB)
  PHANTASLATE_FAIL_OPEN        at memory capacity: "1" admits uncounted
                               requests, anything else refuses new identities
                               (default: refuse)
"""

import hashlib
import ipaddress
import os
import secrets
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

WINDOW_SECONDS = 86_400  # one day

# A per-process secret. Set PHANTASLATE_SALT_SECRET in production so that a
# redeploy doesn't hand everyone a fresh quota.
_SECRET = os.environ.get("PHANTASLATE_SALT_SECRET") or secrets.token_hex(32)


# --- Configuration -----------------------------------------------------------

def _daily_baseline(profile: str) -> int:
    if profile == "web":
        return int(os.environ.get("PHANTASLATE_WEB_DAILY_CHARS", "30000"))
    return int(os.environ.get("PHANTASLATE_DAILY_CHARS", "30000"))


def _multiplier() -> int:
    return int(os.environ.get("PHANTASLATE_IP_MULTIPLIER", "25"))


def _max_tracked() -> int:
    # 500,000 slotted entries measure at roughly 80 MB, which fits the Starter
    # instance alongside the app with room to spare.
    return int(os.environ.get("PHANTASLATE_MAX_TRACKED", "500000"))


def _fail_open() -> bool:
    """At memory capacity: admit uncounted traffic, or refuse new identities?

    Default is to refuse. Admitting means the limiter silently stops limiting
    at exactly the moment it is under the most pressure, and the cost lands on
    the provider bill. Refusing turns away some genuine new users, which is
    visible, recoverable, and cheap. Set PHANTASLATE_FAIL_OPEN=1 to reverse it.
    """
    return os.environ.get("PHANTASLATE_FAIL_OPEN", "").strip() == "1"


def _budget_chars() -> int:
    """Daily global ceiling, expressed in characters.

    Configured in dollars because that is the quantity actually being
    protected; converted here using an assumed provider rate.

    This is an estimate, and honest about being one: it counts *input*
    characters, while the provider bills input and output tokens separately.
    For translation the two run roughly in proportion, so the figure tracks
    real spend closely enough to act as a circuit breaker — but it is not an
    invoice. Reconcile against real provider billing periodically and adjust
    PHANTASLATE_COST_PER_MCHARS rather than assuming this is exact.
    """
    budget_usd = float(os.environ.get("PHANTASLATE_DAILY_BUDGET_USD", "2.00"))
    cost_per_m = float(os.environ.get("PHANTASLATE_COST_PER_MCHARS", "0.12"))
    if cost_per_m <= 0:
        return 0  # 0 means "no budget ceiling"
    return int((budget_usd / cost_per_m) * 1_000_000)


# Graduated compression, per business plan v4.0 §5. The baseline holds until
# the budget is most of the way spent, then steps down rather than cutting off.
# Compression is deliberately not a smooth curve: a user should experience at
# most a couple of distinct limits in a day, not a number that drifts.
_COMPRESSION_STEPS: Tuple[Tuple[float, Optional[int]], ...] = (
    (0.70, None),    # under 70% of budget: full baseline
    (0.90, 20_000),  # 70-90%: compress to 20,000
    (1.00, 10_000),  # 90-100%: compress to 10,000 — v1.0's floor, still generous
)


def _effective_daily(baseline: int, budget_used: int, budget_total: int) -> Tuple[int, Optional[str]]:
    """Return (effective cap, compression label or None)."""
    if budget_total <= 0:
        return baseline, None
    fraction = budget_used / budget_total
    for threshold, compressed in _COMPRESSION_STEPS:
        if fraction < threshold:
            if compressed is None or compressed >= baseline:
                return baseline, None
            return compressed, ("moderate" if threshold <= 0.90 else "severe")
    return 0, "exhausted"


def _day_index(now: float) -> int:
    return int(now // WINDOW_SECONDS)


# --- Identity ----------------------------------------------------------------

def normalise_ip(raw: str) -> str:
    """
    Reduce an address to the unit we want to rate-limit.

    IPv4 is returned as-is: one address is already roughly one household,
    office, or NAT gateway.

    IPv6 is truncated to its /64 prefix. This matters more than it looks.
    A single IPv6 host typically holds many addresses and rotates them — SLAAC
    privacy extensions change the low 64 bits regularly. Hashing the full
    address would put the same person in a fresh bucket every few hours, so
    IPv6 users would effectively bypass the ceiling entirely while IPv4 users
    behind school and office NAT absorbed all of it. Unfair in both directions.
    The /64 is the smallest block an ISP hands to a single subscriber, so it is
    the closest IPv6 equivalent of "one IPv4 address".

    IPv4-mapped IPv6 (::ffff:1.2.3.4) is folded back to plain IPv4 so the same
    client cannot occupy two buckets depending on how it happened to connect.

    Unparseable input is returned unchanged rather than discarded — a garbage
    value still deserves its own bucket, and silently collapsing all
    unparseable callers into one shared counter would let a malformed header
    become a denial-of-service against everyone else who sends one.
    """
    value = (raw or "").strip()
    if not value:
        return "unknown"

    # Strip a bracketed IPv6 form with optional port: [2001:db8::1]:443
    if value.startswith("["):
        end = value.find("]")
        if end != -1:
            value = value[1:end]
    # Strip an IPv4 port: 203.0.113.7:443 (never a bare IPv6, which has colons)
    elif value.count(":") == 1:
        value = value.split(":", 1)[0]

    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return value

    if addr.version == 6:
        mapped = addr.ipv4_mapped
        if mapped is not None:
            return str(mapped)
        network = ipaddress.ip_network(f"{addr}/64", strict=False)
        return str(network.network_address)

    return str(addr)


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


# --- State -------------------------------------------------------------------

@dataclass(slots=True)
class _Counter:
    """Slotted deliberately: without __slots__ each counter costs ~344 bytes
    against ~48 with it, which is the difference between 200k and 500k
    trackable identities on the same instance."""
    chars: int
    day: int


@dataclass
class Verdict:
    allowed: bool
    limit: int
    remaining: int
    reset_at: int              # unix seconds when the window rolls over
    scope: str                 # "caller"   — this install/session hit its cap
                               # "network"  — the address hit the shared ceiling
                               # "budget"   — global daily budget is spent
                               # "capacity" — limiter is full; not the caller's fault
    compression: Optional[str] = None   # None | "moderate" | "severe" | "exhausted"
    budget_fraction: float = 0.0        # 0.0-1.0+, for operational visibility


class RateLimiter:
    def __init__(self) -> None:
        self._counts: Dict[str, _Counter] = {}
        self._budget_used = 0
        self._budget_day = -1
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

    def _roll_budget(self, day: int) -> None:
        if self._budget_day != day:
            self._budget_day = day
            self._budget_used = 0

    def _used(self, key: str, day: int) -> int:
        c = self._counts.get(key)
        if c is None or c.day != day:
            return 0
        return c.chars

    def _has_capacity(self, keys: Tuple[str, ...], day: int, max_tracked: int) -> bool:
        """True if every key is either already tracked or can still be added."""
        room = max_tracked - len(self._counts)
        new_keys = sum(
            1 for k in keys
            if (c := self._counts.get(k)) is None or c.day != day
        )
        return new_keys <= room

    def _charge(self, key: str, day: int, chars: int) -> None:
        c = self._counts.get(key)
        if c is None or c.day != day:
            self._counts[key] = _Counter(chars=chars, day=day)
        else:
            c.chars += chars

    # -- public API --------------------------------------------------------

    def budget_status(self) -> Tuple[int, int, float]:
        """(used, total, fraction) for the current day. Read-only."""
        day = _day_index(time.time())
        self._roll_budget(day)
        total = _budget_chars()
        fraction = (self._budget_used / total) if total > 0 else 0.0
        return self._budget_used, total, fraction

    def check_and_consume(
        self,
        ip: str,
        caller_token: Optional[str],
        chars: int,
        profile: str = "extension",
    ) -> Verdict:
        """
        Decide whether a request of `chars` characters may proceed, and if so
        charge it against the global budget and both identities. Call this
        BEFORE the upstream model request — the whole point is to not spend
        money on traffic that is going to be rejected.

        `profile` selects the cap and namespaces the buckets: "extension" or
        "web". Namespacing matters — without it a website visitor and an
        extension user behind the same address would share one IP counter,
        and whichever arrived second would be throttled by the other's usage.
        """
        now = time.time()
        day = _day_index(now)
        reset_at = (day + 1) * WINDOW_SECONDS

        self._sweep(day, now)
        self._roll_budget(day)

        budget_total = _budget_chars()
        budget_fraction = (self._budget_used / budget_total) if budget_total > 0 else 0.0

        baseline = _daily_baseline(profile)
        daily, compression = _effective_daily(baseline, self._budget_used, budget_total)

        # --- Layer 1: global budget ---------------------------------------
        # Checked first because it is the cheapest check and the only one that
        # bounds total spend. When it binds, nobody proceeds — including
        # callers who have plenty of personal quota left.
        if daily <= 0 or (budget_total > 0 and self._budget_used + chars > budget_total):
            return Verdict(
                allowed=False,
                limit=0,
                remaining=0,
                reset_at=reset_at,
                scope="budget",
                compression="exhausted",
                budget_fraction=budget_fraction,
            )

        ip_cap = daily * _multiplier()
        ip_key = _identity(normalise_ip(ip), f"ip:{profile}", day)

        # A missing token is treated as its own bucket keyed by IP, so a
        # caller can't dodge the per-caller cap simply by omitting the header.
        token_raw = caller_token or f"anon:{normalise_ip(ip)}"
        token_key = _identity(token_raw, f"token:{profile}", day)

        ip_used = self._used(ip_key, day)
        token_used = self._used(token_key, day)

        # --- Layer 2: per-caller fairness ---------------------------------
        if token_used + chars > daily:
            return Verdict(
                allowed=False,
                limit=daily,
                remaining=max(0, daily - token_used),
                reset_at=reset_at,
                scope="caller",
                compression=compression,
                budget_fraction=budget_fraction,
            )

        # --- Layer 3: per-network ceiling ---------------------------------
        if ip_used + chars > ip_cap:
            return Verdict(
                allowed=False,
                limit=ip_cap,
                remaining=max(0, ip_cap - ip_used),
                reset_at=reset_at,
                scope="network",
                compression=compression,
                budget_fraction=budget_fraction,
            )

        # Capacity is checked here, before admitting, rather than inside
        # _charge afterwards. Charging silently on a full table would let the
        # request through uncounted — the limiter would stop limiting exactly
        # when it is under the most load.
        if not self._has_capacity((token_key, ip_key), day, _max_tracked()):
            if not _fail_open():
                return Verdict(
                    allowed=False,
                    limit=daily,
                    remaining=0,
                    reset_at=reset_at,
                    scope="capacity",
                    compression=compression,
                    budget_fraction=budget_fraction,
                )
            # Fail-open: admit, and still charge the global budget so the
            # cost ceiling holds even when per-identity tracking cannot.
            self._budget_used += chars
            return Verdict(
                allowed=True,
                limit=daily,
                remaining=max(0, daily - (token_used + chars)),
                reset_at=reset_at,
                scope="caller",
                compression=compression,
                budget_fraction=budget_fraction,
            )

        self._charge(token_key, day, chars)
        self._charge(ip_key, day, chars)
        self._budget_used += chars

        return Verdict(
            allowed=True,
            limit=daily,
            remaining=max(0, daily - (token_used + chars)),
            reset_at=reset_at,
            scope="caller",
            compression=compression,
            budget_fraction=budget_fraction,
        )


limiter = RateLimiter()


def client_ip(request) -> str:
    """
    Extract the caller's address.

    On Render the app sits behind a proxy, so request.client.host is the
    proxy. The returned value is normalised and hashed by the caller, and is
    never stored or logged raw.

    WHY THE FIRST ENTRY, AND WHEN THAT STOPS BEING TRUE
    ---------------------------------------------------
    Reading X-Forwarded-For[0] is normally unsafe: a client can send its own
    XFF header, the proxy appends to it, and the leftmost value is then
    attacker-controlled — which would make the per-IP ceiling bypassable by
    sending a random address on every request.

    It is safe here only because Render states that it *sets* the first entry
    to the real client IP rather than passing a client-supplied one through.
    That is a property of this host, not of the header.

    Two things break this assumption:

      * Putting Cloudflare's proxy (orange cloud) in front of the relay. Render
        would then see Cloudflare's edge as the client, every visitor would
        collapse into a handful of addresses, and the per-IP ceiling would
        throttle unrelated users as a group. If that change is ever made, read
        CF-Connecting-IP here instead.
      * Moving off Render. Most hosts append rather than overwrite, in which
        case the correct value is the Nth entry from the *right*, where N is
        the number of trusted proxies.

    Anything touching this function should re-check which of those is true.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
