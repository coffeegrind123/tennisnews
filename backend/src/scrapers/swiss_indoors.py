"""Swiss Indoors Basel - https://www.swissindoorsbasel.ch/en/tournament/tournament-news/
Desc in .listEntryDescription, date in .listEntryDate."""

URL = "https://www.swissindoorsbasel.ch/en/tournament/tournament-news/"
BASE = "https://www.swissindoorsbasel.ch"


async def scrape(page) -> list[dict]:
    try:
        await page.goto(URL, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)
        text = await page.evaluate("() => document.body.innerText.substring(0, 100)")
        if "404" in text:
            return []
        return await page.evaluate("""() => {
            const articles = [];
            const seen = new Set();
            document.querySelectorAll('li.listEntryObject-news, [class*="listEntry"]').forEach(el => {
                const a = el.querySelector('h3 a, [class*="Title"] a, a');
                if (!a) return;
                const href = a.getAttribute('href') || '';
                if (!href || seen.has(href)) return;
                seen.add(href);
                const title = a.textContent.trim();
                if (!title || title.length < 10) return;
                const descEl = el.querySelector('[class*="Description"]');
                const desc = descEl ? descEl.textContent.trim().substring(0, 500) : '';
                const dateEl = el.querySelector('[class*="Date"]');
                const date = dateEl ? dateEl.textContent.trim().replace(/\\s+/g, ' ') : '';
                const fullLink = href.startsWith('http') ? href : '""" + BASE + """' + href;
                articles.push({title, link: fullLink, description: desc, date: date});
            });
            return articles.slice(0, 25);
        }""")
    except Exception:
        return []
