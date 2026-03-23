"""Tennisbuzz - https://tennisbuzz.net/ (currently DOWN - site not found)"""

URL = "https://tennisbuzz.net/"


async def scrape(page) -> list[dict]:
    try:
        await page.goto(URL, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(2000)
        text = await page.evaluate("() => document.body.textContent.trim().substring(0, 100)")
        if "not found" in text.lower() or "error" in text.lower():
            return []
        return await page.evaluate("""() => {
            const articles = [];
            const seen = new Set();
            document.querySelectorAll('a[href*="/articles/"], a[href*="/news/"]').forEach(a => {
                const href = a.getAttribute('href') || '';
                if (!href || seen.has(href)) return;
                seen.add(href);
                const h = a.querySelector('h2, h3');
                const title = h ? h.textContent.trim() : a.textContent.trim().substring(0, 200);
                if (!title || title.length < 10) return;
                articles.push({title, link: href, description: ''});
            });
            return articles.slice(0, 25);
        }""")
    except Exception:
        return []
