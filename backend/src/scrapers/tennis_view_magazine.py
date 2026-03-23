from scrapers.utils import log_progress, log_done

"""Tennis View Magazine - http://www.tennisviewmag.com/ (Drupal)
Listing: desc in p.teaser (wasn't working before due to dedup), date in span.date.
Article: meta[name=description]. No article:published_time. Date as visible text only."""

URL = "http://www.tennisviewmag.com/tennis-view-magazine/news"
BASE = "http://www.tennisviewmag.com"


async def scrape(page) -> list[dict]:
    try:
        await page.goto(URL, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(4000)

        links = await page.evaluate("""(function() {
            var byHref = {};
            var aa = document.querySelectorAll('a');
            for (var i = 0; i < aa.length; i++) {
                var h = aa[i].getAttribute('href');
                if (!h || h.indexOf('/article/') === -1) continue;
                var t = aa[i].textContent.trim();
                if (t.toLowerCase() === 'read article') continue;
                if (!byHref[h] || (t.length > byHref[h].title.length)) {
                    byHref[h] = {title: t, link: h};
                }
            }
            var articles = [];
            for (var key in byHref) {
                if (byHref[key].title.length >= 10) {
                    articles.push(byHref[key]);
                }
            }
            return articles.slice(0, 15);
        })()""")

        articles = []
        for idx, item in enumerate(links, 1):
            log_progress(idx, len(links))
            full_link = item["link"] if item["link"].startswith("http") else BASE + item["link"]
            try:
                await page.goto(full_link, wait_until="domcontentloaded", timeout=12000)
                await page.wait_for_timeout(1500)
                meta = await page.evaluate("""() => {
                    var desc = '';
                    var date = '';
                    var m = document.querySelector('meta[name="description"]');
                    if (m) desc = m.getAttribute('content') || '';
                    var els = document.querySelectorAll('[class*="date"], .date, span.date');
                    for (var i = 0; i < els.length; i++) {
                        var t = els[i].textContent.trim();
                        if (t.match(/\\d{4}/)) { date = t; break; }
                    }
                    return {desc: desc.substring(0, 500), date: date};
                }""")
                articles.append({
                    "title": item["title"],
                    "link": full_link,
                    "description": meta["desc"],
                    "date": meta["date"],
                })
            except Exception:
                articles.append({"title": item["title"], "link": full_link, "description": "", "date": ""})
        log_done()
        return articles
    except Exception:
        return []
