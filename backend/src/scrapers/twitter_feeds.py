"""Twitter/X tennis feed scraper via Nitter.

Most instances sit behind a Cloudflare managed challenge or an Anubis
proof-of-work wall. lightbrd.com is the reference case: the FF152 camoufox build
clears its challenge, FF146 could not.

Instances are walked in order and accounts are carried between them: whatever an
instance cannot serve is retried on the next one, so a partial failure costs
those profiles rather than the whole feed. Two distinct failure modes are handled
separately because they need opposite responses:

  * interstitial not cleared -> a property of that request; try the next account
  * Cloudflare error 1015    -> a property of the INSTANCE; abandon it at once
                                and carry the remaining accounts elsewhere

That second case is not hypothetical. Clearing lightbrd's challenge is what
exposed it: lightbrd serves roughly three profiles then rate limits, so the run
that finally "won" the challenge collected FEWER tweets (15) than one that fell
back to an unchallenged instance (55). Requests are paced to stay under that
limit rather than sprinting into it.

The instance list is no longer hardcoded. scrapers/nitter_instances.py pulls
candidates from public registries, probes each one over plain HTTP, and returns
only those that answered - best tier first, shuffled within a tier. That
shuffling is load bearing here rather than cosmetic: instances rate limit per
client after a few profile loads, so a fixed order means one host absorbs every
run and hits its 1015 at the same account every time.

Override the instance order with NITTER_BASES (comma separated), which bypasses
discovery entirely; see nitter_instances for the rest of the knobs.
"""

import os

from scrapers import nitter_instances
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

DEFAULT_BASES = nitter_instances.DEFAULT_BASES

# The account used to decide whether an instance is usable at all. High volume
# and long lived, so an empty timeline here means the instance is broken rather
# than the account being quiet.
PROBE_HANDLE = nitter_instances.PROBE_HANDLE


def resolve_bases(proxy_url: str | None = None) -> list[str]:
    """Instances to walk this run, best first.

    Discovery is resolved per run rather than at import so the list reflects the
    network as it is now, and so a discovery failure degrades to DEFAULT_BASES
    instead of blowing up an import. NITTER_BASES still short-circuits the whole
    thing, which is what the CI debug path uses.
    """
    try:
        return nitter_instances.discover(proxy_url)
    except Exception as e:
        print(f"    [TWITTER] instance discovery failed ({type(e).__name__}: "
              f"{str(e)[:120]}) - falling back to the built-in list")
        return list(DEFAULT_BASES)


TIMELINE_SELECTOR = ".timeline-item"
MAX_TWEETS_PER_ACCOUNT = 5

# First page load on a challenged instance has to run the interstitial JS.
CHALLENGE_TIMEOUT_S = int(os.environ.get("NITTER_CHALLENGE_TIMEOUT", "75"))
# Subsequent loads ride the clearance cookie and should be quick; a long wait
# here just multiplies across 14 accounts.
ACCOUNT_TIMEOUT_S = int(os.environ.get("NITTER_ACCOUNT_TIMEOUT", "25"))
# Pause between profile loads. lightbrd starts returning Cloudflare 1015 after
# roughly three back-to-back requests, so pacing is what keeps an instance alive.
ACCOUNT_DELAY_MS = int(os.environ.get("NITTER_ACCOUNT_DELAY_MS", "4000"))

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


class RateLimited(Exception):
    """The instance served Cloudflare error 1015 (or equivalent) for this request."""


async def _is_rate_limited(page) -> bool:
    state = await page.evaluate("""() => ({
        title: document.title || '',
        body: (document.body ? document.body.innerText : '').slice(0, 300),
    })""")
    blob = f"{state['title']} {state['body']}".lower()
    return "error 1015" in blob or "you are being rate limited" in blob


async def _load_timeline(page, base: str, handle: str, timeout_s: int) -> list[dict] | None:
    """Load one profile. Returns the raw tweet dicts, or None if the page never
    got past its interstitial / never rendered a timeline.

    Raises RateLimited when the instance is throttling us, which is a property of
    the INSTANCE rather than the account and so must abort the whole instance
    instead of being retried per handle.
    """
    url = f"{base}/{handle}"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        print(f"    [TWITTER] {url}: goto failed - {type(e).__name__}: {str(e)[:110]}")
        return None

    if await _is_rate_limited(page):
        raise RateLimited(f"{base} returned Cloudflare 1015 for @{handle}")

    def log(msg):
        print(msg)

    ok = await wait_for_challenge(page, TIMELINE_SELECTOR, timeout_s=timeout_s, log=log)
    if not ok:
        if await _is_rate_limited(page):
            raise RateLimited(f"{base} returned Cloudflare 1015 for @{handle}")
        return None
    return await page.evaluate(EXTRACT_JS, MAX_TWEETS_PER_ACCOUNT)






def _to_records(tweets, account, base):
    out = []
    for t in tweets:
        handle = account["handle"]
        link = f"{base}{t['link']}" if t["link"] else f"https://x.com/{handle}"
        out.append({
            "title": t["text"],
            "description": "",
            "link": link,
            "handle": handle,
            "author": account["name"],
            "outlet": account["outlet"],
            "date": t["date"],
            "is_retweet": t.get("is_retweet", False),
        })
    return out


async def scrape(page, proxy_url: str | None = None) -> list[dict]:
    all_tweets = []
    done = set()
    tried_instances = []
    bases = resolve_bases(proxy_url)

    # Instances are tried in order, and an instance that starts rate limiting is
    # abandoned mid-run with the REMAINING accounts carried to the next one.
    # Clearing lightbrd's Cloudflare challenge is what exposed this: it serves
    # about three profiles then returns error 1015 for the rest, so a run that
    # "won" the challenge collected fewer tweets (15) than one that fell back to
    # an unchallenged instance (55).
    for base in bases:
        remaining = [a for a in ACCOUNTS if a["handle"] not in done]
        if not remaining:
            break
        tried_instances.append(base)
        print(f"    [TWITTER] instance {base}: {len(remaining)} account(s) to fetch")

        rate_limited = False
        for i, account in enumerate(remaining):
            handle = account["handle"]
            # The FIRST load on an instance has to run the interstitial JS and needs
            # the full challenge budget; later loads ride the clearance cookie and
            # only need the short one. Giving every load the short budget silently
            # demoted lightbrd in CI: all 12 accounts reported "no timeline
            # rendered" at ~27s each because clearing took longer than 25s over the
            # proxy, even though it clears in 12-15s direct.
            budget = CHALLENGE_TIMEOUT_S if i == 0 else ACCOUNT_TIMEOUT_S
            try:
                tweets = await _load_timeline(page, base, handle, budget)
                # The first load is the one that PAYS for the interstitial, and the
                # challenge often clears only as that attempt expires - so account 1
                # reports nothing while every later account succeeds. Retry it once,
                # now that the clearance cookie exists, instead of exporting it to a
                # fallback instance.
                if tweets is None and i == 0:
                    print(f"    [TWITTER] @{handle}: retrying now the challenge has cleared")
                    tweets = await _load_timeline(page, base, handle, ACCOUNT_TIMEOUT_S)
            except RateLimited as e:
                print(f"    [TWITTER] {e} - abandoning this instance, "
                      f"{len(remaining) - i} account(s) carried over")
                rate_limited = True
                break

            if tweets is None:
                print(f"    [TWITTER] @{handle}: no timeline rendered")
                # If the FIRST account cannot be served even after its retry, this
                # instance's interstitial is not clearing for us at all, and the
                # remaining accounts will each burn a full timeout proving the same
                # thing. In CI that cost 6.7 minutes on lightbrd - 11 further
                # failures at ~27s each - and pushed the whole run past its step
                # timeout. One proven failure is enough; carry everything over.
                if i == 0:
                    print(f"    [TWITTER] {base}: first account failed after retry - "
                          f"instance is not clearing, carrying all "
                          f"{len(remaining)} account(s) to the next instance")
                    break
                continue

            all_tweets.extend(_to_records(tweets, account, base))
            done.add(handle)
            print(f"    [TWITTER] @{handle}: {len(tweets)} tweets ({base.split('//')[1]})")

            # Pace requests: hammering 12 profiles back to back is what triggers
            # the 1015 in the first place.
            if i < len(remaining) - 1:
                await page.wait_for_timeout(ACCOUNT_DELAY_MS)

        if not rate_limited and len(done) == len(ACCOUNTS):
            break

    missing = [a["handle"] for a in ACCOUNTS if a["handle"] not in done]
    if missing:
        print(f"    [TWITTER] {len(missing)}/{len(ACCOUNTS)} accounts returned nothing: "
              f"{', '.join(missing)}")
    if not all_tweets:
        raise RuntimeError(
            f"no tweets from any instance (tried {tried_instances}) - every one "
            f"failed its interstitial, rate limited us, or served empty timelines"
        )
    print(f"    [TWITTER] instances used={tried_instances} total={len(all_tweets)} "
          f"accounts={len(done)}/{len(ACCOUNTS)}")
    return all_tweets
