"""The Slice - https://www.theslicetennis.com/articles (Squarespace)
Desc in .blog-excerpt, date in .blog-date on listing."""

URL = "https://www.theslicetennis.com/articles"
BASE = "https://www.theslicetennis.com"


async def scrape(page) -> list[dict]:
    try:
        await page.goto(URL, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)
        return await page.evaluate("""() => {
            const articles = [];
            const seen = new Set();
            document.querySelectorAll('.blog-item, [class*="summary-item"], article').forEach(el => {
                const a = el.querySelector('a[href*="/articles/"]');
                if (!a) return;
                const href = a.getAttribute('href') || '';
                if (!href || href === '/articles' || href === '/articles/' || seen.has(href)) return;
                seen.add(href);
                const titleEl = el.querySelector('.blog-title, h2, h3, [class*="title"]');
                const title = titleEl ? titleEl.textContent.trim() : a.textContent.trim().substring(0, 200);
                if (!title || title.length < 10) return;
                const descEl = el.querySelector('.blog-excerpt, [class*="excerpt"]');
                const desc = descEl ? descEl.textContent.trim().substring(0, 500) : '';
                const dateEl = el.querySelector('.blog-date, [class*="date"]');
                const date = dateEl ? dateEl.textContent.trim() : '';
                const fullLink = href.startsWith('http') ? href : '""" + BASE + """' + href;
                articles.push({title, link: fullLink, description: desc, date: date});
            });
            return articles.slice(0, 25);
        }""")
    except Exception:
        return []
