"""Twitter/X tennis feed scraper via Nitter.

Primary instance is lightbrd.com. It sits behind a Cloudflare managed challenge,
so the instance is health-checked once (paying the interstitial cost a single
time -- the clearance cookie then covers every account in the same context) and
only if it cannot be cleared do we fall back to another instance.

The fallbacks are not a "simpler alternative" to lightbrd: Nitter instances die,
get rate limited, and turn their anti-bot settings up without warning, and a
feed that silently drops to zero tweets is exactly the failure mode this repo
already suffered for months. Instance choice is reported in the output so it is
always visible which one served the data.

Override the instance order with NITTER_BASES (comma separated).
"""

import os

from scrapers.cloudflare import wait_for_challenge

# Removed 2026-08-01: @moormangirl (dormant, newest tweet April 2025) and
# @viv_christie (profile renders but serves no timeline - protected or empty).
# Both cost a page load per run and contributed nothing.
ACCOUNTS = [
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
    {"handle": "josemorgado", "name": "José Morgado", "outlet": "Record Portugal / SportTV"},
    {"handle": "MichalSamulski", "name": "Michal Samulski", "outlet": "ITWA / Tennis Hall of Fame"},
]

DEFAULT_BASES = [
    "https://lightbrd.com",
    "https://nitter.privacyredirect.com",
    "https://nitter.tiekoetter.com",
    "https://nitter.poast.org",
    "https://nitter.net",
]

BASES = [b.strip().rstrip("/") for b in os.environ.get("NITTER_BASES", "").split(",") if b.strip()] \
    or DEFAULT_BASES

# The account used to decide whether an instance is usable at all. High volume
# and long lived, so an empty timeline here means the instance is broken rather
# than the account being quiet.
PROBE_HANDLE = "josemorgado"

TIMELINE_SELECTOR = ".timeline-item"
MAX_TWEETS_PER_ACCOUNT = 5

# First page load on a challenged instance has to run the interstitial JS.
CHALLENGE_TIMEOUT_S = int(os.environ.get("NITTER_CHALLENGE_TIMEOUT", "75"))
# Subsequent loads ride the clearance cookie and should be quick; a long wait
# here just multiplies across 14 accounts.
ACCOUNT_TIMEOUT_S = int(os.environ.get("NITTER_ACCOUNT_TIMEOUT", "25"))

EXTRACT_JS = """(max) => {
    var out = [];
    var items = document.querySelectorAll('.timeline-item');
    for (var i = 0; i < items.length && out.length < max; i++) {
        var item = items[i];
        if (item.querySelector('.unavailable-box')) continue;
        var content = item.querySelector('.tweet-content');
        if (!content) continue;
        var text = content.textContent.trim();
        if (!text || text.length < 10) continue;
        var dateEl = item.querySelector('.tweet-date a');
        var linkEl = item.querySelector('.tweet-link');
        var retweet = item.querySelector('.retweet-header');
        out.push({
            text: text.substring(0, 500),
            date: dateEl ? (dateEl.getAttribute('title') || dateEl.textContent.trim()) : '',
            link: linkEl ? linkEl.getAttribute('href') : '',
            is_retweet: !!retweet
        });
    }
    return out;
}"""


async def _load_timeline(page, base: str, handle: str, timeout_s: int) -> list[dict] | None:
    """Load one profile. Returns the raw tweet dicts, or None if the page never
    got past its interstitial / never rendered a timeline."""
    url = f"{base}/{handle}"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        print(f"    [TWITTER] {url}: goto failed - {type(e).__name__}: {str(e)[:110]}")
        return None

    def log(msg):
        print(msg)

    ok = await wait_for_challenge(page, TIMELINE_SELECTOR, timeout_s=timeout_s, log=log)
    if not ok:
        return None
    return await page.evaluate(EXTRACT_JS, MAX_TWEETS_PER_ACCOUNT)


async def _pick_instance(page) -> str | None:
    """Return the first instance that actually serves a timeline."""
    for base in BASES:
        print(f"    [TWITTER] probing instance {base} ...")
        tweets = await _load_timeline(page, base, PROBE_HANDLE, CHALLENGE_TIMEOUT_S)
        if tweets:
            print(f"    [TWITTER] using {base} ({len(tweets)} tweets on probe)")
            return base
        print(f"    [TWITTER] {base} unusable, trying next")
    return None


async def scrape(page) -> list[dict]:
    base = await _pick_instance(page)
    if not base:
        raise RuntimeError(
            f"no usable Nitter instance among {BASES} - every one failed its "
            f"interstitial or served an empty timeline"
        )

    all_tweets = []
    failed = []

    for account in ACCOUNTS:
        handle = account["handle"]
        tweets = await _load_timeline(page, base, handle, ACCOUNT_TIMEOUT_S)

        if tweets is None:
            failed.append(handle)
            print(f"    [TWITTER] @{handle}: no timeline rendered")
            continue

        for t in tweets:
            link = f"{base}{t['link']}" if t["link"] else f"https://x.com/{handle}"
            all_tweets.append({
                "title": t["text"],
                "description": "",
                "link": link,
                "handle": handle,
                "author": account["name"],
                "outlet": account["outlet"],
                "date": t["date"],
                "is_retweet": t.get("is_retweet", False),
            })
        print(f"    [TWITTER] @{handle}: {len(tweets)} tweets")

    if failed:
        print(f"    [TWITTER] {len(failed)}/{len(ACCOUNTS)} accounts returned nothing: "
              f"{', '.join(failed)}")
    print(f"    [TWITTER] instance={base} total={len(all_tweets)}")
    return all_tweets
