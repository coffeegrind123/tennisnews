"""Racquet Sports Industry - https://tennisindustrymag.com/news/
Note: This site returns 403 Forbidden. Scraper attempts access but may fail."""

URL = "https://tennisindustrymag.com/news/"


async def scrape(page) -> list[dict]:
    try:
        await page.goto(URL, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(2000)
        text = await page.evaluate("() => document.body.textContent.trim().substring(0, 200)")
        if "denied" in text.lower() or "403" in text or "forbidden" in text.lower():
            return []
        return await page.evaluate("""() => {
            const articles = [];
            const seen = new Set();
            document.querySelectorAll('article a, h2 a, h3 a').forEach(a => {
                const href = a.getAttribute('href') || '';
                if (!href || seen.has(href)) return;
                seen.add(href);
                const title = a.textContent.trim();
                if (!title || title.length < 10) return;
                articles.push({title, link: href, description: ''});
            });
            return articles.slice(0, 25);
        }""")
    except Exception:
        return []
