"""Tennis Infinity - https://tennis-infinity.com/ (Next.js/Newsifier SPA)
Desc+date from article meta tags. Listing has dates in spans but no year."""

URL = "https://tennis-infinity.com/"
BASE = "https://tennis-infinity.com"


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(5000)

    links = await page.evaluate("""() => {
        const articles = [];
        const seen = new Set();
        document.querySelectorAll('a[href*="/news/"]').forEach(a => {
            const href = a.getAttribute('href') || '';
            if (!href || href === '/news/' || href === '/news' || seen.has(href)) return;
            const text = a.textContent.trim();
            if (!text || text.length < 15) return;
            seen.add(href);
            const title = text.split('\\n')[0].trim().substring(0, 200);
            const fullLink = href.startsWith('http') ? href : '""" + BASE + """' + href;
            articles.push({title, link: fullLink});
        });
        return articles.slice(0, 20);
    }""")

    articles = []
    for item in links:
        try:
            await page.goto(item["link"], wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)
            meta = await page.evaluate("""() => {
                var desc = '';
                var date = '';
                var m = document.querySelector('meta[name="description"]');
                if (m) desc = m.getAttribute('content') || '';
                var d = document.querySelector('meta[property="article:published_time"]');
                if (d) date = d.getAttribute('content') || '';
                return {desc: desc.substring(0, 500), date: date};
            }""")
            articles.append({
                "title": item["title"], "link": item["link"],
                "description": meta["desc"], "date": meta["date"],
            })
        except Exception:
            articles.append({"title": item["title"], "link": item["link"], "description": "", "date": ""})

    return articles
