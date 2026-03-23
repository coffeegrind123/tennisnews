"""Racquet Industry Research - https://www.racquetindustryresearch.org/news/
Uses YourMembership CMS with /news/XXXXX/ URL pattern."""

URL = "https://www.racquetindustryresearch.org/news/"
BASE = "https://www.racquetindustryresearch.org"


async def scrape(page) -> list[dict]:
    try:
        await page.goto(URL, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)
        return await page.evaluate("""() => {
            const articles = [];
            const seen = new Set();
            document.querySelectorAll('a').forEach(a => {
                const href = a.getAttribute('href') || '';
                if (!href.match(/\\/news\\/\\d+\\//)) return;
                if (href.includes('#comments')) return;
                if (seen.has(href)) return;
                seen.add(href);
                const title = a.textContent.trim();
                if (!title || title.length < 10 || title === 'Read more »' || title.includes('view/add')) return;
                const fullLink = href.startsWith('http') ? href : '""" + BASE + """' + href;
                articles.push({title, link: fullLink, description: ''});
            });
            return articles.slice(0, 25);
        }""")
    except Exception:
        return []
