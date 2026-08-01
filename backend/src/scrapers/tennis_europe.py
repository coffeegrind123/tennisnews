"""Tennis Europe - https://www.tenniseurope.org/newslist/News

Hard cookie wall: the news URL 302s to /cookies/?returnurl=... until consent is
stored, so nothing can be read until a consent button is clicked. The consent
buttons are ASP.NET submits identified by class (js-accept-basic /
js-select-all-save), not by a stable label -- the visible text is "Yes, I accept",
which a text match for "accept" only catches by luck and which changes with the
site's language.

Desc in .newsabstract p, date in .post span.date. A second, denser list at the
bottom of the page is a table of "DD/MM/YYYY - Title" rows.
"""

URL = "https://www.tenniseurope.org/newslist/News"
BASE = "https://www.tenniseurope.org"

# The ASP.NET backend is slow and the consent redirect adds a second round trip.
NAV_TIMEOUT_MS = 60000

CONSENT_SELECTORS = (
    "button.js-accept-basic",
    "button.js-select-all-save",
    "button.js-save",
)


async def _accept_cookies(page) -> bool:
    """Returns True if we ended up on the news page rather than the cookie wall."""
    if "/cookies" not in page.url:
        return True
    for sel in CONSENT_SELECTORS:
        try:
            loc = page.locator(sel)
            if await loc.count() == 0:
                continue
            await loc.first.click(timeout=8000)
            await page.wait_for_timeout(2500)
            if "/cookies" not in page.url:
                return True
        except Exception:
            continue
    # Consent stored but no redirect back: go to the news list directly.
    await page.goto(URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
    await page.wait_for_timeout(2000)
    return "/cookies" not in page.url


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
    await page.wait_for_timeout(2000)

    if not await _accept_cookies(page):
        raise RuntimeError(
            f"Tennis Europe: stuck on the cookie wall at {page.url} - none of "
            f"{CONSENT_SELECTORS} produced a redirect back to the news list"
        )

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
