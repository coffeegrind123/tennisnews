"""Wimbledon - https://www.wimbledon.com/en_GB/news/index.html
JS SPA. No desc available. Dates in text near articles (e.g. "MON 02 MAR 2026")."""

URL = "https://www.wimbledon.com/en_GB/news/index.html"
BASE = "https://www.wimbledon.com"


async def scrape(page) -> list[dict]:
    await page.goto(URL, wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(5000)

    # Parse from visible text - Wimbledon renders as: TYPE\nDATE\nTitle
    text = await page.evaluate("() => document.body.innerText")
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    articles = []
    seen = set()
    i = 0
    while i < len(lines) - 1:
        line = lines[i]
        # Look for NEWS/FEATURE/FOUNDATION type markers followed by date
        if line in ("NEWS", "FEATURE", "FOUNDATION"):
            date = ""
            title = ""
            # Next line should be date
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                # Date patterns: "2 DAYS AGO", "MON 02 MAR 2026", "FRI 13 FEB 202611:20 GMT"
                import re
                if re.match(r"(\d+ DAYS? AGO|[A-Z]{3} \d{1,2} [A-Z]{3} \d{4})", next_line):
                    date = next_line.split("GMT")[0].strip()
                    if i + 2 < len(lines):
                        title = lines[i + 2]
                        i += 3
                    else:
                        i += 2
                else:
                    title = next_line
                    i += 2

            if title and len(title) > 10 and title not in seen:
                seen.add(title)
                articles.append({
                    "title": title,
                    "link": URL,
                    "description": "",
                    "date": date,
                })
        else:
            i += 1

    return articles[:25]
