"""Australian Open - https://ausopen.com/news (Drupal 10)
Listing: no desc, time element has text date but empty datetime attr.
Article: meta[name=description]. No article:published_time. Time text on page."""

URL = "https://ausopen.com/news"
BASE = "https://ausopen.com"


from scrapers.utils import log_progress, log_done


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(4000)

    links = await page.evaluate("""() => {
        const articles = [];
        const seen = new Set();
        document.querySelectorAll('h2').forEach(h2 => {
            const title = h2.textContent.trim();
            if (!title || title.length < 10 || seen.has(title)) return;
            seen.add(title);
            const parent = h2.closest('a') || h2.parentElement?.closest('a');
            let link = '';
            if (parent) link = parent.getAttribute('href') || '';
            if (!link) {
                const container = h2.closest('div, section');
                if (container) {
                    const a = container.querySelector('a[href*="/articles/"]');
                    if (a) link = a.getAttribute('href') || '';
                }
            }
            if (!link) return;
            const fullLink = link.startsWith('http') ? link : '""" + BASE + """' + link;
            articles.push({title, link: fullLink});
        });
        return articles.slice(0, 15);
    }""")

    articles = []
    for idx, item in enumerate(links, 1):
        log_progress(idx, len(links))
        try:
            await page.goto(item["link"], wait_until="domcontentloaded", timeout=12000)
            await page.wait_for_timeout(1500)
            meta = await page.evaluate("""() => {
                var desc = '';
                var date = '';
                var m = document.querySelector('meta[name="description"]');
                if (m) desc = m.getAttribute('content') || '';
                // Time element has text date like "11 March 2026"
                var t = document.querySelector('time');
                if (t) date = t.textContent.trim();
                return {desc: desc.substring(0, 500), date: date};
            }""")
            articles.append({
                "title": item["title"], "link": item["link"],
                "description": meta["desc"], "date": meta["date"],
            })
        except Exception:
            articles.append({"title": item["title"], "link": item["link"], "description": "", "date": ""})
    log_done()
    return articles
