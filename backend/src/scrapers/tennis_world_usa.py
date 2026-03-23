"""Tennis World USA - https://www.tennisworldusa.org/
Date via time[datetime] on listing. Desc from article meta."""

URL = "https://www.tennisworldusa.org/"


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    return await page.evaluate("""() => {
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
            articles.push({title, link: href, description: '', date: date});
        });
        return articles.slice(0, 25);
    }""")
