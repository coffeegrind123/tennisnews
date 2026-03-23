"""USTA Florida - https://www.ustaflorida.com/news/
Date in p.post-date on listing. Desc from article meta."""

URL = "https://www.ustaflorida.com/news/"


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    return await page.evaluate("""() => {
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
            articles.push({title, link: href, description: '', date: date});
        });
        return articles.slice(0, 25);
    }""")
