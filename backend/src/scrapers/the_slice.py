"""The Slice - https://www.theslicetennis.com/articles (Squarespace)"""

URL = "https://www.theslicetennis.com/articles"
BASE = "https://www.theslicetennis.com"


async def scrape(page) -> list[dict]:
    try:
        await page.goto(URL, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)
        return await page.evaluate("""() => {
            const articles = [];
            const seen = new Set();
            // Squarespace blog uses .summary-title or similar
            document.querySelectorAll('a[href*="/articles/"]').forEach(a => {
                const href = a.getAttribute('href') || '';
                if (!href || href === '/articles' || href === '/articles/' || seen.has(href)) return;
                seen.add(href);
                const title = a.textContent.trim().substring(0, 200);
                if (!title || title.length < 10) return;
                const fullLink = href.startsWith('http') ? href : '""" + BASE + """' + href;
                articles.push({title, link: fullLink, description: ''});
            });
            return articles.slice(0, 25);
        }""")
    except Exception:
        return []
