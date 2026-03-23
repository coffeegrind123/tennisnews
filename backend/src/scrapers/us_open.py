"""US Open - https://www.usopen.org/en_US/news/index.html
IBM-powered JS-heavy SPA. Articles are rendered as clickable divs, not standard links."""

URL = "https://www.usopen.org/en_US/news/index.html"
BASE = "https://www.usopen.org"


async def scrape(page) -> list[dict]:
    try:
        await page.goto(URL, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(5000)

        # Try cookie consent
        try:
            btn = page.locator("button", has_text="Accept All")
            if await btn.count() > 0:
                await btn.first.click()
                await page.wait_for_timeout(2000)
        except Exception:
            pass

        return await page.evaluate("""() => {
            const articles = [];
            const seen = new Set();
            // US Open renders news items as divs/sections with onclick handlers
            // Try finding any anchor-like elements or clickable containers
            const selectors = [
                'a[href*="/en_US/news/"]',
                'a[href*="article"]',
                '[data-url]',
                '[onclick*="news"]',
                'li a',
            ];
            for (const sel of selectors) {
                document.querySelectorAll(sel).forEach(el => {
                    const href = el.getAttribute('href') || el.getAttribute('data-url') || '';
                    if (!href || seen.has(href) || href === '/en_US/news/index.html') return;
                    seen.add(href);
                    const title = el.textContent.trim().substring(0, 200);
                    if (!title || title.length < 15) return;
                    const fullLink = href.startsWith('http') ? href : '""" + BASE + """' + href;
                    articles.push({title, link: fullLink, description: ''});
                });
            }
            // Fallback: extract from visible text nodes that look like headlines
            if (articles.length === 0) {
                const text = document.body.innerText;
                const lines = text.split('\\n').map(l => l.trim()).filter(l => l.length > 20 && l.length < 150);
                const newsLines = lines.filter(l => !l.match(/^(TICKETS|SCHEDULE|VISIT|WATCH|NEWS|SHOP|Home)/));
                newsLines.slice(0, 15).forEach(line => {
                    articles.push({
                        title: line,
                        link: '""" + URL + """',
                        description: ''
                    });
                });
            }
            return articles.slice(0, 25);
        }""")
    except Exception:
        return []
