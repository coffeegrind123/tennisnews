"""Tennis View Magazine - http://www.tennisviewmag.com/ (Drupal)
Desc in p.teaser, date in span.date on listing."""

URL = "http://www.tennisviewmag.com/tennis-view-magazine/news"
BASE = "http://www.tennisviewmag.com"


async def scrape(page) -> list[dict]:
    try:
        await page.goto(URL, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(4000)

        return await page.evaluate("""(function() {
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
            // Get desc and date from each row
            var rows = document.querySelectorAll('.views-row, tr.views-row');
            var rowData = {};
            rows.forEach(function(row) {
                var a = row.querySelector('a[href*="/article/"]');
                if (!a) return;
                var href = a.getAttribute('href');
                var teaser = row.querySelector('p.teaser, .teaser');
                var dateEl = row.querySelector('span.date, .date');
                rowData[href] = {
                    desc: teaser ? teaser.textContent.trim().substring(0, 500) : '',
                    date: dateEl ? dateEl.textContent.trim() : ''
                };
            });
            var articles = [];
            for (var key in byHref) {
                if (byHref[key].title.length >= 10) {
                    var rd = rowData[key] || {};
                    articles.push({
                        title: byHref[key].title,
                        link: byHref[key].link,
                        description: rd.desc || '',
                        date: rd.date || ''
                    });
                }
            }
            return articles.slice(0, 25);
        })()""")
    except Exception:
        return []
