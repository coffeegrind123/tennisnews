"""Brisbane International - redirects to tennis.com.au/brisbane-international
AEM CMS. Listing: desc in .cmp-teaser__description, date in .cmp-teaser__published-date.
Article: meta[name=description], DC.description. Date as visible text."""

from scrapers.utils import log_progress, log_done

URL = "https://www.brisbaneinternational.com.au/"
BASE = "https://www.tennis.com.au"


async def scrape(page) -> list[dict]:
    try:
        await page.goto(URL, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)

        links = await page.evaluate("""() => {
            const articles = [];
            const seen = new Set();
            document.querySelectorAll('a[class*="teaser"]').forEach(a => {
                const href = a.getAttribute('href') || '';
                if (!href || seen.has(href) || href === '#') return;
                seen.add(href);
                const h3 = a.querySelector('h3');
                const title = h3 ? h3.textContent.trim() : '';
                if (!title || title.length < 10) return;
                if (/^(Visit|Welcome to|Experience|Getting|Tickets|How to)/i.test(title)) return;
                const descEl = a.querySelector('[class*="description"]');
                const desc = descEl ? descEl.textContent.trim().substring(0, 500) : '';
                const dateEl = a.querySelector('[class*="published-date"], [class*="date"]');
                const date = dateEl ? dateEl.textContent.trim() : '';
                const fullLink = href.startsWith('http') ? href : '""" + BASE + """' + href;
                articles.push({title, link: fullLink, description: desc, date: date});
            });
            return articles.slice(0, 15);
        }""")

        articles = []
        for idx, item in enumerate(links, 1):
            log_progress(idx, len(links))
            if item.get("description") and item.get("date"):
                articles.append(item)
                continue
            try:
                await page.goto(item["link"], wait_until="domcontentloaded", timeout=12000)
                await page.wait_for_timeout(1500)
                meta = await page.evaluate("""() => {
                    var desc = '';
                    var date = '';
                    var m = document.querySelector('meta[name="description"]');
                    if (m) desc = m.getAttribute('content') || '';
                    var els = document.querySelectorAll('[class*="date"]');
                    for (var i = 0; i < els.length; i++) {
                        var t = els[i].textContent.trim();
                        if (t.match(/\\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\\b/i) && t.match(/\\d{4}/)) {
                            date = t; break;
                        }
                    }
                    return {desc: desc.substring(0, 500), date: date};
                }""")
                articles.append({
                    **item,
                    "description": item.get("description") or meta["desc"],
                    "date": item.get("date") or meta["date"],
                })
            except Exception:
                articles.append(item)
        log_done()
        return articles
    except Exception:
        return []
