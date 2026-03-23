"""Wimbledon - https://www.wimbledon.com/en_GB/news/index.html
Heavy JS SPA - extract article titles and links from the news feed."""

URL = "https://www.wimbledon.com/en_GB/news/index.html"
BASE = "https://www.wimbledon.com"


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(5000)

    return await page.evaluate("""() => {
        const articles = [];
        const seen = new Set();
        // Wimbledon renders news items as clickable tiles with data attributes
        // Extract from all anchor links that point to news content
        document.querySelectorAll('a').forEach(a => {
            const href = a.getAttribute('href') || '';
            if (!href.includes('/news/') && !href.includes('/en_GB/')) return;
            if (href === '/en_GB/news/index.html' || href.endsWith('/news/')) return;
            // Must be an article path (contains date-like or article slug)
            if (!href.match(/\\d{4}/) && !href.match(/[a-z]+-[a-z]+/)) return;
            if (seen.has(href)) return;
            seen.add(href);
            const title = a.textContent.trim().substring(0, 200);
            if (!title || title.length < 15) return;
            const fullLink = href.startsWith('http') ? href : '""" + BASE + """' + href;
            articles.push({title, link: fullLink, description: ''});
        });
        return articles.slice(0, 25);
    }""")
