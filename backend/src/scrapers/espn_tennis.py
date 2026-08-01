"""ESPN Tennis - https://www.espn.com/tennis/
Desc in .contentItem__subhead on listing. Date from article meta DC.date.issued.

The page carries ESPN-wide nav, promos and "more sports" rails, so a bare
a[href*="/story/"] match pulled in NFL/NBA content ("NFL depth charts for all 32
teams") and published it as tennis news. Only /tennis/story/ URLs count."""

URL = "https://www.espn.com/tennis/"


from scrapers.utils import log_progress, log_done


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    links = await page.evaluate("""() => {
        const articles = [];
        const seen = new Set();
        document.querySelectorAll('a[href*="/tennis/story/"]').forEach(a => {
            const href = a.getAttribute('href') || '';
            if (!href || seen.has(href)) return;
            // Guard against absolute links to other sports that happen to
            // contain the substring, and against /tennis/story/ appearing
            // inside a query string.
            if (!/^(https:\\/\\/www\\.espn\\.com)?\\/tennis\\/story\\//.test(href)) return;
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
    for idx, item in enumerate(links, 1):
        log_progress(idx, len(links))
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

    log_done()
    return articles
