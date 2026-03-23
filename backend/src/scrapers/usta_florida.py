"""USTA Florida - https://www.ustaflorida.com/news/ (WordPress + Yoast)
Listing: date in .post-date. No desc on listing.
Article: meta[name=description], article:published_time."""

URL = "https://www.ustaflorida.com/news/"


from scrapers.utils import log_progress, log_done


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    links = await page.evaluate("""() => {
        const articles = [];
        const seen = new Set();
        document.querySelectorAll('h2 a, h3 a').forEach(a => {
            const href = a.getAttribute('href') || '';
            if (!href || seen.has(href) || href === '#') return;
            seen.add(href);
            const title = a.textContent.trim();
            if (!title || title.length < 10) return;
            const container = a.closest('article, div, li');
            const dateEl = container ? container.querySelector('.post-date, [class*="date"]') : null;
            const date = dateEl ? dateEl.textContent.trim() : '';
            articles.push({title, link: href, date: date});
        });
        return articles.slice(0, 15);
    }""")

    articles = []
    for idx, item in enumerate(links, 1):
        log_progress(idx, len(links))
        try:
            await page.goto(item["link"], wait_until="domcontentloaded", timeout=12000)
            await page.wait_for_timeout(1500)
            meta = await page.evaluate("""() => {
                var desc = '';
                var date = '';
                var m = document.querySelector('meta[name="description"]');
                if (m) desc = m.getAttribute('content') || '';
                var d = document.querySelector('meta[property="article:published_time"]');
                if (d) date = d.getAttribute('content') || '';
                return {desc: desc.substring(0, 500), date: date};
            }""")
            articles.append({
                **item,
                "description": meta["desc"],
                "date": meta["date"] or item["date"],
            })
        except Exception:
            articles.append({**item, "description": ""})
    log_done()
    return articles
