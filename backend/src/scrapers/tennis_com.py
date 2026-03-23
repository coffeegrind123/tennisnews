"""Tennis.com - https://www.tennis.com/news"""

URL = "https://www.tennis.com/news"
BASE = "https://www.tennis.com"


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    return await page.evaluate("""() => {
        const articles = [];
        const seen = new Set();
        document.querySelectorAll('a[href*="/news/articles/"]').forEach(a => {
            const href = a.getAttribute('href') || '';
            if (seen.has(href)) return;
            seen.add(href);
            const h = a.querySelector('h2, h3');
            const title = h ? h.textContent.trim() : a.textContent.trim().substring(0, 200);
            if (!title || title.length < 10) return;
            const p = a.querySelector('p');
            articles.push({
                title: title,
                link: href.startsWith('http') ? href : '""" + BASE + """' + href,
                description: p ? p.textContent.trim().substring(0, 300) : ''
            });
        });
        return articles.slice(0, 25);
    }""")
