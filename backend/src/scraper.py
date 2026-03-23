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
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import feedparser

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


def strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:500]


def parse_date(entry) -> str:
    for field in ("published_parsed", "updated_parsed"):
        t = getattr(entry, field, None) or entry.get(field)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc).isoformat()
            except Exception:
                pass
    for field in ("published", "updated"):
        v = getattr(entry, field, None) or entry.get(field)
        if v:
            return v
    return ""


async def fetch_rss(site: dict) -> list[dict]:
    feed_url = site["feed_url"]
    name = site["name"]
    try:
        feed = await asyncio.to_thread(feedparser.parse, feed_url)
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
        print(f"  [RSS] {name}: {len(articles)} articles")
        return articles
    except Exception as e:
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
                "source_name": name,
                "source_url": site["url"],
                "date": item.get("date", ""),
            })
        print(f"  [SCRAPE] {name}: {len(articles)} articles")
        return articles
    except Exception as e:
        print(f"  [SCRAPE] {name}: ERROR - {e}")
        return []


async def scrape_all_sites(scrape_sites: list[dict]) -> list[dict]:
    if not scrape_sites:
        return []

    camoufox_path = str(CAMOUFOX_BIN) if CAMOUFOX_BIN.exists() else None
    if not camoufox_path:
        print("[WARN] camoufox binary not found, skipping scrape sites")
        return []

    try:
        from camoufox.async_api import AsyncCamoufox
    except ImportError:
        print("[WARN] camoufox not installed, skipping scrape sites")
        return []

    proxy_config = parse_proxy_url(DEFAULT_HTTP_PROXY) if DEFAULT_HTTP_PROXY else None
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
    try:
        async with AsyncCamoufox(**kwargs) as browser:
            page = await browser.new_page()
            for site in scrape_sites:
                try:
                    articles = await scrape_site_with_module(page, site)
                    all_articles.extend(articles)
                except Exception as e:
                    print(f"  [SCRAPE] {site['name']}: FAILED - {e}")

            # Scrape Twitter feeds
            print("  Fetching Twitter feeds...")
            try:
                from scrapers.twitter_feeds import scrape as scrape_twitter
                twitter_tweets = await scrape_twitter(page)
                print(f"  [TWITTER] Total: {len(twitter_tweets)} tweets")
            except Exception as e:
                print(f"  [TWITTER] ERROR - {e}")

            await page.close()
    except Exception as e:
        print(f"[ERROR] camoufox session failed: {e}")

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

    seen = set()
    unique = []
    for a in all_articles:
        key = re.sub(r"\W+", "", a["title"].lower())[:60]
        if key not in seen:
            seen.add(key)
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

    generate_html(unique, tweets, PUBLIC_DIR / "index.html")

    print(f"\nDone: {len(unique)} unique articles + {len(tweets)} tweets saved")
    print(f"  JSON: {articles_path}")
    print(f"  Tweets: {tweets_path}")
    print(f"  HTML: {PUBLIC_DIR / 'index.html'}")


if __name__ == "__main__":
    asyncio.run(run())
