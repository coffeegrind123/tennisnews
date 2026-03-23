"""US Open - https://www.usopen.org/en_US/news/index.html
JS SPA. Parse articles from visible text. Dates + author in text."""

URL = "https://www.usopen.org/en_US/news/index.html"
BASE = "https://www.usopen.org"

import re


async def scrape(page) -> list[dict]:
    try:
        await page.goto(URL, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(5000)

        try:
            btn = page.locator("button", has_text="Accept All")
            if await btn.count() > 0:
                await btn.first.click()
                await page.wait_for_timeout(2000)
        except Exception:
            pass

        text = await page.evaluate("() => document.body.innerText")
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        articles = []
        seen = set()
        i = 0
        while i < len(lines):
            line = lines[i]
            # Article titles are followed by "By Author\nDay, Month DD\nNEWS"
            # or "Day, Month DD\nNEWS"
            if line == "NEWS" and i >= 2:
                # Walk backwards to find title and date
                date = ""
                author = ""
                title = ""
                # Check previous lines
                prev1 = lines[i - 1] if i - 1 >= 0 else ""
                prev2 = lines[i - 2] if i - 2 >= 0 else ""
                prev3 = lines[i - 3] if i - 3 >= 0 else ""

                # Date pattern: "Monday, March 16" or "Friday, March 13"
                date_pat = r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s"
                if re.match(date_pat, prev1):
                    date = prev1
                    if prev2.startswith("By "):
                        author = prev2
                        title = prev3
                    else:
                        title = prev2
                elif prev1.startswith("By "):
                    author = prev1
                    title = prev2
                else:
                    title = prev1

                if title and len(title) > 10 and title not in seen and title != "NEWS":
                    seen.add(title)
                    desc = author if author else ""
                    articles.append({
                        "title": title,
                        "link": URL,
                        "description": desc,
                        "date": date,
                    })
            i += 1

        return articles[:25]
    except Exception:
        return []
