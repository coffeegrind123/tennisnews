"""Tennis Canada - https://www.tenniscanada.com/news

Article tiles are <article class="article-tile">, title in h3.title, date in
p.date > time, link in a.link, description in p.short-description.

The heading level is why this module returned 0 articles from some point before
2026-09-03: it required h2, and the site now renders every tile title as
`<h3 class="title like-h5">` - the "like-h5" telling the story, a heading level
changed while the visual style was pinned. 15 tiles were on the page the whole
time and health.json recorded 339KB of HTML with 4722 characters of body text
against a count of 0.

So the heading is matched by ROLE (.title, or any h2-h4) rather than by level.
A CMS retheme moves a heading level; it does not usually stop calling the
element the title.

The page also renders each of the newest five tiles twice - once in the featured
strip, once in the list below - so the href dedupe is load bearing rather than
defensive.
"""

URL = "https://www.tenniscanada.com/news"


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    return await page.evaluate("""() => {
        const articles = [];
        const seen = new Set();
        document.querySelectorAll('article, .article-tile').forEach(el => {
            const titleEl = el.querySelector('.title, h2, h3, h4');
            // a.link is the tile's own "read more" anchor. Plain 'a' would also
            // match the tag chips in the featured tile's <ul class="article-tags">
            // and link the article to a category listing.
            const a = el.querySelector('a.link[href], a[href]');
            if (!titleEl || !a) return;
            const href = a.href || a.getAttribute('href') || '';
            if (!href || seen.has(href)) return;
            seen.add(href);
            const title = titleEl.textContent.trim();
            if (!title || title.length < 10) return;
            // <time> before .date: p.date wraps an inline calendar SVG, so its
            // textContent carries the icon's whitespace around the date.
            const dateEl = el.querySelector('time, .date, [class*="date"]');
            const date = dateEl ? dateEl.textContent.trim() : '';
            const descEl = el.querySelector('.short-description');
            const desc = descEl ? descEl.textContent.trim().substring(0, 500) : '';
            articles.push({title, link: href, description: desc, date: date});
        });
        return articles.slice(0, 25);
    }""")
