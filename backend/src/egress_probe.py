"""Which egress can actually clear a Nitter instance's Cloudflare challenge?

Answers one question that cannot be measured off a GitHub runner: proxied or
direct. The residential proxy rotates its exit IP PER CONNECTION (documented
upstream, and measured 2026-09-01: four consecutive requests exited in Korea,
the US, France and Indonesia). A Cloudflare managed challenge issues clearance
to a consistent client, so a rotating exit may be structurally incapable of
clearing one no matter how long it is given - while a runner's own address is
stable but has a datacenter reputation. This prints which of the two works.

As of 2026-09-03 it also answers a second question that only the runner can:
what sources are LEFT. X Corp began sending cease-and-desist letters to public
Nitter operators in late August 2026, so "which instance works" has partly been
replaced by "does any independent path to a tweet still exist".

Run: python3 egress_probe.py                 (the source survey - the default)
     python3 egress_probe.py direct proxied   (named egress arms)
     python3 egress_probe.py sources direct   (both)
"""
import asyncio, json, os, re, sys, time
from urllib.parse import urlparse
from urllib.request import Request

from camoufox.async_api import AsyncCamoufox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scraper import parse_proxy_url, CAMOUFOX_BIN
from scrapers import nitter_instances as ni
from scrapers import twitter_feeds as tf

BASE = os.environ.get("PROBE_BASE", "https://nitter.freedit.eu")
HANDLE = os.environ.get("PROBE_HANDLE", "josemorgado")
BUDGET = int(os.environ.get("PROBE_BUDGET", "150"))


async def egress_ips(page, n: int = 3) -> list[str]:
    """The exit address, sampled over separate requests. Two different answers
    here IS the finding: it means the challenge cannot see a stable client."""
    seen = []
    for _ in range(n):
        try:
            r = await page.request.get("https://api.ipify.org", timeout=20000)
            seen.append((await r.text()).strip())
        except Exception as e:
            seen.append(f"({type(e).__name__})")
    return seen


async def arm(label: str, proxy_url: str | None, geoip: bool = False,
              humanize: bool = False) -> None:
    cfg = parse_proxy_url(proxy_url) if proxy_url else None
    kwargs = {"headless": True, "humanize": humanize, "enable_cache": True,
              "timeout": 60000, "executable_path": str(CAMOUFOX_BIN)}
    if cfg:
        kwargs["proxy"] = cfg
    # camoufox warns on every proxied launch that geoip=True is "heavily
    # recommended", and the scraper has never passed it. Without it the spoofed
    # locale, timezone and geolocation describe a client somewhere other than
    # where the exit IP is, which is exactly the incoherence a managed challenge
    # is looking for.
    if geoip:
        kwargs["geoip"] = True
    print(f"\n=== {label} ===", flush=True)
    async with AsyncCamoufox(**kwargs) as browser:
        page = await browser.new_page()
        ips = await egress_ips(page)
        stable = len(set(ips)) == 1
        print(f"  exit IPs: {ips}  -> {'STABLE' if stable else 'ROTATING'}", flush=True)
        started = time.monotonic()
        try:
            tweets = await tf._load_timeline(page, BASE, HANDLE, BUDGET)
        except Exception as e:
            print(f"  -> {type(e).__name__}: {str(e)[:100]}", flush=True)
            return
        secs = time.monotonic() - started
        print(f"  -> {'TIMELINE' if tweets else 'NO TIMELINE'} after {secs:.0f}s "
              f"({len(tweets or [])} tweets)", flush=True)




# ---------------------------------------------------------------------------
# Source survey: what is LEFT to scrape, measured from the runner
# ---------------------------------------------------------------------------
# Added 2026-09-03, because the answer changed underneath the project. X Corp
# began sending cease-and-desist letters to public Nitter operators in late
# August 2026 - xcancel.com's own page is dated Monday 24 August, one day before
# this repo's first red run - and four of the corpus's best-known hosts now
# serve a notice instead of tweets. "Widen the instance list" is therefore not
# obviously a strategy any more, and the question worth measuring is whether an
# independent source exists at all.
#
# Every arm below prints RAW evidence - status, byte count, an excerpt - because
# the interesting outcomes are the ambiguous ones. In particular a 429 from a
# datacenter IP and a 429 through a residential exit mean completely different
# things, and only the runner can tell them apart: measured from the dev
# container on 2026-09-03, syndication.twitter.com returned "Rate limit
# exceeded" on four consecutive attempts, which says nothing at all about
# whether it works through the proxy the scrape actually uses.

SURVEY_HANDLE = os.environ.get("PROBE_HANDLE", "josemorgado")

# Every host worth a verdict, including the ones expected to be gone: a survey
# that only lists survivors cannot show that the corpus is collapsing.
SURVEY_HOSTS = [
    "https://nitter.freedit.eu",
    "https://lightbrd.com",
    "https://nitter.kareem.one",
    "https://nuku.trabun.org",
    "https://nt.vern.cc",
    "https://bird.habedieeh.re",
    "https://xcancel.com",
    "https://nitter.net",
    "https://nitter.catsarch.com",
    "https://nitter.tiekoetter.com",
    "https://nitter.privacyredirect.com",
    "https://twiiit.com",
]

# Candidate registries, including two the project does not use yet. d420 is in
# the live list but answered {"hosts": []} on 2026-09-03 - healthy monitor,
# zero healthy hosts - so the corpus is effectively one frozen 2024 snapshot
# plus a hand-maintained wiki table.
SURVEY_REGISTRIES = [
    "https://raw.githubusercontent.com/qallen028/nitter-instances/master/history/summary.json",
    "https://raw.githubusercontent.com/wiki/zedeus/nitter/Instances.md",
    "https://status.d420.de/api/v1/instances",
    "https://raw.githubusercontent.com/libredirect/instances/main/data.json",
]

# X's own embed infrastructure. No auth, no login, not a third-party frontend -
# so a cease-and-desist letter to instance operators does not touch it. If this
# answers through the proxy it is the independent fallback the scrape lacks.
SYNDICATION_TIMELINE = ("https://syndication.twitter.com/srv/timeline-profile/"
                        "screen-name/{handle}")


def _fetch(url: str, proxy_url: str | None, timeout: int = 25):
    """(status, body) with the body PRESERVED on an HTTP error.

    Discarding an error body is how a Cloudflare interstitial becomes
    indistinguishable from a dead host - the same mistake nitter_instances.
    classify() documents at length.
    """
    headers = {"User-Agent": ni.USER_AGENT,
               "Accept": "text/html,application/xhtml+xml,*/*",
               "Accept-Language": "en-US,en;q=0.9"}
    try:
        with ni._opener(proxy_url).open(Request(url, headers=headers),
                                        timeout=timeout) as r:
            return r.status, r.read(400_000).decode("utf-8", "replace")
    except Exception as e:
        code = getattr(e, "code", None)
        if code is None:
            return 0, f"{type(e).__name__}: {str(e)[:120]}"
        try:
            return code, e.read(400_000).decode("utf-8", "replace")
        except Exception:
            return code, ""


def _survey_registries(proxy_url: str | None) -> None:
    print("\n=== REGISTRIES (what the candidate corpus is actually made of) ===",
          flush=True)
    for url in SURVEY_REGISTRIES:
        entries = ni.fetch_registry(url, proxy_url)
        host = urlparse(url).netloc
        tail = url.rsplit("/", 1)[-1][:28]
        print(f"  {host:<28} {tail:<30} candidates={len(entries)}", flush=True)


def _survey_instances(proxy_url: str | None) -> None:
    print("\n=== INSTANCES (plain HTTP through the scrape's own egress) ===",
          flush=True)
    for base in SURVEY_HOSTS:
        rec = ni.classify(base, None, proxy_url, timeout=15)
        print(f"  {ni.TIER_NAMES[rec['tier']]:<13} {base:<36} "
              f"http={rec['http']:<4} {rec['bytes']:>7}B {rec['elapsed_ms']:>6}ms  "
              f"{rec['note'][:96]}", flush=True)


def _survey_syndication(proxy_url: str | None) -> None:
    print("\n=== X SYNDICATION (the only non-Nitter path left) ===", flush=True)
    url = SYNDICATION_TIMELINE.format(handle=SURVEY_HANDLE)
    for attempt in (1, 2, 3):
        code, body = _fetch(url, proxy_url)
        has_next = "__NEXT_DATA__" in body
        entries = -1
        if has_next:
            m = re.search(r'<script id="__NEXT_DATA__" type="application/json">'
                          r'(.*?)</script>', body, re.S)
            if m:
                try:
                    blob = json.loads(m.group(1))
                    entries = len(blob.get("props", {}).get("pageProps", {})
                                  .get("timeline", {}).get("entries", []))
                except Exception as e:
                    entries = -2
                    print(f"    __NEXT_DATA__ present but unparsable: "
                          f"{type(e).__name__}", flush=True)
        verdict = ("TIMELINE" if entries > 0 else
                   "EMPTY TIMELINE" if has_next else
                   "RATE LIMITED" if code == 429 else "NO")
        print(f"  attempt {attempt}: http={code} bytes={len(body)} "
              f"next_data={has_next} entries={entries} -> {verdict}", flush=True)
        print(f"    body head: {body[:150]!r}", flush=True)
        if entries > 0:
            print(f"  -> USABLE: {entries} tweets for @{SURVEY_HANDLE} with no "
                  f"instance, no challenge and no auth", flush=True)
            return
        time.sleep(5)
    print("  -> unusable from this egress", flush=True)


async def survey() -> None:
    proxy_url = os.environ.get("SCRAPER_HTTP_PROXY")
    print(f"survey: proxy={'yes' if proxy_url else 'NO - direct'} "
          f"handle=@{SURVEY_HANDLE}", flush=True)
    _survey_registries(proxy_url)
    _survey_instances(proxy_url)
    _survey_syndication(proxy_url)


# Each arm changes exactly one thing from the one above it, so whichever one
# first says TIMELINE names the missing ingredient rather than a lucky
# combination.
ARMS = {
    "direct":            ("DIRECT, as the scraper launches today", False, False, False),
    "direct-geoip":      ("DIRECT + geoip", False, True, False),
    "proxied":           ("PROXIED, as the scraper launches today", True, False, False),
    "proxied-geoip":     ("PROXIED + geoip", True, True, False),
    "proxied-geoip-hum": ("PROXIED + geoip + humanize", True, True, True),
}


async def main():
    which = sys.argv[1:] or ["sources"]
    if "sources" in which:
        await survey()
        which = [w for w in which if w != "sources"]
    for name in which:
        label, proxied, geoip, humanize = ARMS[name]
        proxy = os.environ.get("SCRAPER_HTTP_PROXY") if proxied else None
        if proxied and not proxy:
            print(f"\n=== {label} === skipped, no SCRAPER_HTTP_PROXY", flush=True)
            continue
        await arm(label, proxy, geoip=geoip, humanize=humanize)

asyncio.run(main())
