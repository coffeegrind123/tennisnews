"""Anti-bot interstitial handling for camoufox pages.

Covers the two walls Nitter instances actually sit behind:

  * Cloudflare "Just a moment..." managed challenge / Turnstile
  * the Anubis-style JS proof-of-work pages ("Making sure you're not a bot!",
    "Verifying your browser")

Both are *non-interactive most of the time*: a browser with a plausible
fingerprint solves them by simply being left alone long enough to run the JS.
So the strategy is poll-for-clear first, and only reach for a Turnstile
checkbox click if a checkbox actually materialises.

Everything here logs the raw observation (title, html length, body text) rather
than just a boolean, because "did not clear" and "cleared but the page is empty"
look identical from the outside and need completely different fixes.
"""

CHALLENGE_TITLES = (
    "just a moment",
    "making sure you're not a bot",
    "verifying your browser",
    "attention required",
    "checking your browser",
    "please wait",
    "ddos-guard",
)

CHALLENGE_JS = """() => {
    const title = document.title || '';
    const body = document.body ? document.body.innerText : '';
    return {
        title: title,
        url: location.href,
        len: document.documentElement.outerHTML.length,
        body: body.replace(/\\s+/g, ' ').slice(0, 200),
        hasTurnstile: !!document.querySelector('iframe[src*="challenges.cloudflare.com"], .cf-turnstile, #challenge-stage'),
        hasChallengeForm: !!document.querySelector('#challenge-form, #challenge-running, #cf-challenge-running'),
    };
}"""


def looks_like_challenge(state: dict, ready_selector_count: int) -> bool:
    """A page is still challenged if the real content never appeared AND it
    either says so in the title or is still showing a Turnstile widget."""
    if ready_selector_count > 0:
        return False
    title = (state.get("title") or "").lower()
    if any(t in title for t in CHALLENGE_TITLES):
        return True
    return bool(state.get("hasTurnstile") or state.get("hasChallengeForm"))


async def _try_turnstile_click(page, log) -> bool:
    """Click the Turnstile checkbox if one is actually rendered.

    The widget lives in a cross-origin iframe; the checkbox is only clickable
    once it has painted, and the iframe re-renders mid-solve which invalidates
    element handles. So this is best-effort and always safe to call again.
    """
    for frame in page.frames:
        if "challenges.cloudflare.com" not in (frame.url or ""):
            continue
        for sel in ("input[type=checkbox]", "#challenge-stage input", "label"):
            try:
                loc = frame.locator(sel)
                if await loc.count() == 0:
                    continue
                await loc.first.click(timeout=5000)
                log("      clicked turnstile checkbox")
                return True
            except Exception:
                continue
    return False


async def wait_for_challenge(page, ready_selector: str, timeout_s: int = 75,
                             poll_s: float = 3.0, log=print) -> bool:
    """Wait until `ready_selector` appears, solving an interstitial if present.

    Returns True if the real content rendered, False otherwise. On failure the
    caller gets a specific, logged reason rather than a bare False.
    """
    waited = 0.0
    clicked = False
    last = {}

    while waited < timeout_s:
        count = await page.evaluate(
            "(sel) => document.querySelectorAll(sel).length", ready_selector
        )
        if count > 0:
            if waited:
                log(f"      cleared after {waited:.0f}s ({count} x {ready_selector})")
            return True

        last = await page.evaluate(CHALLENGE_JS)
        if not looks_like_challenge(last, count):
            # No content and no challenge either: an error page, an empty
            # profile, or a layout we do not recognise. Say which.
            log(f"      no challenge but no content: title={last['title']!r} "
                f"len={last['len']} body={last['body'][:120]!r}")
            return False

        # Turnstile widgets need one click; managed challenges need none.
        if last.get("hasTurnstile") and not clicked and waited >= 6:
            clicked = await _try_turnstile_click(page, log)

        await page.wait_for_timeout(int(poll_s * 1000))
        waited += poll_s

    log(f"      STILL CHALLENGED after {timeout_s}s: title={last.get('title')!r} "
        f"len={last.get('len')} turnstile={last.get('hasTurnstile')} "
        f"body={str(last.get('body'))[:140]!r}")
    return False


async def wait_until_cleared(page, timeout_s: int = 75, poll_s: float = 3.0,
                             log=print) -> bool:
    """Wait for an interstitial to clear WITHOUT knowing the site's markup.

    `wait_for_challenge` needs a ready selector, which only works where the
    caller knows what the real page looks like. This is the generic path: it
    polls until the page stops *looking* like an interstitial, so a scraper that
    came back empty behind a challenge can simply be re-run afterwards.

    The clearance cookie lives on the browser context, so a module re-navigating
    on its own carries it - which is why re-running the module is enough and no
    per-site wiring is required.
    """
    waited = 0.0
    clicked = False
    last: dict = {}

    while waited < timeout_s:
        last = await page.evaluate(CHALLENGE_JS)
        if not looks_like_challenge(last, 0):
            log(f"      challenge cleared after {waited:.0f}s "
                f"(title now {last.get('title','')[:40]!r})")
            return True
        if last.get("hasTurnstile") and not clicked and waited >= 6:
            clicked = await _try_turnstile_click(page, log)
        await page.wait_for_timeout(int(poll_s * 1000))
        waited += poll_s

    log(f"      STILL CHALLENGED after {timeout_s}s: title={last.get('title')!r} "
        f"turnstile={last.get('hasTurnstile')}")
    return False
