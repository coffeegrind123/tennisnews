"""DuckDuckGo News - aggregator covering Reuters, NYT, NBC, BBC, Yahoo etc.

The old implementation lifted a `vqd` token off the bootstrap page and called the
internal `/news.js` JSON endpoint. The token is still there, but the endpoint now
answers 403 ("If this error persists, please let us know: ops@duckduckgo.com"),
so every query fell into a bare `except: continue` and the source reported zero
without ever saying why.

The rendered results are still fully present in the DOM, so read those instead.
DuckDuckGo ships build-hashed class names, so nothing here keys off a class:
results are `<article>` elements (excluding the outer wrapper article) that hold
an `h2` plus an outbound link, the source name is the span next to the favicon
served from /ip3/, and the element after the h2 holds "<relative date><excerpt>".
"""
from urllib.parse import quote_plus

QUERIES = [
    "tennis",
    "ATP tour",
    "WTA tour",
    "tennis injury",
    "Grand Slam tennis",
]

EXTRACT_JS = r"""() => {
    const out = [];
    const arts = [...document.querySelectorAll('article')].filter(a =>
        !a.querySelector('article') &&           // skip the page-level wrapper
        a.querySelector('h2') &&
        a.querySelector('a[href^="http"]'));

    for (const a of arts) {
        const h2 = a.querySelector('h2');
        const link = a.querySelector('a[href^="http"]');
        const title = h2.textContent.trim();
        const href = link.getAttribute('href') || '';
        if (!title || title.length < 10 || !href) continue;

        let source = '';
        const fav = a.querySelector('img[src*="/ip3/"]');
        if (fav && fav.nextElementSibling) source = fav.nextElementSibling.textContent.trim();

        let date = '';
        let excerpt = '';
        const body = h2.nextElementSibling;
        if (body) {
            const text = body.textContent.trim();
            // "2 days agoJuly 31 (Reuters) - ..." / "5 hours agoThe ..."
            const m = text.match(/^(\d+\s+(?:second|minute|hour|day|week|month)s?\s+ago|yesterday|today)/i);
            if (m) {
                date = m[1];
                excerpt = text.slice(m[0].length).trim();
            } else {
                excerpt = text;
            }
        }
        out.push({title: title, link: href, source: source, date: date, excerpt: excerpt.slice(0, 500)});
    }
    return out;
}"""


async def scrape(page) -> list[dict]:
    articles = []
    seen = set()
    errors = []

    for q in QUERIES:
        url = f"https://duckduckgo.com/?q={quote_plus(q)}&iar=news&ia=news&df=d"
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_selector("article h2", timeout=20000)
            await page.wait_for_timeout(1500)
            results = await page.evaluate(EXTRACT_JS)
        except Exception as e:
            errors.append(f"{q}: {type(e).__name__}: {str(e)[:90]}")
            continue

        if not results:
            errors.append(f"{q}: page loaded but matched 0 result articles")
        for r in results:
            link = r["link"]
            if link in seen:
                continue
            seen.add(link)
            src = r["source"].strip()
            articles.append({
                "title": r["title"],
                "description": r["excerpt"],
                "link": link,
                "date": r["date"],
                "source_name": f"DDG/{src}" if src else "DuckDuckGo News",
            })

    if not articles:
        raise RuntimeError(
            "DuckDuckGo News returned nothing for any query. "
            + (" | ".join(errors) if errors else "no errors reported - selector drift?")
        )
    if errors:
        print(f"\n      [DDG] {len(errors)}/{len(QUERIES)} queries failed: {'; '.join(errors)}")
    return articles
