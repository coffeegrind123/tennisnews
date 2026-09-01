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

What the discovery probe CANNOT tell you is whether an instance can actually
read tweets - it only sees the wall in front of them. Three failure modes hide
behind one "challenged" verdict and each is handled here, because here is where
a real browser is looking at the real page:

  * the interstitial never clears        -> a property of the request; one retry,
                                            then carry the accounts onward
  * Cloudflare error 1015                -> a property of the INSTANCE; abandon
                                            it at once
  * nitter answers, and says it has no   -> also the instance, and permanent:
    auth tokens / cannot resolve the        it will not improve with a better
    user / its origin is 504                client, so abandon AND remember

That last case used to be the most expensive thing in the run. nt.vern.cc
renders "Instance has no auth tokens, or is fully rate limited" instantly, but
plain HTTP sees only its 418, scores it "challenged", and the browser then waits
the full 75s challenge budget for content the instance has already said it does
not have. Every verdict reached here is written back through
nitter_instances.record_verification, which is what puts a working instance at
the front of the list next run instead of leaving it to the shuffle.

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


class InstanceUnusable(Exception):
    """The instance answered, and what it answered proves it cannot serve tweets.

    Distinct from RateLimited (which is temporary) and from a failed challenge
    (which is per-request): this one is a property of the instance that no
    client and no retry will change, so it is both abandoned and remembered.
    """


async def _page_blob(page) -> str:
    """title + visible body, lowercased. One round trip, because every check
    below wants the same text and each `evaluate` costs a proxied RTT."""
    state = await page.evaluate("""() => ({
        title: document.title || '',
        body: (document.body ? document.body.innerText : '').slice(0, 400),
    })""")
    return f"{state['title']} {state['body']}".lower()


def _is_rate_limited(blob: str) -> bool:
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

    # Checked BEFORE the challenge wait, not after: an instance that has already
    # rendered its "no auth tokens" page is not going to render a timeline in
    # another 75 seconds, and waiting for it is what pushed CI runs past their
    # step timeout.
    blob = await _page_blob(page)
    if _is_rate_limited(blob):
        raise RateLimited(f"{base} returned Cloudflare 1015 for @{handle}")
    fatal = nitter_instances.fatal_body_reason(blob, handle)
    if fatal:
        raise InstanceUnusable(f"{base}: {fatal}")

    def log(msg):
        print(msg)

    ok = await wait_for_challenge(page, TIMELINE_SELECTOR, timeout_s=timeout_s, log=log)
    if not ok:
        # The error can also arrive late - a challenge clears and what is behind
        # it is the token page. Re-read rather than assuming the first look.
        blob = await _page_blob(page)
        if _is_rate_limited(blob):
            raise RateLimited(f"{base} returned Cloudflare 1015 for @{handle}")
        fatal = nitter_instances.fatal_body_reason(blob, handle)
        if fatal:
            raise InstanceUnusable(f"{base}: {fatal}")
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
        # Tweets THIS instance served. A 1015 after it has already delivered is
        # an instance doing its job and then throttling, which must not be
        # recorded as "cannot serve tweets" - that is the state that would
        # demote a working instance out of the list.
        served_here = 0
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
                if served_here == 0:
                    nitter_instances.record_verification(
                        base, False, "rate limited before serving anything")
                rate_limited = True
                break
            except InstanceUnusable as e:
                # Permanent, and now remembered: next run puts this base behind
                # everything else instead of re-proving it for 75 seconds.
                print(f"    [TWITTER] {e} - permanent, abandoning this instance "
                      f"and remembering it; {len(remaining) - i} account(s) carried over")
                nitter_instances.record_verification(base, False, str(e)[:160],
                                                     permanent=True)
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
                    nitter_instances.record_verification(
                        base, False, "interstitial did not clear in the browser")
                    break
                continue

            all_tweets.extend(_to_records(tweets, account, base))
            done.add(handle)
            served_here += len(tweets)
            print(f"    [TWITTER] @{handle}: {len(tweets)} tweets ({base.split('//')[1]})")
            if served_here == len(tweets):
                # First tweets out of this instance: it is proven, and proof is
                # the thing the probe could never supply. Recorded on the first
                # success rather than at the end of the loop so a later 1015
                # cannot cost us the verdict.
                nitter_instances.record_verification(base, True, tweets=len(tweets))

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
