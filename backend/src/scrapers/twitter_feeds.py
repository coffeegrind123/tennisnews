"""Twitter/X tennis feed scraper via xcancel.com proxy.
Scrapes recent tweets from curated tennis-focused accounts."""

ACCOUNTS = [
    {"handle": "moormangirl", "name": "Gale Moorman", "outlet": "Tennis World USA"},
    {"handle": "amylundydahl", "name": "Amy Lundy", "outlet": "Tennis Connected"},
    {"handle": "perfecttennisuk", "name": "Perfect Tennis", "outlet": "Perfect Tennis"},
    {"handle": "djokernole", "name": "Novak Djokovic", "outlet": "Official"},
    {"handle": "jelenadjokovic", "name": "Jelena Djokovic", "outlet": "Djokovic family"},
    {"handle": "tomtebbutt", "name": "Tom Tebbutt", "outlet": "Tennis Canada"},
    {"handle": "tennispublisher", "name": "Randy Walker", "outlet": "World Tennis Magazine"},
    {"handle": "blairhenley", "name": "Blair Henley", "outlet": "World Tennis Magazine"},
    {"handle": "tennisviewmag", "name": "Tennis View Mag", "outlet": "Tennis View Magazine"},
    {"handle": "theslicetennis", "name": "The Slice Tennis", "outlet": "The Slice"},
    {"handle": "mattyat", "name": "Matt Trollope", "outlet": "Tennis Australia"},
    {"handle": "viv_christie", "name": "Vivienne Christie", "outlet": "Tennis Australia"},
]

BASE = "https://xcancel.com"


async def scrape(page) -> list[dict]:
    all_tweets = []

    for account in ACCOUNTS:
        handle = account["handle"]
        display = account["name"]
        url = f"{BASE}/{handle}"

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(3000)

            tweets = await page.evaluate("""(function() {
                var tweets = [];
                var items = document.querySelectorAll('.timeline-item');
                for (var i = 0; i < Math.min(items.length, 5); i++) {
                    var content = items[i].querySelector('.tweet-content');
                    var dateEl = items[i].querySelector('.tweet-date a');
                    var linkEl = items[i].querySelector('.tweet-link');
                    if (!content) continue;
                    var text = content.textContent.trim();
                    if (!text || text.length < 10) continue;
                    var date = dateEl ? dateEl.textContent.trim() : '';
                    var link = linkEl ? linkEl.getAttribute('href') : '';
                    tweets.push({text: text.substring(0, 500), date: date, link: link});
                }
                return tweets;
            })()""")

            for t in tweets:
                tweet_link = f"https://x.com/{handle}/status/" if not t["link"] else f"{BASE}{t['link']}"
                all_tweets.append({
                    "title": t["text"],
                    "description": "",
                    "link": tweet_link,
                    "handle": handle,
                    "author": display,
                    "outlet": account["outlet"],
                    "date": t["date"],
                })

            print(f"    [TWITTER] @{handle}: {len(tweets)} tweets")
        except Exception as e:
            print(f"    [TWITTER] @{handle}: ERROR - {e}")

    return all_tweets
