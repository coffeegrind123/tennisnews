"""Tennis Canada - https://www.tenniscanada.com/news"""

URL = "https://www.tenniscanada.com/news"


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    return await page.evaluate("""() => {
        const articles = [];
        const seen = new Set();
        document.querySelectorAll('article').forEach(el => {
            const h2 = el.querySelector('h2');
            const a = el.querySelector('a');
            if (!h2 || !a) return;
            const href = a.getAttribute('href') || '';
            if (!href || seen.has(href)) return;
            seen.add(href);
            const title = h2.textContent.trim();
            if (!title || title.length < 10) return;
            articles.push({title, link: href, description: ''});
        });
        return articles.slice(0, 25);
    }""")
