"""Wimbledon - https://www.wimbledon.com/en_GB/news

Next.js SPA. The 2026 rebuild replaced the old `/news/articles/<id>` links and
their heading markup with "content tile" components: `a.ct` wrapping
`.ct__title` (headline), `.ct__time` (relative or absolute date) and
`.content-tag` (News / Feature / ...). Links are now `/en_GB/news/<slug>`, so
the previous `a[href*="/news/articles/"]` selector matched nothing and the
source silently returned zero.

Listing gives title + date; the article page is still the only source of a
description.
"""

from scrapers.utils import log_progress, log_done

URL = "https://www.wimbledon.com/en_GB/news/index.html"
BASE = "https://www.wimbledon.com"

# Tiles also cover video/photo galleries, which have no article text.
SKIP_TAGS = {"video", "gallery", "photos", "highlights"}


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="domcontentloaded", timeout=40000)
    await page.wait_for_selector("a.ct", timeout=30000)
    await page.wait_for_timeout(2000)

    links = await page.evaluate("""(skipTags) => {
        const articles = [];
        const seen = new Set();
        document.querySelectorAll('a.ct').forEach(a => {
            const href = a.getAttribute('href') || '';
            if (!href.includes('/news/') || seen.has(href)) return;

            const titleEl = a.querySelector('.ct__title');
            const timeEl = a.querySelector('.ct__time');
            const tagEl = a.querySelector('.content-tag');

            let title = titleEl ? titleEl.textContent.trim() : '';
            if (!title) {
                // aria-label is "<Tag>, <Title>, <Date>, <N> min read"; the title
                // itself can contain commas, so only trust it as a fallback.
                const aria = a.getAttribute('aria-label') || '';
                const parts = aria.split(', ');
                if (parts.length >= 3) title = parts.slice(1, -2).join(', ').trim();
            }
            if (!title || title.length < 10) return;

            const tag = tagEl ? tagEl.textContent.trim().toLowerCase() : '';
            if (skipTags.includes(tag)) return;

            seen.add(href);
            articles.push({
                title: title,
                link: href.startsWith('http') ? href : '""" + BASE + """' + href,
                date: timeEl ? timeEl.textContent.trim() : '',
            });
        });
        return articles.slice(0, 20);
    }""", list(SKIP_TAGS))

    articles = []
    for idx, item in enumerate(links, 1):
        log_progress(idx, len(links))
        try:
            await page.goto(item["link"], wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(1500)
            meta = await page.evaluate("""() => {
                var desc = '';
                var m = document.querySelector('meta[name="description"], meta[property="og:description"]');
                if (m) desc = m.getAttribute('content') || '';
                if (!desc) {
                    var ps = document.querySelectorAll('article p, .article-body p, p');
                    for (var i = 0; i < ps.length; i++) {
                        var t = ps[i].textContent.trim();
                        if (t.length > 50 && !t.match(/^(cookie|we use|accept|your browser)/i)) {
                            desc = t; break;
                        }
                    }
                }
                var date = '';
                var d2 = document.querySelector('meta[property="article:published_time"]');
                if (d2) date = d2.getAttribute('content') || '';
                if (!date) {
                    var t = document.querySelector('time[datetime]');
                    if (t) date = t.getAttribute('datetime') || '';
                }
                if (!date) {
                    // resultdate is epoch MILLIseconds. It also shows up holding a
                    // bare year ("2026"), which parseInt happily turned into 2026ms
                    // -> 1970-01-01. Only trust plausible timestamps.
                    var rd = document.querySelector('meta[name="resultdate"]');
                    if (rd) {
                        var ms = parseInt(rd.getAttribute('content'), 10);
                        if (ms > 946684800000 && ms < 4102444800000) date = new Date(ms).toISOString();
                    }
                }
                return {desc: desc.substring(0, 500), date: date};
            }""")
            articles.append({
                **item,
                "description": meta["desc"],
                # Article metadata is absolute; only fall back to the tile's
                # relative wording ("Yesterday") when the page has neither.
                "date": meta["date"] or item["date"],
            })
        except Exception as e:
            print(f"      [Wimbledon] {item['link']}: {type(e).__name__}: {str(e)[:80]}")
            articles.append({**item, "description": ""})

    log_done()
    return articles
