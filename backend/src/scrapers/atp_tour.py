"""ATP Tour - https://www.atptour.com/en/news"""

NAME = "ATP Tour"
URL = "https://www.atptour.com/en/news"
BASE = "https://www.atptour.com"


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    return await page.evaluate("""() => {
        const articles = [];
        document.querySelectorAll('.atp_card').forEach(card => {
            const link = card.querySelector('a.card-link');
            const title = card.querySelector('h3');
            if (!title || !link) return;
            const t = title.textContent.trim();
            const href = link.getAttribute('href') || '';
            if (!t || t.length < 5) return;
            articles.push({
                title: t,
                link: href.startsWith('http') ? href : '""" + BASE + """' + href,
                description: ''
            });
        });
        return articles.slice(0, 25);
    }""")
