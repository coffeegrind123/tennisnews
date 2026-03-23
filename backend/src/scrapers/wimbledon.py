"""Wimbledon - https://www.wimbledon.com/en_GB/news/index.html
JS SPA. No og:description. Date from custom meta[name=resultdate] (Unix ms) or text.
Must parse articles from visible text on listing, then visit for desc + date."""

from scrapers.utils import log_progress, log_done

URL = "https://www.wimbledon.com/en_GB/news/index.html"
BASE = "https://www.wimbledon.com"

import re


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(5000)

    text = await page.evaluate("() => document.body.innerText")
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # Also try to grab actual links
    page_links = await page.evaluate("""() => {
        var links = {};
        document.querySelectorAll('a').forEach(a => {
            var href = a.getAttribute('href') || '';
            if (href.includes('/news/') && href.includes('/articles/')) {
                var text = a.textContent.trim().substring(0, 200);
                if (text.length > 10) links[text] = href.startsWith('http') ? href : '""" + BASE + """' + href;
            }
        });
        return links;
    }""")

    raw = []
    seen = set()
    i = 0
    while i < len(lines) - 1:
        line = lines[i]
        if line in ("NEWS", "FEATURE", "FOUNDATION"):
            date = ""
            title = ""
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                if re.match(r"(\d+ DAYS? AGO|[A-Z]{3} \d{1,2} [A-Z]{3} \d{4})", next_line):
                    date = next_line.split("GMT")[0].strip()
                    if i + 2 < len(lines):
                        title = lines[i + 2]
                        i += 3
                    else:
                        i += 2
                else:
                    title = next_line
                    i += 2
            if title and len(title) > 10 and title not in seen:
                seen.add(title)
                link = page_links.get(title, URL)
                raw.append({"title": title, "link": link, "date": date})
        else:
            i += 1

    # Visit article pages for desc + better dates
    articles = []
    visit_items = raw[:20]
    for idx, item in enumerate(visit_items, 1):
        log_progress(idx, len(visit_items))
        if item["link"] == URL:
            articles.append({**item, "description": ""})
            continue
        try:
            await page.goto(item["link"], wait_until="domcontentloaded", timeout=12000)
            await page.wait_for_timeout(2000)
            meta = await page.evaluate("""() => {
                var desc = '';
                var date = '';
                // First meaningful paragraph for desc
                var ps = document.querySelectorAll('p');
                for (var i = 0; i < ps.length; i++) {
                    var t = ps[i].textContent.trim();
                    if (t.length > 50 && !t.match(/^(cookie|we use|accept|your browser)/i)) {
                        desc = t; break;
                    }
                }
                // Date from custom meta resultdate (Unix ms)
                var rd = document.querySelector('meta[name="resultdate"]');
                if (rd) {
                    var ms = parseInt(rd.getAttribute('content'));
                    if (ms > 0) {
                        var d = new Date(ms);
                        date = d.toISOString();
                    }
                }
                return {desc: desc.substring(0, 500), date: date};
            }""")
            articles.append({
                **item,
                "description": meta["desc"],
                "date": meta["date"] or item["date"],
            })
        except Exception:
            articles.append({**item, "description": ""})

    log_done()
    return articles
