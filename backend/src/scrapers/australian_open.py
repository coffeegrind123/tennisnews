"""Australian Open - https://ausopen.com/news
Date on listing via time element. Desc from article meta."""

URL = "https://ausopen.com/news"
BASE = "https://ausopen.com"


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
            // Date from nearby time element
            const container = h2.closest('div, section, article');
            const timeEl = container ? container.querySelector('time') : null;
            const date = timeEl ? (timeEl.textContent.trim() || '') : '';
            articles.push({title, link: fullLink, date: date});
        });
        return articles.slice(0, 20);
    }""")

    articles = []
    for item in links:
        try:
            await page.goto(item["link"], wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(1500)
            desc = await page.evaluate("""() => {
                var m = document.querySelector('meta[name="description"]');
                return m ? (m.getAttribute('content') || '').substring(0, 500) : '';
            }""")
            articles.append({
                "title": item["title"], "link": item["link"],
                "description": desc, "date": item.get("date", ""),
            })
        except Exception:
            articles.append({"title": item["title"], "link": item["link"], "description": "", "date": item.get("date", "")})

    return articles
