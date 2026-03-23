"""Rafael Nadal Fans - https://rafaelnadalfans.com/ (WordPress)"""

URL = "https://rafaelnadalfans.com/"


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    return await page.evaluate("""() => {
        const articles = [];
        const seen = new Set();
        document.querySelectorAll('.entry-title a, article h2 a, h2.entry-title a').forEach(a => {
            const href = a.getAttribute('href') || '';
            if (!href || seen.has(href)) return;
            seen.add(href);
            const title = a.textContent.trim();
            if (!title || title.length < 10) return;
            articles.push({title, link: href, description: ''});
        });
        return articles.slice(0, 25);
    }""")
