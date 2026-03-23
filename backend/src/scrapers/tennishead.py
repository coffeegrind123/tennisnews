"""Tennishead - https://tennishead.net/tennis/news/
Desc in article p, date in article time[datetime]."""

URL = "https://tennishead.net/tennis/news/"


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    return await page.evaluate("""() => {
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
