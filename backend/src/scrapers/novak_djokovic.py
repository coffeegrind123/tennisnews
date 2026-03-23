"""Novak Djokovic - https://novakdjokovic.com/en/n/news/
Desc in .grid-excerpt, date in .grid-meta. Title in h5.grid-title a or h4 a."""

URL = "https://novakdjokovic.com/en/n/news/"


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    return await page.evaluate("""() => {
        const articles = [];
        const seen = new Set();
        document.querySelectorAll('.grid-item-news, [class*="grid-item"]').forEach(el => {
            const a = el.querySelector('h4 a, h5 a, [class*="title"] a');
            if (!a) return;
            const href = a.getAttribute('href') || '';
            if (!href || seen.has(href)) return;
            seen.add(href);
            const title = a.textContent.trim();
            if (!title || title.length < 10) return;
            const excerptEl = el.querySelector('[class*="excerpt"]');
            const desc = excerptEl ? excerptEl.textContent.trim().substring(0, 500) : '';
            const metaEl = el.querySelector('[class*="meta"]');
            const date = metaEl ? metaEl.textContent.trim() : '';
            articles.push({title, link: href, description: desc, date: date});
        });
        if (articles.length === 0) {
            document.querySelectorAll('h4 a').forEach(a => {
                const href = a.getAttribute('href') || '';
                if (!href || seen.has(href)) return;
                seen.add(href);
                const title = a.textContent.trim();
                if (!title || title.length < 10) return;
                articles.push({title, link: href, description: '', date: ''});
            });
        }
        return articles.slice(0, 25);
    }""")
