"""Tennis.com - https://www.tennis.com/news
Desc in p tags on listing. Date only on article pages."""

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
            const title = h ? h.textContent.trim() : '';
            if (!title || title.length < 10) return;
            const p = a.querySelector('p');
            const desc = p ? p.textContent.trim().substring(0, 500) : '';
            articles.push({
                title: title,
                link: href.startsWith('http') ? href : '""" + BASE + """' + href,
                description: desc,
                date: ''
            });
        });
        return articles.slice(0, 25);
    }""")
