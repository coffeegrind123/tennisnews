"""ESPN Tennis - https://www.espn.com/tennis/
Desc in .contentItem__subhead on listing. Date from article meta DC.date.issued."""

URL = "https://www.espn.com/tennis/"


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    links = await page.evaluate("""() => {
        const articles = [];
        const seen = new Set();
        document.querySelectorAll('a[href*="/story/"]').forEach(a => {
            const href = a.getAttribute('href') || '';
            if (!href || seen.has(href)) return;
            seen.add(href);
            const title = a.textContent.trim();
            if (!title || title.length < 10) return;
            const fullLink = href.startsWith('http') ? href : 'https://www.espn.com' + href;
            // Try to find subhead/desc nearby
            const parent = a.closest('[class*="contentItem"], article, li, div');
            const sub = parent ? parent.querySelector('[class*="subhead"], [class*="description"], p') : null;
            const desc = sub ? sub.textContent.trim().substring(0, 500) : '';
            articles.push({title, link: fullLink, description: desc});
        });
        return articles.slice(0, 25);
    }""")

    articles = []
    for item in links:
        try:
            await page.goto(item["link"], wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(1500)
            meta = await page.evaluate("""() => {
                var date = '';
                var desc = '';
                var d = document.querySelector('meta[name="DC.date.issued"]');
                if (d) date = d.getAttribute('content') || '';
                if (!date) {
                    var d2 = document.querySelector('meta[property="article:published_time"]');
                    if (d2) date = d2.getAttribute('content') || '';
                }
                var m = document.querySelector('meta[name="description"]');
                if (m) desc = m.getAttribute('content') || '';
                return {date: date, desc: desc.substring(0, 500)};
            }""")
            articles.append({
                "title": item["title"], "link": item["link"],
                "description": item["description"] or meta["desc"],
                "date": meta["date"],
            })
        except Exception:
            articles.append({"title": item["title"], "link": item["link"], "description": item.get("description", ""), "date": ""})

    return articles
