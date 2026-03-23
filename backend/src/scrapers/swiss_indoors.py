"""Swiss Indoors Basel - https://www.swissindoorsbasel.ch/en/tournament/news"""

URL = "https://www.swissindoorsbasel.ch/en/tournament/news"
BASE = "https://www.swissindoorsbasel.ch"


async def scrape(page) -> list[dict]:
    try:
        await page.goto(URL, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)
        return await page.evaluate("""() => {
            const articles = [];
            const seen = new Set();
            document.querySelectorAll('a[href*="/news/"], article a, h2 a, h3 a').forEach(a => {
                const href = a.getAttribute('href') || '';
                if (!href || seen.has(href) || href.endsWith('/news') || href.endsWith('/news/')) return;
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
