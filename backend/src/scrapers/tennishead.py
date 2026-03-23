"""Tennishead - https://tennishead.net/tennis/news/
Desc in article p, date in article time[datetime].
Featured article has no p tag - visit article page for og:description."""

from scrapers.utils import log_progress, log_done

URL = "https://tennishead.net/tennis/news/"


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    items = await page.evaluate("""() => {
        const articles = [];
        const seen = new Set();
        document.querySelectorAll('article').forEach(el => {
            const a = el.querySelector('h2 a, h3 a');
            if (!a) return;
            const href = a.getAttribute('href') || '';
            if (!href || seen.has(href)) return;
            seen.add(href);
            const title = a.textContent.trim();
            if (!title || title.length < 10) return;
            const p = el.querySelector('p');
            const desc = p ? p.textContent.trim().substring(0, 500) : '';
            const timeEl = el.querySelector('time');
            const date = timeEl ? (timeEl.getAttribute('datetime') || timeEl.textContent.trim()) : '';
            articles.push({title, link: href, description: desc, date: date});
        });
        return articles.slice(0, 25);
    }""")

    articles = []
    needs_visit = [i for i, a in enumerate(items) if not a.get("description")]
    for idx, item in enumerate(items):
        if idx in needs_visit:
            log_progress(idx + 1, len(items))
            try:
                await page.goto(item["link"], wait_until="domcontentloaded", timeout=12000)
                await page.wait_for_timeout(1500)
                desc = await page.evaluate("""() => {
                    var m = document.querySelector('meta[property="og:description"], meta[name="description"]');
                    return m ? (m.getAttribute('content') || '').substring(0, 500) : '';
                }""")
                item["description"] = desc
            except Exception:
                pass
        articles.append(item)

    if needs_visit:
        log_done()
    return articles
