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


async def arm(label: str, proxy_url: str | None) -> None:
    cfg = parse_proxy_url(proxy_url) if proxy_url else None
    kwargs = {"headless": True, "humanize": False, "enable_cache": True,
              "timeout": 60000, "executable_path": str(CAMOUFOX_BIN)}
    if cfg:
        kwargs["proxy"] = cfg
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


async def main():
    which = sys.argv[1:] or ["direct", "proxied"]
    for name in which:
        if name == "direct":
            await arm("DIRECT (the runner's own address)", None)
        else:
            p = os.environ.get("SCRAPER_HTTP_PROXY")
            if not p:
                print("\n=== PROXIED === skipped, no SCRAPER_HTTP_PROXY", flush=True)
                continue
            await arm("PROXIED (residential, rotates per connection)", p)

asyncio.run(main())
