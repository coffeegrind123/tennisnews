"""ESPN Tennis - https://www.espn.com/tennis/"""

URL = "https://www.espn.com/tennis/"


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    return await page.evaluate("""() => {
        const articles = [];
        const seen = new Set();
        document.querySelectorAll('a[href*="/story/"]').forEach(a => {
            const href = a.getAttribute('href') || '';
            if (!href || seen.has(href)) return;
            seen.add(href);
            const title = a.textContent.trim();
            if (!title || title.length < 10) return;
            const fullLink = href.startsWith('http') ? href : 'https://www.espn.com' + href;
            articles.push({title, link: fullLink, description: ''});
        });
        return articles.slice(0, 25);
    }""")
