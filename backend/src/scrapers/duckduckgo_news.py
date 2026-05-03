"""DuckDuckGo News - aggregator covering Reuters, NYT, NBC, BBC, Yahoo etc.

Bootstrap: GET https://duckduckgo.com/?q=...&iar=news → page contains vqd token
Fetch:     GET https://duckduckgo.com/news.js?...&vqd=...&df=d → JSON results
df=d restricts to last 24h. Multi-query iteration broadens coverage.
"""
from datetime import datetime, timezone
from urllib.parse import quote_plus

QUERIES = [
    "tennis",
    "ATP tour",
    "WTA tour",
    "tennis injury",
    "Grand Slam tennis",
]

NEWS_JS_TMPL = (
    "/news.js?l=us-en&o=json&noamp=1&q={q}&df=d&vqd={vqd}&p=-1"
)


async def scrape(page) -> list[dict]:
    articles = []
    seen = set()
    for q in QUERIES:
        try:
            await page.goto(
                f"https://duckduckgo.com/?q={quote_plus(q)}&iar=news&ia=news&df=d",
                wait_until="domcontentloaded",
                timeout=20000,
            )
            vqd = await page.evaluate(
                "() => { const m = document.documentElement.outerHTML.match(/vqd=([^\"&\\s]+)/); return m ? m[1] : null; }"
            )
            if not vqd:
                continue
            url = NEWS_JS_TMPL.format(q=quote_plus(q), vqd=vqd)
            data = await page.evaluate(
                "async (u) => { const r = await fetch(u, { headers: { 'X-Requested-With': 'XMLHttpRequest' } }); return await r.json(); }",
                url,
            )
            if not isinstance(data, dict):
                continue
            for r in data.get("results") or []:
                link = r.get("url") or ""
                if not link or link in seen:
                    continue
                seen.add(link)
                ts = r.get("date") or 0
                date_str = ""
                if ts:
                    try:
                        date_str = (
                            datetime.fromtimestamp(int(ts), tz=timezone.utc)
                            .strftime("%a, %d %b %Y %H:%M:%S %z")
                        )
                    except Exception:
                        pass
                src = (r.get("source") or "").strip()
                title = (r.get("title") or "").strip()
                excerpt = (r.get("excerpt") or "").strip()
                articles.append({
                    "title": title,
                    "description": excerpt,
                    "link": link,
                    "date": date_str,
                    "source_name": f"DDG/{src}" if src else "DuckDuckGo News",
                })
        except Exception:
            continue
    return articles
