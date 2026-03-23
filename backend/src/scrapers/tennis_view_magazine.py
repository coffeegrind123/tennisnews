"""Tennis View Magazine - http://www.tennisviewmag.com/ (Drupal)"""

URL = "http://www.tennisviewmag.com/tennis-view-magazine/news"
BASE = "http://www.tennisviewmag.com"


async def scrape(page) -> list[dict]:
    try:
        await page.goto(URL, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(4000)

        raw = await page.evaluate("""(function() {
            var byHref = {};
            var aa = document.querySelectorAll('a');
            for (var i = 0; i < aa.length; i++) {
                var h = aa[i].getAttribute('href');
                if (!h || h.indexOf('/article/') === -1) continue;
                var t = aa[i].textContent.trim();
                if (t.toLowerCase() === 'read article') continue;
                if (!byHref[h] || (t.length > byHref[h].title.length)) {
                    byHref[h] = {title: t, link: h, description: ''};
                }
            }
            var articles = [];
            for (var key in byHref) {
                if (byHref[key].title.length >= 10) {
                    articles.push(byHref[key]);
                }
            }
            return articles.slice(0, 25);
        })()""")

        for a in raw:
            if not a["link"].startswith("http"):
                a["link"] = BASE + a["link"]
        return raw
    except Exception:
        return []
