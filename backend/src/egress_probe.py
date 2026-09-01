"""Which egress can actually clear a Nitter instance's Cloudflare challenge?

Answers one question that cannot be measured off a GitHub runner: proxied or
direct. The residential proxy rotates its exit IP PER CONNECTION (documented
upstream, and measured 2026-09-01: four consecutive requests exited in Korea,
the US, France and Indonesia). A Cloudflare managed challenge issues clearance
to a consistent client, so a rotating exit may be structurally incapable of
clearing one no matter how long it is given - while a runner's own address is
stable but has a datacenter reputation. This prints which of the two works.

Run: python3 egress_probe.py            (both arms)
     python3 egress_probe.py direct     (one arm)
"""
import asyncio, os, sys, time
from camoufox.async_api import AsyncCamoufox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scraper import parse_proxy_url, CAMOUFOX_BIN
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
    which = sys.argv[1:] or list(ARMS)
    for name in which:
        label, proxied, geoip, humanize = ARMS[name]
        proxy = os.environ.get("SCRAPER_HTTP_PROXY") if proxied else None
        if proxied and not proxy:
            print(f"\n=== {label} === skipped, no SCRAPER_HTTP_PROXY", flush=True)
            continue
        await arm(label, proxy, geoip=geoip, humanize=humanize)

asyncio.run(main())
