"""Tennis Australia - https://www.tennis.com.au/"""

URL = "https://www.tennis.com.au/news-and-events/news-and-features/all-news"
BASE = "https://www.tennis.com.au"


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    return await page.evaluate("""() => {
        const articles = [];
        const seen = new Set();
        document.querySelectorAll('a[class*="teaser"]').forEach(a => {
            const href = a.getAttribute('href') || '';
            if (!href || seen.has(href) || href === '#') return;
            seen.add(href);
            const h3 = a.querySelector('h3');
            const title = h3 ? h3.textContent.trim() : a.textContent.trim().substring(0, 200);
            if (!title || title.length < 10) return;
            const fullLink = href.startsWith('http') ? href : '""" + BASE + """' + href;
            articles.push({title, link: fullLink, description: ''});
        });
        return articles.slice(0, 25);
    }""")
