"""Tennis Europe - https://www.tenniseurope.org/newslist/News
Requires cookie consent acceptance before content loads."""

URL = "https://www.tenniseurope.org/newslist/News"
BASE = "https://www.tenniseurope.org"


async def scrape(page) -> list[dict]:
    try:
        await page.goto(URL, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2000)

        # Accept cookie consent if present
        try:
            btn = page.locator("button", has_text="accept")
            if await btn.count() > 0:
                await btn.first.click()
                await page.wait_for_timeout(3000)
            else:
                btn2 = page.locator("button", has_text="Select all and save")
                if await btn2.count() > 0:
                    await btn2.first.click()
                    await page.wait_for_timeout(3000)
        except Exception:
            pass

        return await page.evaluate("""() => {
            const articles = [];
            const seen = new Set();
            document.querySelectorAll('a[href*="/news/"]').forEach(a => {
                const href = a.getAttribute('href') || '';
                if (!href.match(/\\/news\\/\\d+/)) return;
                if (seen.has(href)) return;
                seen.add(href);
                const title = a.textContent.trim();
                if (!title || title.length < 10 || title === 'Read more »' || title === 'Latest News') return;
                const fullLink = href.startsWith('http') ? href : '""" + BASE + """' + href;
                articles.push({title, link: fullLink, description: ''});
            });
            return articles.slice(0, 25);
        }""")
    except Exception:
        return []
