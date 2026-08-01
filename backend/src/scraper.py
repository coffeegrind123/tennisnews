#!/usr/bin/env python3
"""
Tennis News Scraper
Fetches articles from ~37 tennis news sites via RSS feeds and camoufox browser scraping.
Each scrape site has a dedicated module in scrapers/ with tailored extraction logic.
"""

import asyncio
import importlib
import json
import os
import re
import sys
import html as html_lib
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(line_buffering=True)
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import feedparser

HELSINKI_TZ = ZoneInfo("Europe/Helsinki")

SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent
PROJECT_DIR = BACKEND_DIR.parent

DATA_DIR = PROJECT_DIR / "data"
PUBLIC_DIR = PROJECT_DIR / "public"

IN_CONTAINER = Path("/opt/camoufox/camoufox-bin").exists()
CAMOUFOX_BIN = (
    Path("/opt/camoufox/camoufox-bin")
    if IN_CONTAINER
    else BACKEND_DIR / "camoufox_build" / "camoufox-bin"
)

DEFAULT_HTTP_PROXY = os.environ.get("SCRAPER_HTTP_PROXY")

# Per-run source health. Written to data/health.json and used to decide the exit
# code, so a run that quietly collects nothing fails the job instead of going green.
HEALTH: dict = {
    "browser_ok": False,
    "browser_error": "",
    "sources": {},
    "twitter": {"tweets": 0, "accounts": 0, "error": "not run"},
}


def parse_proxy_url(proxy_url: str) -> dict | None:
    try:
        parsed = urlparse(proxy_url)
        if not parsed.hostname or not parsed.port:
            return None
        config = {"server": f"http://{parsed.hostname}:{parsed.port}"}
        if parsed.username:
            config["username"] = parsed.username
        if parsed.password:
            config["password"] = parsed.password
        return config
    except Exception:
        return None


PROXY_PROBE_URL = "https://example.com"


def proxy_reachable(config: dict, timeout: float = 15.0) -> bool:
    """Fetch a URL *through* the proxy before handing it to the browser.

    A dead proxy is indistinguishable from a dead internet from inside the
    browser: every goto fails instantly with NS_ERROR_PROXY_CONNECTION_REFUSED,
    which reads as "all 21 sites are broken" rather than "one credential
    expired".

    This deliberately issues a real HTTPS request, which makes the proxy perform
    a CONNECT with our credentials. A plain TCP connect to host:port is NOT
    sufficient and gave a false pass in CI: the socket opened, the preflight
    said "reachable", and every subsequent browser navigation was still refused
    because the proxy accepts connections but rejects the tunnel.
    """
    from urllib.request import ProxyHandler, build_opener

    server = config.get("server", "")
    parsed = urlparse(server)
    if not parsed.hostname or not parsed.port:
        HEALTH["proxy_error"] = f"unparseable proxy server: {server!r}"
        return False

    auth = ""
    if config.get("username"):
        auth = f"{config['username']}:{config.get('password', '')}@"
    proxy_url = f"http://{auth}{parsed.hostname}:{parsed.port}"

    opener = build_opener(ProxyHandler({"http": proxy_url, "https": proxy_url}))
    try:
        with opener.open(PROXY_PROBE_URL, timeout=timeout) as r:
            if r.status >= 400:
                HEALTH["proxy_error"] = f"proxy returned HTTP {r.status} for {PROXY_PROBE_URL}"
                return False
            return True
    except Exception as e:
        HEALTH["proxy_error"] = f"{type(e).__name__}: {str(e)[:160]}"
        return False


def strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:500]


def to_helsinki(dt_str: str) -> str:
    """Best-effort convert a date string to Europe/Helsinki format."""
    if not dt_str:
        return ""
    s = dt_str.strip()

    # Relative dates: "3 days ago", "2 hours ago", "Yesterday", "Today"
    now_local = datetime.now(HELSINKI_TZ)
    rel = re.match(r"(\d+)\s+(minute|hour|day|week|month)s?\s+ago", s, re.IGNORECASE)
    if rel:
        n = int(rel.group(1))
        unit = rel.group(2).lower()
        delta = {
            "minute": timedelta(minutes=n),
            "hour": timedelta(hours=n),
            "day": timedelta(days=n),
            "week": timedelta(weeks=n),
            "month": timedelta(days=30 * n),
        }[unit]
        return (now_local - delta).strftime("%Y-%m-%d %H:%M %Z")
    if re.match(r"^yesterday\b", s, re.IGNORECASE):
        return (now_local - timedelta(days=1)).strftime("%Y-%m-%d %H:%M %Z")
    if re.match(r"^(today|just now)\b", s, re.IGNORECASE):
        return now_local.strftime("%Y-%m-%d %H:%M %Z")
    # Nitter's short form on recent tweets: "2h", "45m", "3d"
    short = re.match(r"^(\d+)([mhd])$", s)
    if short:
        n = int(short.group(1))
        delta = {"m": timedelta(minutes=n), "h": timedelta(hours=n), "d": timedelta(days=n)}[short.group(2)]
        return (now_local - delta).strftime("%Y-%m-%d %H:%M %Z")

    # Twitter/xcancel: "Mar 23, 2026 · 8:15 AM UTC" -> "Mar 23, 2026 8:15 AM UTC"
    s = re.sub(r"\s*·\s*", " ", s)

    # Clean up common noise
    s = re.sub(r"^\w+day,\s*", "", s)  # "Wednesday, March 4" -> "March 4"
    s = re.sub(r"\s*(GMT|BST|UTC|EST|PST|CET|CEST)\s*$", "", s)  # strip tz abbrevs
    s = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", s)  # "March 5th" -> "March 5"
    s = re.sub(r"\.\s*$", "", s)  # trailing period (Djokovic dates: "12. 03. 2026.")
    s = re.sub(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", r"\1/\2/\3", s)  # "12. 03. 2026" -> "12/03/2026"
    # Swiss Indoors: "20Oct 2025" -> "20 Oct 2025"
    s = re.sub(r"(\d{1,2})([A-Z][a-z]{2})\s+(\d{4})", r"\1 \2 \3", s)
    # Wimbledon: "MON 02 MAR 202610:30" -> "02 Mar 2026 10:30"
    s = re.sub(r"^[A-Z]{3}\s+", "", s)
    m = re.match(r"(\d{1,2})\s+([A-Z]{3})\s+(\d{4})(\d{2}:\d{2})", s)
    if m:
        s = f"{m.group(1)} {m.group(2)} {m.group(3)} {m.group(4)}"
    # US short dates: "5/19/25" -> "05/19/2025"
    m2 = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2})$", s)
    if m2:
        y = int(m2.group(3))
        y = y + 2000 if y < 50 else y + 1900
        s = f"{m2.group(1)}/{m2.group(2)}/{y}"

    # Try RFC 2822 first
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(dt_str)
        return dt.astimezone(HELSINKI_TZ).strftime("%Y-%m-%d %H:%M %Z")
    except Exception:
        pass

    formats = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d %b %Y %H:%M",
        "%d %b %Y",
        "%b %d %Y",
        "%b %d, %Y %I:%M %p",
        "%b %d, %Y",
        "%B %d %Y",
        "%B %d, %Y",
        "%B %d",
        "%d %B %Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%b %d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(s.strip(), fmt)
            if dt.year == 1900:
                dt = dt.replace(year=datetime.now().year)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(HELSINKI_TZ).strftime("%Y-%m-%d %H:%M %Z")
        except Exception:
            continue
    return dt_str


def parse_date(entry) -> str:
    for field in ("published_parsed", "updated_parsed"):
        t = getattr(entry, field, None) or entry.get(field)
        if t:
            try:
                dt = datetime(*t[:6], tzinfo=timezone.utc)
                return dt.astimezone(HELSINKI_TZ).strftime("%Y-%m-%d %H:%M %Z")
            except Exception:
                pass
    for field in ("published", "updated"):
        v = getattr(entry, field, None) or entry.get(field)
        if v:
            return to_helsinki(v)
    return ""


# There is no single user agent these hosts agree on, so rotate rather than
# pick. Measured, not assumed: most feeds behind a WAF reject feedparser's
# self-identifying default ("feedparser/6.0.14 +https://github.com/..."), but
# World Tennis Magazine and 10sBalls do the exact opposite - they serve the
# feedparser agent and answer a Chrome UA with 403. Trying a browser agent
# alone made those two worse, not better.
RSS_USER_AGENTS = [
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    feedparser.USER_AGENT,
    "Mozilla/5.0 (compatible; TennisNewsBot/1.0; +https://github.com/coffeegrind123/tennisnews)",
]


async def fetch_rss(site: dict) -> list[dict]:
    feed_url = site["feed_url"]
    name = site["name"]
    try:
        feed = None
        tried = []
        for agent in RSS_USER_AGENTS:
            feed = await asyncio.to_thread(feedparser.parse, feed_url, agent=agent)
            if feed.entries:
                break
            tried.append(f"{agent.split('/')[0]}:{getattr(feed, 'status', None)}")
            await asyncio.sleep(1)

        if not feed.entries:
            status = getattr(feed, "status", None)
            bozo = getattr(feed, "bozo_exception", None)
            HEALTH["sources"][name] = {
                "type": "rss", "count": 0,
                "error": f"no entries from any user agent ({', '.join(tried)}); "
                         f"last http={status}, bozo={str(bozo)[:80]}",
            }
            print(f"  [RSS] {name}: 0 articles (tried {', '.join(tried)})")
            return []

        articles = []
        for entry in feed.entries[:20]:
            title = strip_html(entry.get("title", ""))
            if not title:
                continue
            link = entry.get("link", "")
            desc = strip_html(
                entry.get("summary", "") or entry.get("description", "")
            )
            articles.append({
                "title": title,
                "description": desc,
                "link": link,
                "source_name": name,
                "source_url": site["url"],
                "date": parse_date(entry),
            })
        HEALTH["sources"][name] = {"type": "rss", "count": len(articles), "error": ""}
        print(f"  [RSS] {name}: {len(articles)} articles")
        return articles
    except Exception as e:
        HEALTH["sources"][name] = {"type": "rss", "count": 0, "error": str(e)[:200]}
        print(f"  [RSS] {name}: ERROR - {e}")
        return []


async def scrape_site_with_module(page, site: dict) -> list[dict]:
    name = site["name"]
    module_name = site["module"]
    try:
        mod = importlib.import_module(f"scrapers.{module_name}")
        raw = await mod.scrape(page)
        articles = []
        for item in raw:
            title = item.get("title", "").strip()
            if not title or len(title) < 5:
                continue
            articles.append({
                "title": title[:200],
                "description": item.get("description", "")[:500],
                "link": item.get("link", ""),
                "source_name": item.get("source_name") or name,
                "source_url": site["url"],
                "date": to_helsinki(item.get("date", "")),
            })
        HEALTH["sources"][name] = {"type": "scrape", "count": len(articles), "error": ""}
        print(f"{len(articles)} articles")
        return articles
    except Exception as e:
        HEALTH["sources"][name] = {"type": "scrape", "count": 0, "error": str(e)[:200]}
        print(f"ERROR - {e}")
        return []


async def scrape_all_sites(scrape_sites: list[dict]) -> list[dict]:
    if not scrape_sites:
        return [], []

    camoufox_path = str(CAMOUFOX_BIN) if CAMOUFOX_BIN.exists() else None
    if not camoufox_path:
        HEALTH["browser_error"] = f"camoufox binary not found at {CAMOUFOX_BIN}"
        print(f"[FATAL] {HEALTH['browser_error']}")
        return [], []

    try:
        from camoufox.async_api import AsyncCamoufox
    except ImportError as e:
        HEALTH["browser_error"] = f"camoufox not importable: {e}"
        print(f"[FATAL] {HEALTH['browser_error']}")
        return [], []

    proxy_config = parse_proxy_url(DEFAULT_HTTP_PROXY) if DEFAULT_HTTP_PROXY else None
    if proxy_config:
        if proxy_reachable(proxy_config):
            HEALTH["proxy"] = "configured and reachable"
            print(f"  [PROXY] {proxy_config['server']} reachable")
        else:
            # Going direct beats scraping nothing at all. Say so loudly: the run
            # is now using the runner's own IP, which some sites treat worse.
            HEALTH["proxy"] = "configured but UNREACHABLE - fell back to direct"
            print(f"  [PROXY] WARNING: {proxy_config['server']} unreachable "
                  f"({HEALTH.get('proxy_error')}) - falling back to a direct connection")
            proxy_config = None
    else:
        HEALTH["proxy"] = "not configured"

    kwargs = {
        "headless": True,
        "humanize": False,
        "enable_cache": True,
        "timeout": 60000,
        "executable_path": camoufox_path,
    }
    if proxy_config:
        kwargs["proxy"] = proxy_config

    all_articles = []
    twitter_tweets = []
    total = len(scrape_sites)
    try:
        async with AsyncCamoufox(**kwargs) as browser:
            HEALTH["browser_ok"] = True
            page = await browser.new_page()
            for idx, site in enumerate(scrape_sites, 1):
                print(f"  [{idx}/{total}] {site['name']}...", end=" ")
                try:
                    articles = await scrape_site_with_module(page, site)
                    all_articles.extend(articles)
                except Exception as e:
                    HEALTH["sources"][site["name"]] = {"count": 0, "error": str(e)[:200]}
                    print(f"FAILED - {e}")

            # Scrape Twitter feeds
            print("  Fetching Twitter feeds...")
            try:
                from scrapers.twitter_feeds import scrape as scrape_twitter
                twitter_tweets = await scrape_twitter(page)
                for tw in twitter_tweets:
                    tw["date"] = to_helsinki(tw.get("date", ""))
                HEALTH["twitter"] = {
                    "tweets": len(twitter_tweets),
                    "accounts": len(set(t.get("handle", "") for t in twitter_tweets)),
                    "error": "",
                }
                print(f"  [TWITTER] Total: {len(twitter_tweets)} tweets")
            except Exception as e:
                HEALTH["twitter"] = {"tweets": 0, "accounts": 0, "error": str(e)[:300]}
                print(f"  [TWITTER] ERROR - {e}")

            await page.close()
    except Exception as e:
        HEALTH["browser_error"] = f"{type(e).__name__}: {e}"
        print(f"[FATAL] camoufox session failed: {HEALTH['browser_error']}")

    return all_articles, twitter_tweets


def generate_html(articles: list[dict], tweets: list[dict], output_path: Path):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sources = sorted(set(a["source_name"] for a in articles))

    rows = []
    for a in articles:
        t = html_lib.escape(a["title"])
        d = html_lib.escape(a["description"])
        l = html_lib.escape(a["link"])
        s = html_lib.escape(a["source_name"])
        dt = html_lib.escape(a.get("date", ""))
        rows.append(
            f'<div class="a">'
            f'<h2><a href="{l}">{t}</a></h2>'
            f'<p class="s">Source: {s}</p>'
            f'{f"<p>{d}</p>" if d else ""}'
            f'{f"<p class=d>{dt}</p>" if dt else ""}'
            f"</div>"
        )

    tweet_rows = []
    for tw in tweets:
        t = html_lib.escape(tw["title"])
        l = html_lib.escape(tw["link"])
        author = html_lib.escape(tw.get("author", ""))
        handle = html_lib.escape(tw.get("handle", ""))
        dt = html_lib.escape(tw.get("date", ""))
        tweet_rows.append(
            f'<div class="tw">'
            f'<p class="tw-author"><b>@{handle}</b> ({author})</p>'
            f'<p>{t}</p>'
            f'<p class="d"><a href="{l}">{dt}</a></p>'
            f"</div>"
        )

    source_links = " | ".join(
        f'<a href="?source={html_lib.escape(s)}">{html_lib.escape(s)}</a>'
        for s in sources
    )

    page = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Tennis News Feed</title>
<style>body{{font-family:sans-serif;max-width:900px;margin:0 auto;padding:1em}}
.a{{border-bottom:1px solid #ccc;padding:0.5em 0}}.s{{color:#666;font-size:0.9em}}
.d{{color:#999;font-size:0.8em}}h2{{font-size:1.1em;margin:0.3em 0}}
p{{margin:0.2em 0}}a{{color:#1a6}}nav{{margin:1em 0;font-size:0.85em}}
form{{margin:1em 0}}input{{padding:0.3em;width:300px}}
.tw{{border-bottom:1px solid #eee;padding:0.4em 0}}.tw-author{{color:#555;font-size:0.9em}}
h1.section{{margin-top:2em;border-top:2px solid #333;padding-top:0.5em}}</style></head>
<body>
<h1>Tennis News Feed</h1>
<p>Updated: {now} | {len(articles)} articles from {len(sources)} sources | <a href="#twitter">{len(tweets)} tweets</a></p>
<form method="get"><input type="text" name="q" placeholder="Search articles...">
<button type="submit">Search</button></form>
<nav>Sources: {source_links}</nav>
{"".join(rows)}
<h1 class="section" id="twitter">Tennis Twitter Feed</h1>
<p>{len(tweets)} tweets from {len(set(tw.get('handle','') for tw in tweets))} accounts</p>
{"".join(tweet_rows)}
</body></html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(page, encoding="utf-8")


async def run():
    from sites import SITES

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    rss_sites = [s for s in SITES if s["type"] == "rss"]
    scrape_sites = [s for s in SITES if s["type"] == "scrape"]

    print(f"Fetching {len(rss_sites)} RSS + {len(scrape_sites)} scrape sites...")

    rss_tasks = [fetch_rss(s) for s in rss_sites]
    rss_results = await asyncio.gather(*rss_tasks)
    rss_articles = [a for batch in rss_results for a in batch]

    scrape_articles, tweets = await scrape_all_sites(scrape_sites)

    all_articles = rss_articles + scrape_articles

    # Dedup on title AND link: the same story often appears twice on one listing
    # (e.g. a "featured" block plus the chronological list) under two different
    # headlines, which a title-only key lets through.
    seen_titles = set()
    seen_links = set()
    unique = []
    for a in all_articles:
        title_key = re.sub(r"\W+", "", a["title"].lower())[:60]
        link_key = a.get("link", "").split("#")[0].rstrip("/")
        if title_key in seen_titles or (link_key and link_key in seen_links):
            continue
        seen_titles.add(title_key)
        if link_key:
            seen_links.add(link_key)
        unique.append(a)

    def sort_key(a):
        d = a.get("date", "")
        return (0, d) if d else (1, "")

    unique.sort(key=sort_key, reverse=True)

    articles_path = DATA_DIR / "articles.json"
    articles_path.write_text(
        json.dumps(unique, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    tweets_path = DATA_DIR / "tweets.json"
    tweets_path.write_text(
        json.dumps(tweets, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Static HTML only includes last 2 days
    now = datetime.now(HELSINKI_TZ)
    cutoff = (now - timedelta(days=2)).strftime("%Y-%m-%d")
    recent = [a for a in unique if a.get("date", "")[:10] >= cutoff]
    recent_tweets = [t for t in tweets if t.get("date", "")[:10] >= cutoff]
    generate_html(recent, recent_tweets, PUBLIC_DIR / "index.html")

    print(f"\nDone: {len(unique)} unique articles ({len(recent)} recent) + {len(tweets)} tweets saved")
    print(f"  JSON: {articles_path}")
    print(f"  Tweets: {tweets_path}")
    print(f"  HTML: {PUBLIC_DIR / 'index.html'}")

    return report_health(scrape_sites, len(scrape_articles))


def report_health(scrape_sites: list[dict], scrape_article_count: int) -> int:
    """Write data/health.json and return the process exit code.

    A run where the browser never started, or where every browser-scraped source
    came back empty, is a FAILURE even though the RSS half still produced JSON.
    Reporting that as success is what let this rot undetected for months.
    """
    HEALTH["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    empty = sorted(n for n, v in HEALTH["sources"].items() if v.get("count", 0) == 0)
    HEALTH["empty_sources"] = empty
    (DATA_DIR / "health.json").write_text(
        json.dumps(HEALTH, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    fatal = []
    if scrape_sites and not HEALTH["browser_ok"]:
        fatal.append(f"browser never started: {HEALTH['browser_error'] or 'unknown'}")
    elif scrape_sites and scrape_article_count == 0:
        fatal.append(f"all {len(scrape_sites)} browser-scraped sources returned 0 articles")
    if HEALTH["twitter"].get("tweets", 0) == 0:
        fatal.append(f"twitter returned 0 tweets: {HEALTH['twitter'].get('error') or 'no error reported'}")

    print("\n--- source health ---")
    print(f"  browser_ok={HEALTH['browser_ok']} twitter_tweets={HEALTH['twitter'].get('tweets', 0)}")
    if empty:
        print(f"  {len(empty)} source(s) returned 0 articles: {', '.join(empty)}")

    if fatal:
        for f in fatal:
            print(f"[FAIL] {f}")
        return 1
    print("  all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
