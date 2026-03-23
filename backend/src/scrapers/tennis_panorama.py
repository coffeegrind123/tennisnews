"""Tennis Panorama - https://www.tennispanorama.com/ (WordPress/GenerateBlocks)
Desc in .gb-block-post-grid-excerpt, date in .gb-block-post-grid-date."""

URL = "https://www.tennispanorama.com/"


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    return await page.evaluate("""() => {
        const articles = [];
        const seen = new Set();
        document.querySelectorAll('h3 a').forEach(a => {
            const href = a.getAttribute('href') || '';
            if (!href || seen.has(href) || href === '#') return;
            seen.add(href);
            const title = a.textContent.trim();
            if (!title || title.length < 10) return;
            const container = a.closest('[class*="gb-block-post"], article, div');
            const descEl = container ? container.querySelector('[class*="excerpt"]') : null;
            const desc = descEl ? descEl.textContent.trim().substring(0, 500) : '';
            const dateEl = container ? container.querySelector('[class*="date"]') : null;
            const date = dateEl ? dateEl.textContent.trim() : '';
            articles.push({title, link: href, description: desc, date: date});
        });
        return articles.slice(0, 25);
    }""")
