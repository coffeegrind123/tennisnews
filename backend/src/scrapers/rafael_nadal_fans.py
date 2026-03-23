"""Rafael Nadal Fans - https://rafaelnadalfans.com/ (WordPress)
Listing: date in time[datetime]. No desc on listing.
Article: og:description (NOT name=description), article:published_time."""

URL = "https://rafaelnadalfans.com/"


from scrapers.utils import log_progress, log_done


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    links = await page.evaluate("""() => {
        const articles = [];
        const seen = new Set();
        document.querySelectorAll('.entry-title a, article h2 a').forEach(a => {
            const href = a.getAttribute('href') || '';
            if (!href || seen.has(href)) return;
            seen.add(href);
            const title = a.textContent.trim();
            if (!title || title.length < 10) return;
            const container = a.closest('article, .post, div');
            const timeEl = container ? container.querySelector('time[datetime]') : null;
            const date = timeEl ? (timeEl.getAttribute('datetime') || '') : '';
            articles.push({title, link: href, date: date});
        });
        return articles.slice(0, 15);
    }""")

    articles = []
    for idx, item in enumerate(links, 1):
        log_progress(idx, len(links))
        try:
            await page.goto(item["link"], wait_until="domcontentloaded", timeout=12000)
            await page.wait_for_timeout(1500)
            desc = await page.evaluate("""() => {
                var m = document.querySelector('meta[property="og:description"]');
                return m ? (m.getAttribute('content') || '').substring(0, 500) : '';
            }""")
            articles.append({**item, "description": desc})
        except Exception:
            articles.append({**item, "description": ""})
    log_done()
    return articles
