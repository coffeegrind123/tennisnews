"""Australian Open - https://ausopen.com/news"""

URL = "https://ausopen.com/news"
BASE = "https://ausopen.com"


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(4000)

    return await page.evaluate("""() => {
        const articles = [];
        const seen = new Set();
        // Get unique h2 elements as article titles
        document.querySelectorAll('h2').forEach(h2 => {
            const title = h2.textContent.trim();
            if (!title || title.length < 10 || seen.has(title)) return;
            seen.add(title);
            // Find closest link
            const parent = h2.closest('a') || h2.parentElement?.closest('a');
            let link = '';
            if (parent) {
                link = parent.getAttribute('href') || '';
            } else {
                const a = h2.querySelector('a') || h2.parentElement?.querySelector('a[href*="/articles/"]');
                if (a) link = a.getAttribute('href') || '';
            }
            if (!link) {
                // Search nearby for article links
                const container = h2.closest('div, section');
                if (container) {
                    const a = container.querySelector('a[href*="/articles/"]');
                    if (a) link = a.getAttribute('href') || '';
                }
            }
            if (!link) return;
            const fullLink = link.startsWith('http') ? link : '""" + BASE + """' + link;
            articles.push({title, link: fullLink, description: ''});
        });
        return articles.slice(0, 25);
    }""")
