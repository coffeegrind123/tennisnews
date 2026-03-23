"""ATP Tour - https://www.atptour.com/en/news
No desc/date on listing. Must visit each article for meta description + ld+json date."""

NAME = "ATP Tour"
URL = "https://www.atptour.com/en/news"
BASE = "https://www.atptour.com"


from scrapers.utils import log_progress, log_done


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    links = await page.evaluate("""() => {
        const articles = [];
        document.querySelectorAll('.atp_card').forEach(card => {
            const link = card.querySelector('a.card-link');
            const title = card.querySelector('h3');
            if (!title || !link) return;
            const t = title.textContent.trim();
            const href = link.getAttribute('href') || '';
            if (!t || t.length < 5) return;
            if (href.includes('/video/')) return;
            articles.push({
                title: t,
                link: href.startsWith('http') ? href : '""" + BASE + """' + href,
            });
        });
        return articles.slice(0, 20);
    }""")

    articles = []
    for idx, item in enumerate(links, 1):
        log_progress(idx, len(links))
        try:
            await page.goto(item["link"], wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(1500)
            meta = await page.evaluate("""() => {
                var desc = '';
                var date = '';
                var is404 = document.title.includes('404');
                if (!is404) {
                    var m = document.querySelector('meta[name="description"]');
                    if (m) desc = m.getAttribute('content') || '';
                    var ld = document.querySelector('script[type="application/ld+json"]');
                    if (ld) {
                        try {
                            var j = JSON.parse(ld.textContent);
                            if (j.datePublished) date = j.datePublished;
                        } catch(e) {}
                    }
                }
                return {desc: desc.substring(0, 500), date: date, is404: is404};
            }""")
            date = meta["date"]
            if not date:
                from datetime import datetime, timezone
                date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            articles.append({
                "title": item["title"],
                "link": item["link"],
                "description": meta["desc"],
                "date": date,
            })
        except Exception:
            articles.append({"title": item["title"], "link": item["link"], "description": "", "date": ""})

    log_done()
    return articles
