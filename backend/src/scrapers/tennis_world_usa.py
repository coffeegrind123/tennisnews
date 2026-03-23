"""Tennis World USA - https://www.tennisworldusa.org/
Date via time[datetime] on listing. Desc from article meta."""

URL = "https://www.tennisworldusa.org/"


from scrapers.utils import log_progress, log_done


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    links = await page.evaluate("""() => {
        const articles = [];
        const seen = new Set();
        document.querySelectorAll('article').forEach(el => {
            const a = el.querySelector('a');
            const h3 = el.querySelector('h3');
            if (!a) return;
            const href = a.getAttribute('href') || '';
            if (!href || seen.has(href)) return;
            seen.add(href);
            const title = h3 ? h3.textContent.trim() : a.textContent.trim().substring(0, 200);
            if (!title || title.length < 10) return;
            const timeEl = el.querySelector('time');
            const date = timeEl ? (timeEl.getAttribute('datetime') || timeEl.textContent.trim()) : '';
            articles.push({title, link: href, date: date});
        });
        return articles.slice(0, 25);
    }""")

    articles = []
    for idx, item in enumerate(links, 1):
        log_progress(idx, len(links))
        try:
            await page.goto(item["link"], wait_until="domcontentloaded", timeout=12000)
            await page.wait_for_timeout(1500)
            desc = await page.evaluate("""() => {
                var m = document.querySelector('meta[name="description"], meta[property="og:description"]');
                return m ? (m.getAttribute('content') || '').substring(0, 500) : '';
            }""")
            articles.append({**item, "description": desc})
        except Exception:
            articles.append({**item, "description": ""})
    log_done()
    return articles
