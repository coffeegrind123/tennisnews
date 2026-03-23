"""Tennis Europe - https://www.tenniseurope.org/newslist/News
Cookie consent required. Desc in .newsabstract p, date in .post span.date."""

URL = "https://www.tenniseurope.org/newslist/News"
BASE = "https://www.tenniseurope.org"


async def scrape(page) -> list[dict]:
    try:
        await page.goto(URL, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2000)

        try:
            btn = page.locator("button", has_text="accept")
            if await btn.count() > 0:
                await btn.first.click()
                await page.wait_for_timeout(3000)
            else:
                btn2 = page.locator("button", has_text="Select all and save")
                if await btn2.count() > 0:
                    await btn2.first.click()
                    await page.wait_for_timeout(3000)
        except Exception:
            pass

        return await page.evaluate("""() => {
            const articles = [];
            const seen = new Set();
            document.querySelectorAll('.post').forEach(el => {
                const a = el.querySelector('h3 a');
                if (!a) return;
                const href = a.getAttribute('href') || '';
                if (!href || !href.match(/\\/news\\/\\d+/) || seen.has(href)) return;
                seen.add(href);
                const title = a.textContent.trim();
                if (!title || title.length < 10) return;
                const descEl = el.querySelector('.newsabstract p, .newsabstract');
                const desc = descEl ? descEl.textContent.trim().substring(0, 500) : '';
                const dateEl = el.querySelector('span.date, .copyright span');
                const date = dateEl ? dateEl.textContent.trim() : '';
                const fullLink = href.startsWith('http') ? href : '""" + BASE + """' + href;
                articles.push({title, link: fullLink, description: desc, date: date});
            });
            // Short news list at bottom: "DD/MM/YYYY\t-\tTitle" with link
            var rows = document.querySelectorAll('tr, li, p, div');
            for (var i = 0; i < rows.length; i++) {
                var text = rows[i].textContent.trim();
                var m = text.match(/^(\\d{2}\\/\\d{2}\\/\\d{4})\\s*[-–]\\s*(.+)/);
                if (m) {
                    var dateStr = m[1]; // DD/MM/YYYY
                    var rowTitle = m[2].trim();
                    if (seen.has(rowTitle)) continue;
                    // Find link in this row
                    var rowLink = '';
                    var ra = rows[i].querySelector('a[href*="/news/"]');
                    if (ra) rowLink = ra.getAttribute('href') || '';
                    if (!rowLink) continue;
                    seen.add(rowTitle);
                    var fullL = rowLink.startsWith('http') ? rowLink : '""" + BASE + """' + rowLink;
                    articles.push({title: rowTitle, link: fullL, description: '', date: dateStr});
                }
            }
            return articles.slice(0, 25);
        }""")
    except Exception:
        return []
