"""Asian Tennis Federation - https://www.asiantennis.com/news/
Date in .post-date on listing. No desc available."""

URL = "https://www.asiantennis.com/news/"
BASE = "https://www.asiantennis.com"


async def scrape(page) -> list[dict]:
    try:
        await page.goto(URL, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)
        return await page.evaluate("""() => {
            const articles = [];
            const seen = new Set();
            document.querySelectorAll('.list-post-content, article, .post').forEach(el => {
                const a = el.querySelector('h3 a, h4 a, a');
                if (!a) return;
                const href = a.getAttribute('href') || '';
                if (!href || seen.has(href) || href === '#') return;
                seen.add(href);
                const title = a.textContent.trim();
                if (!title || title.length < 10) return;
                const dateEl = el.querySelector('.post-date, [class*="date"]');
                const date = dateEl ? dateEl.textContent.trim() : '';
                const fullLink = href.startsWith('http') ? href : '""" + BASE + """' + href;
                articles.push({title, link: fullLink, description: '', date: date});
            });
            return articles.slice(0, 25);
        }""")
    except Exception:
        return []
