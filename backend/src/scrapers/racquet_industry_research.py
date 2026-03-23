"""Racquet Industry Research - https://www.racquetindustryresearch.org/news/
YourMembership CMS. Dates in bold text before articles. No desc."""

URL = "https://www.racquetindustryresearch.org/news/"
BASE = "https://www.racquetindustryresearch.org"


async def scrape(page) -> list[dict]:
    try:
        await page.goto(URL, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)
        return await page.evaluate("""() => {
            var articles = [];
            var seen = {};
            // Each news item has: date in small>b, title in a with /news/DIGITS/ href
            // Description follows as text after the link
            var cells = document.querySelectorAll('td');
            var currentDate = '';
            cells.forEach(function(td) {
                var dateEl = td.querySelector('.small b, b');
                if (dateEl) {
                    var d = dateEl.textContent.trim();
                    if (d.match(/\\d{4}$/)) currentDate = d;
                }
                var links = td.querySelectorAll('a');
                links.forEach(function(a) {
                    var href = a.getAttribute('href') || '';
                    if (!href.match(/\\/news\\/\\d+\\//)) return;
                    if (href.indexOf('#') > -1) return;
                    if (seen[href]) return;
                    seen[href] = true;
                    var title = a.textContent.trim();
                    if (!title || title.length < 10 || title === 'Read more \\u00bb') return;
                    var fullLink = href.startsWith('http') ? href : '""" + BASE + """' + href;
                    // Try to get description from sibling text
                    var desc = '';
                    var next = a.nextSibling;
                    while (next) {
                        if (next.nodeType === 3) desc += next.textContent;
                        if (next.nodeType === 1 && next.tagName === 'BR') break;
                        next = next.nextSibling;
                    }
                    articles.push({
                        title: title,
                        link: fullLink,
                        description: desc.trim().substring(0, 500),
                        date: currentDate
                    });
                });
            });
            return articles.slice(0, 25);
        }""")
    except Exception:
        return []
