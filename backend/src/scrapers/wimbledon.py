"""Wimbledon - https://www.wimbledon.com/en_GB/news/index.html
JS SPA. Extract article links directly from DOM, visit each for desc + date.
Previous text-parsing approach broke when site stopped separating category labels on own lines."""

from scrapers.utils import log_progress, log_done

URL = "https://www.wimbledon.com/en_GB/news/index.html"
BASE = "https://www.wimbledon.com"

import re


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(5000)

    links = await page.evaluate("""() => {
        const articles = [];
        const seen = new Set();
        document.querySelectorAll('a[href*="/news/articles/"]').forEach(a => {
            const href = a.getAttribute('href') || '';
            if (!href || seen.has(href)) return;
            seen.add(href);
            let title = '';
            const headings = a.querySelectorAll('h2, h3, h4, [class*="title"], [class*="heading"]');
            for (const h of headings) {
                const t = h.textContent.trim();
                if (t.length > 10) { title = t; break; }
            }
            if (!title) title = a.getAttribute('aria-label') || '';
            if (!title) {
                const text = a.textContent.trim().replace(/\\s+/g, ' ');
                const cleaned = text
                    .replace(/^(NEWS|FEATURE|FOUNDATION|news|feature|foundation)\\s*/i, '')
                    .replace(/[A-Z]{3}\\s+\\d{1,2}\\s+[A-Z]{3}\\s+\\d{4}\\s*\\d{2}:\\d{2}\\s*GMT\\s*/gi, '')
                    .replace(/^\\d+\\s+DAYS?\\s+AGO\\s*/i, '')
                    .trim();
                if (cleaned.length > 10) title = cleaned.substring(0, 200);
            }
            if (!title || title.length < 10) return;
            const fullLink = href.startsWith('http') ? href : '""" + BASE + """' + href;
            articles.push({title, link: fullLink});
        });
        return articles.slice(0, 20);
    }""")

    articles = []
    for idx, item in enumerate(links, 1):
        log_progress(idx, len(links))
        try:
            await page.goto(item["link"], wait_until="domcontentloaded", timeout=12000)
            await page.wait_for_timeout(2000)
            meta = await page.evaluate("""() => {
                var desc = '';
                var date = '';
                var ps = document.querySelectorAll('p');
                for (var i = 0; i < ps.length; i++) {
                    var t = ps[i].textContent.trim();
                    if (t.length > 50 && !t.match(/^(cookie|we use|accept|your browser)/i)) {
                        desc = t; break;
                    }
                }
                var rd = document.querySelector('meta[name="resultdate"]');
                if (rd) {
                    var ms = parseInt(rd.getAttribute('content'));
                    if (ms > 0) date = new Date(ms).toISOString();
                }
                if (!date) {
                    var d2 = document.querySelector('meta[property="article:published_time"]');
                    if (d2) date = d2.getAttribute('content') || '';
                }
                return {desc: desc.substring(0, 500), date: date};
            }""")
            articles.append({**item, "description": meta["desc"], "date": meta["date"]})
        except Exception:
            articles.append({**item, "description": "", "date": ""})

    log_done()
    return articles
