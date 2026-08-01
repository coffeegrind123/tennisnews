"""US Open - https://www.usopen.org/en_US/news/index.html

The news tiles are anchorless `div.chip.news-chip` elements wired up with JS click
handlers, so there is no article URL anywhere in the rendered DOM. The previous
implementation screen-scraped `document.body.innerText` and set every article's
link to the index page itself, which made all 10 "articles" point at the same URL.

The page's own SPA reads a JSON feed instead, which carries the real permalink,
description and an epoch-ms publish date. That is what this reads.
"""

from datetime import datetime, timedelta, timezone

URL = "https://www.usopen.org/en_US/news/index.html"
BASE = "https://www.usopen.org"
FEED = (BASE + "/relatedcontent/rest/v2/uso_v1/en/content/byType/news"
        "?zone=3&subType=articles&subType=match%20preview"
        "&startDate={start}&endDate={end}&count=100")

# photolist entries are image galleries with no article text; excluded by the
# subType filter above, but re-checked here in case the feed ignores it.
SKIP_SUBTYPES = {"photolist", "video"}
LOOKBACK_DAYS = 60


async def scrape(page) -> list[dict]:
    now = datetime.now(timezone.utc)
    feed_url = FEED.format(
        start=(now - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d"),
        end=(now + timedelta(days=1)).strftime("%Y-%m-%d"),
    )

    # Load the site first so the feed request carries the same origin/session the
    # SPA would have; the endpoint 302s for requests it does not like.
    await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(1500)

    resp = await page.request.get(feed_url, timeout=30000)
    if not resp.ok:
        raise RuntimeError(f"US Open feed returned HTTP {resp.status} for {feed_url}")
    payload = await resp.json()

    items = payload.get("content") or []
    if not items:
        raise RuntimeError(
            f"US Open feed returned no content (totalRows={payload.get('totalRows')}, "
            f"keys={list(payload)}) for {feed_url}"
        )

    articles = []
    for item in items:
        if item.get("subType") in SKIP_SUBTYPES:
            continue
        title = (item.get("title") or item.get("shortTitle") or "").strip()
        url = item.get("url") or item.get("shareUrl") or ""
        if not title or not url:
            continue

        date = ""
        ms = item.get("displayDate") or item.get("sortDate")
        if isinstance(ms, (int, float)) and ms > 0:
            date = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()

        credit = (item.get("metadata") or {}).get("credit", "")
        desc = (item.get("description") or "").strip()
        if credit and desc:
            desc = f"{desc} (By {credit})"

        articles.append({
            "title": title,
            "link": url if url.startswith("http") else BASE + url,
            "description": desc[:500],
            "date": date,
        })

    return articles[:25]
