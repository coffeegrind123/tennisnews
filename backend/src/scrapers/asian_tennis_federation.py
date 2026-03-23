"""Asian Tennis Federation - https://www.asiantennis.com/news/"""

URL = "https://www.asiantennis.com/news/"
BASE = "https://www.asiantennis.com"


async def scrape(page) -> list[dict]:
    try:
        await page.goto(URL, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)
        return await page.evaluate("""() => {
            const articles = [];
            const seen = new Set();
            document.querySelectorAll('article a, h2 a, h3 a, .entry-title a, .news-item a').forEach(a => {
                const href = a.getAttribute('href') || '';
                if (!href || seen.has(href) || href === '#') return;
                seen.add(href);
                const title = a.textContent.trim();
                if (!title || title.length < 10) return;
                const fullLink = href.startsWith('http') ? href : '""" + BASE + """' + href;
                articles.push({title, link: fullLink, description: ''});
            });
            return articles.slice(0, 25);
        }""")
    except Exception:
        return []
