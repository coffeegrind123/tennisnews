"""Rafael Nadal Fans - https://rafaelnadalfans.com/ (WordPress)
Date in time.entry-date[datetime] on listing. Desc from article meta."""

URL = "https://rafaelnadalfans.com/"


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    return await page.evaluate("""() => {
        const articles = [];
        const seen = new Set();
        document.querySelectorAll('.entry-title a, article h2 a').forEach(a => {
            const href = a.getAttribute('href') || '';
            if (!href || seen.has(href)) return;
            seen.add(href);
            const title = a.textContent.trim();
            if (!title || title.length < 10) return;
            const container = a.closest('article, .post, div');
            const timeEl = container ? container.querySelector('time.entry-date, time[datetime]') : null;
            const date = timeEl ? (timeEl.getAttribute('datetime') || timeEl.textContent.trim()) : '';
            articles.push({title, link: href, description: '', date: date});
        });
        return articles.slice(0, 25);
    }""")
