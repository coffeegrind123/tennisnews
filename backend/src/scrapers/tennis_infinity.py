"""Tennis Infinity - https://tennis-infinity.com/ (Next.js/Newsifier SPA)"""

URL = "https://tennis-infinity.com/"
BASE = "https://tennis-infinity.com"


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(5000)

    return await page.evaluate("""() => {
        const articles = [];
        const seen = new Set();
        document.querySelectorAll('a[href*="/news/"]').forEach(a => {
            const href = a.getAttribute('href') || '';
            if (!href || href === '/news/' || href === '/news' || seen.has(href)) return;
            // Skip nav links (short text like "News", "ATP", etc.)
            const text = a.textContent.trim();
            if (!text || text.length < 15) return;
            seen.add(href);
            const title = text.split('\\n')[0].trim().substring(0, 200);
            const fullLink = href.startsWith('http') ? href : '""" + BASE + """' + href;
            articles.push({title, link: fullLink, description: ''});
        });
        return articles.slice(0, 25);
    }""")
