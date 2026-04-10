"""Tennis.com - https://www.tennis.com/news
Listing: desc in p tags. No date on listing.
Article: meta[name=description], date as visible text "Published Mar 23, 2026"."""

URL = "https://www.tennis.com/news"
BASE = "https://www.tennis.com"


from scrapers.utils import log_progress, log_done


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    links = await page.evaluate("""() => {
        const articles = [];
        const seen = new Set();
        document.querySelectorAll('a[href*="/news/articles/"]').forEach(a => {
            const href = a.getAttribute('href') || '';
            if (seen.has(href)) return;
            seen.add(href);
            const h = a.querySelector('h2, h3');
            let title = h ? h.textContent.trim() : '';
            if (!title) title = a.getAttribute('aria-label') || '';
            if (!title) { const sp = a.querySelector('span'); if (sp) title = sp.textContent.trim(); }
            if (!title || title.length < 10) return;
            const p = a.querySelector('p');
            const desc = p ? p.textContent.trim().substring(0, 500) : '';
            articles.push({
                title: title,
                link: href.startsWith('http') ? href : '""" + BASE + """' + href,
                description: desc,
            });
        });
        return articles.slice(0, 25);
    }""")

    articles = []
    for idx, item in enumerate(links, 1):
        log_progress(idx, len(links))
        try:
            await page.goto(item["link"], wait_until="domcontentloaded", timeout=12000)
            await page.wait_for_timeout(1500)
            meta = await page.evaluate("""() => {
                var date = '';
                var desc = '';
                // Date from visible text
                var els = document.querySelectorAll('[class*="date"], [class*="Date"]');
                for (var i = 0; i < els.length; i++) {
                    var t = els[i].textContent.trim().replace(/^Published\\s*/i, '');
                    if (t.match(/\\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\\b/i)) { date = t; break; }
                }
                // Desc from meta
                var m = document.querySelector('meta[name="description"]');
                if (m) desc = m.getAttribute('content') || '';
                return {date: date, desc: desc.substring(0, 500)};
            }""")
            articles.append({
                **item,
                "description": item["description"] or meta["desc"],
                "date": meta["date"],
            })
        except Exception:
            articles.append({**item, "date": ""})
    log_done()
    return articles
