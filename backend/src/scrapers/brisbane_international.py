"""Brisbane International - redirects to tennis.com.au/brisbane-international
Same AEM CMS as Tennis Australia."""

URL = "https://www.brisbaneinternational.com.au/"
BASE = "https://www.tennis.com.au"


async def scrape(page) -> list[dict]:
    try:
        await page.goto(URL, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)
        return await page.evaluate("""() => {
            const articles = [];
            const seen = new Set();
            document.querySelectorAll('a[class*="teaser"]').forEach(a => {
                const href = a.getAttribute('href') || '';
                if (!href || seen.has(href) || href === '#') return;
                seen.add(href);
                const h3 = a.querySelector('h3');
                const title = h3 ? h3.textContent.trim() : '';
                if (!title || title.length < 10) return;
                const descEl = a.querySelector('[class*="description"]');
                const desc = descEl ? descEl.textContent.trim().substring(0, 500) : '';
                const dateEl = a.querySelector('[class*="published-date"], [class*="date"]');
                const date = dateEl ? dateEl.textContent.trim() : '';
                const fullLink = href.startsWith('http') ? href : '""" + BASE + """' + href;
                articles.push({title, link: fullLink, description: desc, date: date});
            });
            // Fallback: any news links
            if (articles.length === 0) {
                document.querySelectorAll('a[href*="/news/"], h2 a, h3 a').forEach(a => {
                    const href = a.getAttribute('href') || '';
                    if (!href || seen.has(href) || href === '#') return;
                    seen.add(href);
                    const title = a.textContent.trim();
                    if (!title || title.length < 10) return;
                    const fullLink = href.startsWith('http') ? href : '""" + BASE + """' + href;
                    articles.push({title, link: fullLink, description: '', date: ''});
                });
            }
            return articles.slice(0, 25);
        }""")
    except Exception:
        return []
