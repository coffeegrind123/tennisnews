"""Asian Tennis Federation - https://www.asiantennis.com/news/
No meta description anywhere. Date in .post-date on listing.
Article: first paragraph is only source of desc."""

URL = "https://www.asiantennis.com/news/"
BASE = "https://www.asiantennis.com"


from scrapers.utils import log_progress, log_done


async def scrape(page) -> list[dict]:
    try:
        await page.goto(URL, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)

        links = await page.evaluate("""() => {
            const articles = [];
            const seen = new Set();
            document.querySelectorAll('.list-post-content, article, .post').forEach(el => {
                const a = el.querySelector('h3 a, h4 a, a');
                if (!a) return;
                const href = a.getAttribute('href') || '';
                if (!href || seen.has(href) || href === '#') return;
                seen.add(href);
                const title = a.textContent.trim();
                if (!title || title.length < 10) return;
                const dateEl = el.querySelector('.post-date, [class*="date"]');
                const date = dateEl ? dateEl.textContent.trim() : '';
                const fullLink = href.startsWith('http') ? href : '""" + BASE + """' + href;
                articles.push({title, link: fullLink, date: date});
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
                    var ps = document.querySelectorAll('p');
                    for (var i = 0; i < ps.length; i++) {
                        var t = ps[i].textContent.trim();
                        if (t.length > 50 && !t.match(/^(cookie|we use|accept|privacy)/i)) {
                            return t.substring(0, 500);
                        }
                    }
                    return '';
                }""")
                articles.append({**item, "description": desc})
            except Exception:
                articles.append({**item, "description": ""})
        log_done()
        return articles
    except Exception:
        return []
