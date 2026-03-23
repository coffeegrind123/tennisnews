"""Tennishead - https://tennishead.net/tennis/news/"""

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
            articles.push({
                title,
                link: href,
                description: p ? p.textContent.trim().substring(0, 300) : ''
            });
        });
        return articles.slice(0, 25);
    }""")
