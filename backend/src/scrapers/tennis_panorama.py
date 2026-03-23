"""Tennis Panorama - https://www.tennispanorama.com/ (WordPress/GenerateBlocks)
Listing: desc in .gb-block-post-grid-excerpt, date in .gb-block-post-grid-date.
Article: meta[name=description], article:published_time."""

URL = "https://www.tennispanorama.com/"


from scrapers.utils import log_progress, log_done


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    links = await page.evaluate("""() => {
        const articles = [];
        const seen = new Set();
        document.querySelectorAll('h3 a').forEach(a => {
            const href = a.getAttribute('href') || '';
            if (!href || seen.has(href) || href === '#') return;
            seen.add(href);
            const title = a.textContent.trim();
            if (!title || title.length < 10) return;
            const container = a.closest('[class*="gb-block-post"], article, div');
            const descEl = container ? container.querySelector('[class*="excerpt"]') : null;
            const desc = descEl ? descEl.textContent.trim().substring(0, 500) : '';
            const dateEl = container ? container.querySelector('[class*="date"]') : null;
            const date = dateEl ? dateEl.textContent.trim() : '';
            articles.push({title, link: href, description: desc, date: date});
        });
        return articles.slice(0, 15);
    }""")

    articles = []
    for idx, item in enumerate(links, 1):
        log_progress(idx, len(links))
        if item.get("description") and item.get("date"):
            articles.append(item)
            continue
        try:
            await page.goto(item["link"], wait_until="domcontentloaded", timeout=12000)
            await page.wait_for_timeout(1500)
            meta = await page.evaluate("""() => {
                var desc = '';
                var date = '';
                var m = document.querySelector('meta[name="description"], meta[property="og:description"]');
                if (m) desc = m.getAttribute('content') || '';
                var d = document.querySelector('meta[property="article:published_time"]');
                if (d) date = d.getAttribute('content') || '';
                return {desc: desc.substring(0, 500), date: date};
            }""")
            articles.append({
                **item,
                "description": item["description"] or meta["desc"],
                "date": item["date"] or meta["date"],
            })
        except Exception:
            articles.append(item)
    log_done()
    return articles
