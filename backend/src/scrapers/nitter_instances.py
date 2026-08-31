"""Discovery of Nitter instances that are actually up, right now.

The instance list used to be five hardcoded bases. That list rots silently, and
every rotted entry costs a full challenge budget (75s) before the fallback even
starts. This module replaces it with candidates pulled from public registries,
verified by a live probe, ranked by what they actually returned, and shuffled.

WHY THE PROBE IS THE AUTHORITY AND THE REGISTRY IS NOT
-----------------------------------------------------
Registries publish a `status` field, and trusting it is how you end up walking a
list of hosts that stopped resolving two years ago.

Measured 2026-08-31 against qallen028/nitter-instances, the registry this module
was written for: `history/summary.json` was last written 2024-04-02, and of the
37 entries it still marks `"status": "up"`, 18 fail DNS or connect outright and
NOT ONE serves a timeline. Picking a random "up" instance from it is picking a
random gravestone. The failure is silent - every base looks like "the scraper is
broken" rather than "the list is fiction".

So registries supply CANDIDATE URLS ONLY. "Up" means "answered our probe just
now". Each candidate is classified by what it actually returned:

  TIER_TIMELINE   - plain HTTP already renders .timeline-item. Best case.
  TIER_CHALLENGE  - Cloudflare / Anubis interstitial. Plain HTTP cannot see past
                    it but camoufox usually can, so this is a CANDIDATE, not a
                    failure. nitter.freedit.eu lives here and works.
  TIER_LIMITED    - HTTP 429 / error 1015. Alive, throttling us this second.
  TIER_EMPTY      - recognisably Nitter, but no timeline. Backend broken.
  dead            - DNS failure, refused, timeout, or not Nitter at all. Dropped.

A challenged instance is deliberately NOT dropped: the plain-HTTP probe is a
weaker client than the browser that follows it, and treating "I can't see it"
as "it isn't there" would discard the instances that actually work.

REGISTRY FRESHNESS
------------------
A registry's `status` is only meaningful if the registry is still being written.
When the newest datapoint is older than NITTER_REGISTRY_MAX_AGE_DAYS, the status
field is ignored entirely and every URL becomes a candidate - a two-year-old
"up" is worth no more than a two-year-old "down", and the probe decides anyway.

Env:
  NITTER_BASES                  bypass discovery entirely (comma separated)
  NITTER_REGISTRIES             override the registry URL list (comma separated)
  NITTER_DISCOVERY              set to "0" to skip discovery and use DEFAULT_BASES
  NITTER_PROBE_TIMEOUT          per-candidate probe timeout, seconds (default 6)
  NITTER_PROBE_WORKERS          parallel probes (default 16)
  NITTER_DISCOVERY_TTL          cache lifetime in seconds (default 21600 = 6h)
  NITTER_REGISTRY_MAX_AGE_DAYS  staleness threshold (default 30)
  NITTER_SHUFFLE_SEED           fix the shuffle for reproducible debugging
  NITTER_MAX_BASES              cap the returned list (default 8)
"""

import base64
import json
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from urllib.request import ProxyHandler, Request, build_opener

# The cache is a machine-local performance artefact, NOT published data. It
# deliberately does not live in data/, which CI commits wholesale with
# `git add -f data/` - a file that rewrites itself every run would churn the
# repo and, worse, ship one runner's view of the network as though it were the
# project's. Per-run diagnostics go to health.json via LAST_RUN instead.
CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache"
CACHE_PATH = CACHE_DIR / "nitter_instances.json"

# What the most recent discover() saw, for the caller to fold into health.json.
# Populated even when discovery falls back, so "why did this run use the
# built-in list" is answerable after the fact.
LAST_RUN: dict = {"status": "not run"}

# The account probed to decide whether an instance is usable. High volume and
# long lived, so an empty timeline here means the instance is broken rather than
# the account being quiet.
PROBE_HANDLE = os.environ.get("NITTER_PROBE_HANDLE", "josemorgado")

# Known-good bases, kept as the floor. Discovery ADDS to these and reorders
# them; it never leaves the scraper with less than it had before. This list is
# also what a failed discovery falls back to, so a base that is DEFINITIVELY
# gone is removed rather than kept for sentiment - in the fallback path every
# dead entry costs a full 75s challenge budget to re-prove.
#
# Browser-verified 2026-08-31 (camoufox FF152, the same stack the scrape uses):
#   nitter.freedit.eu   cleared Cloudflare in 9s, rendered 20 timeline items
#   lightbrd.com        challenge solves, then "Waiting for lightbrd.com to
#                       respond" - Cloudflare is up, the origin behind it is not
#   nitter.kareem.one   challenge never cleared
#   nitter.tiekoetter.com  HTTP 429, alive but throttling
#   nitter.privacyredirect.com  HTTP 502
# Removed the same day: nitter.poast.org (NXDOMAIN) and nitter.net (serves a
# stub page, no timeline) - both were pure cost.
DEFAULT_BASES = [
    "https://nitter.freedit.eu",
    "https://lightbrd.com",
    "https://nitter.kareem.one",
    "https://nitter.tiekoetter.com",
    "https://nitter.privacyredirect.com",
]

# Registries are tried in order and merged; each is optional and a failure of one
# never blocks the others.
#   qallen028  - the upptime mirror. JSON list of {url, status, dailyMinutesDown}.
#                Frozen since 2024-04-02, so it is here for its URL corpus only.
#   zedeus wiki - the project's own instance table. Small but hand maintained.
#   d420        - live health monitor, {"hosts": [...], "last_update": ...}.
DEFAULT_REGISTRIES = [
    "https://raw.githubusercontent.com/qallen028/nitter-instances/master/history/summary.json",
    "https://raw.githubusercontent.com/wiki/zedeus/nitter/Instances.md",
    "https://status.d420.de/api/v1/instances",
]

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0"
)

TIER_TIMELINE = 0
TIER_CHALLENGE = 1
TIER_LIMITED = 2
TIER_EMPTY = 3
TIER_DEAD = 9

TIER_NAMES = {
    TIER_TIMELINE: "timeline",
    TIER_CHALLENGE: "challenged",
    TIER_LIMITED: "rate-limited",
    TIER_EMPTY: "nitter-empty",
    TIER_DEAD: "dead",
}

# Markers that mean "an interstitial is in front of the content", not "the
# content is gone". Kept in sync with scrapers/cloudflare.py, which is what
# actually clears them.
CHALLENGE_MARKERS = (
    "cf-mitigated",
    "challenge-platform",
    "just a moment",
    "cf_chl",
    "__cf_bm",
    "enable javascript and cookies",
    "checking your browser",
    "attention required",
    "making sure you're not a bot",
    "verifying your browser",
    "ddos-guard",
    "proof-of-work",
    "anubis",
)

RATE_LIMIT_MARKERS = ("error 1015", "you are being rate limited", "too many requests")

# Text that proves the page is Nitter rather than a parked domain or a landing
# page for some unrelated service that inherited the hostname.
#
# A bare "nitter" substring is NOT enough and was removed after it fired on
# farside.link's 404 page, which simply lists every frontend it can redirect to.
# Every marker here is structural - markup Nitter emits - not prose that any
# page discussing Nitter could contain.
NITTER_MARKERS = (
    "timeline-item",
    "profile-card",
    "profile-banner",
    'content="nitter"',
    "/js/infinitescroll.js",
    "icon-container",
)

# Instances that have publicly announced they are gone. Probing them is a waste
# of a worker slot and, in the C&D cases, of the operator's patience.
RETIRED_MARKERS = (
    "cease and desist",
    "cease-and-desist",
    "is over. thanks to",
    "until further notice",
)

_MAX_BODY = 200_000


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


# Tunables are resolved at CALL time, not import time. Binding them to module
# constants at import made every one of them silently inert unless the variable
# was already set in the environment that imported the module - which reads as
# "the setting does nothing" and is impossible to spot from the outside. Only
# NITTER_BASES and NITTER_DISCOVERY behaved correctly, because those two happen
# to be read inside discover().
_DEFAULTS = {
    "NITTER_PROBE_TIMEOUT": 6,
    "NITTER_PROBE_WORKERS": 16,
    "NITTER_DISCOVERY_TTL": 6 * 60 * 60,
    "NITTER_REGISTRY_MAX_AGE_DAYS": 30,
    "NITTER_MAX_BASES": 8,
    "NITTER_REGISTRY_TIMEOUT": 20,
}


def tunable(name: str) -> int:
    return _env_int(name, _DEFAULTS[name])


def _log(msg: str) -> None:
    print(f"    [NITTER-DISCOVERY] {msg}", flush=True)


def _opener(proxy_url: str | None):
    if not proxy_url:
        return build_opener()
    return build_opener(ProxyHandler({"http": proxy_url, "https": proxy_url}))


def normalise(url: str) -> tuple[str, str | None]:
    """Return (base_without_credentials, basic_auth_header_value_or_None).

    Registries carry entries like https://nitter:nitter@nitter.ftw.lol. urllib
    will not authenticate from a URL, and leaving the credentials in the base
    would push them into every scraped tweet link, so they are split out here
    and replayed as a header on the probe.
    """
    url = (url or "").strip().rstrip("/")
    if not url:
        return "", None
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.hostname:
        return "", None

    auth = None
    if parsed.username:
        raw = f"{parsed.username}:{parsed.password or ''}".encode()
        auth = "Basic " + base64.b64encode(raw).decode()

    netloc = parsed.hostname
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urlunparse((parsed.scheme, netloc, "", "", "", "")), auth


# --------------------------------------------------------------------------
# Registry parsing
# --------------------------------------------------------------------------

def _newest_iso_date(blob: str) -> str | None:
    """Newest YYYY-MM-DD found anywhere in the payload.

    Used as the freshness signal. Deliberately format agnostic: every registry
    seen so far stamps dates SOMEWHERE (upptime in dailyMinutesDown keys, d420 in
    last_update), and a registry that carries no date at all cannot prove it is
    fresh, which is the answer we want anyway.
    """
    dates = re.findall(r"\b(20\d{2}-[01]\d-[0-3]\d)\b", blob)
    return max(dates) if dates else None


def _registry_age_days(blob: str) -> float | None:
    newest = _newest_iso_date(blob)
    if not newest:
        return None
    try:
        when = datetime.strptime(newest, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - when).total_seconds() / 86400.0


def _parse_upptime_summary(payload) -> list[tuple[str, str]]:
    """qallen028-style: a list of {url, status, ...}. Returns (url, status)."""
    out = []
    if not isinstance(payload, list):
        return out
    for entry in payload:
        if isinstance(entry, dict) and entry.get("url"):
            out.append((str(entry["url"]), str(entry.get("status", "unknown"))))
    return out


def _parse_d420(payload) -> list[tuple[str, str]]:
    """status.d420.de: {"hosts": [...], "last_update": ...}.

    Hosts may be bare strings or objects; both shapes are accepted because the
    endpoint has returned an empty list every time it has been observed and the
    populated shape is therefore unverified. Anything unrecognised is skipped
    rather than guessed at.
    """
    out = []
    if not isinstance(payload, dict):
        return out
    for host in payload.get("hosts") or []:
        if isinstance(host, str):
            out.append((host, "up"))
        elif isinstance(host, dict):
            url = host.get("url") or host.get("host") or host.get("domain")
            if url:
                healthy = host.get("healthy", host.get("status", "up"))
                status = "up" if healthy in (True, "up", "healthy") else "down"
                out.append((str(url), status))
    return out


def _parse_markdown_table(text: str) -> list[tuple[str, str]]:
    """zedeus wiki Instances.md: markdown link tables.

    Only https:// links whose host looks like an instance are taken; the page
    also links to SSLLabs, GitHub and flag icons, which must not become
    candidates.
    """
    out = []
    for url in re.findall(r"\((https://[^)\s]+)\)", text):
        host = (urlparse(url).hostname or "").lower()
        if not host:
            continue
        if any(bad in host for bad in ("ssllabs.com", "github.com", "githubusercontent.com",
                                       "archive.org", "twitter.com", "x.com")):
            continue
        out.append((url, "unknown"))
    return out


def fetch_registry(url: str, proxy_url: str | None = None) -> list[tuple[str, str]]:
    """Pull one registry. Returns (url, status) pairs; [] on any failure.

    Logs the RAW shape - size, age, entry count - rather than only a verdict,
    because "registry returned nothing" and "registry returned 100 dead hosts"
    need opposite responses and look identical from a boolean.
    """
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
        with _opener(proxy_url).open(req, timeout=tunable("NITTER_REGISTRY_TIMEOUT")) as r:
            raw = r.read(_MAX_BODY * 20).decode("utf-8", "replace")
            status = r.status
    except Exception as e:
        _log(f"registry {url}: FAILED {type(e).__name__}: {str(e)[:120]}")
        return []

    age = _registry_age_days(raw)
    age_txt = f"{age:.0f}d old" if age is not None else "undated"

    entries: list[tuple[str, str]] = []
    payload = None
    try:
        payload = json.loads(raw)
    except ValueError:
        pass

    if payload is not None:
        entries = _parse_upptime_summary(payload) or _parse_d420(payload)
    if not entries:
        entries = _parse_markdown_table(raw)

    stale = age is not None and age > tunable("NITTER_REGISTRY_MAX_AGE_DAYS")
    up = sum(1 for _, s in entries if s == "up")
    _log(f"registry {url.split('/')[2]}: http={status} bytes={len(raw)} {age_txt} "
         f"entries={len(entries)} marked-up={up}"
         + ("  <- STALE, its status field is being ignored" if stale else ""))

    if stale:
        # A status older than the threshold carries no information, so every URL
        # becomes a candidate and the live probe decides. This is the whole
        # reason the probe exists: qallen028 has marked 37 hosts "up" since
        # April 2024 and every one of them is now dead.
        entries = [(u, "unknown") for u, _ in entries]
    return entries


# --------------------------------------------------------------------------
# Live probing
# --------------------------------------------------------------------------

def classify(base: str, auth: str | None, proxy_url: str | None,
             timeout: float | None = None) -> dict:
    """Fetch base/<PROBE_HANDLE> over plain HTTP and say what came back.

    Returns a record carrying the RAW evidence (http status, byte count, a body
    excerpt) alongside the tier, so a misclassification is diagnosable from the
    log instead of requiring a re-run.
    """
    timeout = tunable("NITTER_PROBE_TIMEOUT") if timeout is None else timeout
    url = f"{base}/{PROBE_HANDLE}"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if auth:
        headers["Authorization"] = auth

    rec = {"base": base, "auth": auth, "tier": TIER_DEAD, "http": 0,
           "bytes": 0, "note": "", "elapsed_ms": 0, "final": base}
    started = time.monotonic()
    body = ""
    final_url = url
    try:
        with _opener(proxy_url).open(Request(url, headers=headers), timeout=timeout) as r:
            rec["http"] = r.status
            final_url = r.geturl() or url
            body = r.read(_MAX_BODY).decode("utf-8", "replace")
    except Exception as e:
        # HTTPError still carries a body, and that body is exactly what tells a
        # Cloudflare interstitial (403/503, recoverable) apart from a dead host.
        # Discarding it here is what would make lightbrd.com look dead.
        code = getattr(e, "code", None)
        if code is None:
            rec["note"] = f"{type(e).__name__}: {str(e)[:90]}"
            rec["elapsed_ms"] = int((time.monotonic() - started) * 1000)
            return rec
        rec["http"] = code
        final_url = getattr(e, "url", url) or url
        try:
            body = e.read(_MAX_BODY).decode("utf-8", "replace")
        except Exception:
            body = ""

    rec["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    rec["bytes"] = len(body)
    low = body.lower()

    # urllib follows redirects, so record where we ACTUALLY landed. Two things
    # depend on it:
    #   * twiiit.com and nitter.cz both 302 to nt.vern.cc. Without this they
    #     occupy three slots in an eight-slot list that all hit one backend,
    #     and one backend's rate limit then looks like three instances failing.
    #   * a redirect that drops the handle means we were bounced to a homepage,
    #     not served a profile - see the landing-page check below.
    final = urlparse(final_url)
    rec["final"] = f"{final.scheme}://{final.netloc}" if final.netloc else base

    # A profile request that lands on a path no longer naming the handle was
    # answered by a landing page. n.opnxng.com does exactly this - it 302s to an
    # Opnxng blog whose prose mentions "Anubis", which scored it as a solvable
    # interstitial and put a hosting company's changelog into the instance list.
    if PROBE_HANDLE.lower() not in (final.path or "").lower() and "timeline-item" not in low:
        rec["tier"] = TIER_DEAD
        rec["note"] = f"redirected off the profile to {final.path or '/'} - landing page"
        return rec

    if any(m in low for m in RETIRED_MARKERS) and "timeline-item" not in low:
        rec["tier"] = TIER_DEAD
        rec["note"] = "operator retired the instance"
        return rec

    if "timeline-item" in low:
        rec["tier"] = TIER_TIMELINE
        rec["note"] = f"{low.count('timeline-item')} timeline items"
        return rec

    if any(m in low for m in CHALLENGE_MARKERS):
        rec["tier"] = TIER_CHALLENGE
        rec["note"] = "interstitial - browser may clear it"
        return rec

    if rec["http"] == 429 or any(m in low for m in RATE_LIMIT_MARKERS):
        rec["tier"] = TIER_LIMITED
        rec["note"] = "throttling right now"
        return rec

    if any(m in low for m in NITTER_MARKERS):
        rec["tier"] = TIER_EMPTY
        rec["note"] = "nitter responded but rendered no timeline"
        return rec

    rec["tier"] = TIER_DEAD
    rec["note"] = f"not nitter (http {rec['http']}, {rec['bytes']}B)"
    return rec


def probe_all(candidates: list[tuple[str, str | None]],
              proxy_url: str | None = None) -> list[dict]:
    """Probe every candidate concurrently.

    Concurrency is halved when going through a proxy. The scrape's upstream is a
    residential proxy with a per-account connection cap; opening 16 tunnels at
    once to burn through a hundred hosts is exactly the shape that trips it, and
    a refused tunnel is indistinguishable here from a dead host - so the whole
    candidate set would classify DEAD and the fix would look like "nitter is
    gone" rather than "we opened too many sockets".
    """
    if not candidates:
        return []
    workers = max(1, tunable("NITTER_PROBE_WORKERS"))
    if proxy_url:
        workers = max(1, workers // 2)
    _log(f"probing {len(candidates)} candidate(s), {workers} at a time"
         + (" via the proxy" if proxy_url else " direct"))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(
            lambda c: classify(c[0], c[1], proxy_url), candidates))


# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------

def _read_cache(ttl_s: int) -> list[str] | None:
    if ttl_s <= 0:
        return None
    try:
        blob = json.loads(CACHE_PATH.read_text())
        age = time.time() - float(blob["fetched_at"])
        bases = [b for b in blob.get("bases", []) if isinstance(b, str)]
    except Exception:
        return None
    if age > ttl_s or not bases:
        return None
    _log(f"reusing cached list ({len(bases)} bases, {age / 60:.0f} min old, "
         f"ttl {ttl_s // 60} min)")
    return bases


def _write_cache(bases: list[str], records: list[dict]) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps({
            "fetched_at": time.time(),
            "probe_handle": PROBE_HANDLE,
            "bases": bases,
            "records": [
                {k: r[k] for k in ("base", "final", "tier", "http", "bytes", "note", "elapsed_ms")}
                for r in sorted(records, key=lambda r: (r["tier"], r["base"]))
            ],
        }, indent=2))
    except Exception as e:
        _log(f"could not write {CACHE_PATH}: {type(e).__name__}: {e}")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def discover(proxy_url: str | None = None, use_cache: bool = True) -> list[str]:
    """Return Nitter bases to try, best first, shuffled within equal tiers.

    Never returns an empty list: if discovery finds nothing usable the caller
    still gets DEFAULT_BASES, so a broken registry or a firewalled runner leaves
    the scraper no worse off than the hardcoded list it replaced.
    """
    override = [b.strip().rstrip("/") for b in
                os.environ.get("NITTER_BASES", "").split(",") if b.strip()]
    if override:
        _log(f"NITTER_BASES override in effect: {override}")
        LAST_RUN.clear()
        LAST_RUN.update({"status": "env override", "bases": override})
        return override

    if os.environ.get("NITTER_DISCOVERY", "1") == "0":
        _log("discovery disabled (NITTER_DISCOVERY=0); using the built-in list")
        LAST_RUN.clear()
        LAST_RUN.update({"status": "disabled", "bases": list(DEFAULT_BASES)})
        return list(DEFAULT_BASES)

    if use_cache:
        cached = _read_cache(tunable("NITTER_DISCOVERY_TTL"))
        if cached:
            LAST_RUN.clear()
            LAST_RUN.update({"status": "cached", "bases": cached})
            return cached

    registries = [u.strip() for u in
                  os.environ.get("NITTER_REGISTRIES", "").split(",") if u.strip()] \
        or DEFAULT_REGISTRIES

    # base -> auth header. Dict keeps insertion order and dedupes hosts that
    # several registries all list.
    candidates: dict[str, str | None] = {}
    for base in DEFAULT_BASES:
        norm, auth = normalise(base)
        if norm:
            candidates[norm] = auth

    for reg in registries:
        for url, _status in fetch_registry(reg, proxy_url):
            norm, auth = normalise(url)
            if norm and norm not in candidates:
                candidates[norm] = auth

    _log(f"{len(candidates)} unique candidate host(s) from "
         f"{len(registries)} registr(ies) + {len(DEFAULT_BASES)} built-ins")

    records = probe_all(list(candidates.items()), proxy_url)

    by_tier: dict[int, list[dict]] = {}
    for rec in records:
        by_tier.setdefault(rec["tier"], []).append(rec)

    tier_counts = {TIER_NAMES[t]: len(by_tier.get(t, []))
                   for t in (TIER_TIMELINE, TIER_CHALLENGE, TIER_LIMITED,
                             TIER_EMPTY, TIER_DEAD)}
    _log("probe results: " + ", ".join(f"{k}={v}" for k, v in tier_counts.items()))

    for tier in (TIER_TIMELINE, TIER_CHALLENGE, TIER_LIMITED, TIER_EMPTY):
        for rec in sorted(by_tier.get(tier, []), key=lambda r: r["base"]):
            _log(f"  {TIER_NAMES[tier]:<13} {rec['base']:<38} "
                 f"http={rec['http']:<4} {rec['bytes']:>7}B {rec['elapsed_ms']:>5}ms  "
                 f"{rec['note']}")

    seed = os.environ.get("NITTER_SHUFFLE_SEED")
    rng = random.Random(int(seed)) if (seed or "").lstrip("-").isdigit() else random.Random()

    # Shuffling matters beyond fairness to operators: instances rate limit per
    # client after a handful of profile loads, so a fixed order means the same
    # host absorbs every run and hits its 1015 at the same point every time.
    # Ordering is by tier first, random within a tier - so a verified timeline
    # always outranks a guess, and ties are broken by chance rather than by
    # whichever registry happened to be listed first.
    # Collapse aliases. Several "instances" are only redirectors: twiiit.com and
    # nitter.cz both land on nt.vern.cc. Keeping all three would spend three of
    # eight slots on one backend, and that backend's rate limit would then read
    # as three separate instances failing.
    seen_backends: set[str] = set()
    ordered: list[str] = []
    for tier in (TIER_TIMELINE, TIER_CHALLENGE, TIER_LIMITED, TIER_EMPTY):
        bucket = by_tier.get(tier, [])
        rng.shuffle(bucket)
        # Within the shuffled bucket, a host that IS its own backend sorts ahead
        # of one that only redirects there, so the surviving slot goes to
        # nt.vern.cc rather than to nitter.cz pointing at it. Same backend either
        # way, one less redirect hop per profile load. sorted() is stable, so the
        # shuffle still decides the order among equals.
        bucket = sorted(bucket, key=lambda r: r.get("final") != r["base"])
        for rec in bucket:
            backend = rec.get("final") or rec["base"]
            if backend in seen_backends:
                _log(f"  alias        {rec['base']} -> {backend} (already listed, skipped)")
                continue
            seen_backends.add(backend)
            ordered.append(rec["base"])

    if not ordered:
        # Every candidate probed dead. That is a real, reportable state - as of
        # 2026-08 it is the expected one - but it is NOT a reason to hand the
        # browser an empty list, because the browser can clear walls this probe
        # cannot. Fall back rather than guarantee zero tweets.
        _log("no candidate answered the probe at all - falling back to the "
             "built-in list so the browser still gets its chance")
        LAST_RUN.clear()
        LAST_RUN.update({
            "status": "no live instance found",
            "candidates": len(candidates),
            "tiers": tier_counts,
            "bases": list(DEFAULT_BASES),
        })
        return list(DEFAULT_BASES)

    ordered = ordered[:max(1, tunable("NITTER_MAX_BASES"))]
    _log(f"selected {len(ordered)}: {ordered}")
    LAST_RUN.clear()
    LAST_RUN.update({
        "status": "discovered",
        "candidates": len(candidates),
        "tiers": tier_counts,
        "bases": ordered,
    })
    _write_cache(ordered, records)
    return ordered


def pick_one(proxy_url: str | None = None) -> str | None:
    """A single random instance that is up. discover() already randomises within
    tiers, so the head of the list is exactly that."""
    bases = discover(proxy_url)
    return bases[0] if bases else None


if __name__ == "__main__":
    import sys

    result = discover(os.environ.get("SCRAPER_HTTP_PROXY"),
                      use_cache="--no-cache" not in sys.argv)
    print("\n".join(result))
