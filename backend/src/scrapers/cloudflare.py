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

# Prose, and therefore ONLY a hint. Cloudflare serves the interstitial in the
# language of the exit IP's country, so the moment the browser started using
# geoip=True (which is what finally let it clear a challenge at all) these
# stopped matching: a Korean exit returns "잠시만 기다리십시오…", and the
# detector reported "no challenge" and abandoned in 3.7s a challenge that
# clears in ten seconds. With a rotating residential exit the same page also
# arrives in French, Portuguese and Indonesian. Structural detection below is
# the authority; this list only helps when it happens to be in English.
CHALLENGE_TITLES = (
    "just a moment",
    "making sure you're not a bot",
    "verifying your browser",
    "attention required",
    "checking your browser",
    "please wait",
    "ddos-guard",
)

# Playwright raises "Execution context was destroyed, most likely because of a
# navigation" the instant the page navigates out from under an in-flight
# evaluate. On an interstitial that is not an error - it is what SUCCESS looks
# like: Cloudflare redirects to the real page the moment the proof-of-work
# lands, and whichever poll was in flight dies with it. The exception used to
# escape the whole Twitter phase. Measured twice in CI: 2026-08-25 (nitter.poast
# .org, thrown on the re-read one line after the challenge finally cleared) and
# 2026-09-02 (nitter.freedit.eu, 9.6s into the FIRST account) - both times it
# discarded every remaining account AND every remaining instance and turned the
# run red, having collected nothing.
NAVIGATION_RACE_MARKERS = (
    "execution context was destroyed",
    "most likely because of a navigation",
    "cannot find context with specified id",
    "because of a navigation",
    "frame was detached",
    "navigating and changing the document",
)


def is_navigation_race(exc: BaseException) -> bool:
    """True when this exception means "the page moved", not "the page is dead".

    Deliberately matched on the message rather than the exception class: the
    camoufox fork ships its own playwright build, and a class import that
    resolves to a DIFFERENT playwright than the one raising would silently
    match nothing - failing exactly like the bug this guards against.
    """
    msg = str(exc).lower()
    return any(m in msg for m in NAVIGATION_RACE_MARKERS)


async def safe_evaluate(page, script, *args, retries: int = 2, log=print):
    """page.evaluate that survives the document being replaced under it.

    Re-runs the script against the new document after waiting for it to reach
    domcontentloaded. Anything that is not a navigation race is re-raised
    untouched, and so is a race that outlives `retries` - a page that keeps
    navigating is a real failure and must not be silently reported as an empty
    result.
    """
    for attempt in range(retries + 1):
        try:
            return await page.evaluate(script, *args) if args else await page.evaluate(script)
        except Exception as e:
            if attempt >= retries or not is_navigation_race(e):
                raise
            log(f"      page navigated mid-evaluate ({str(e)[:80]}) - "
                f"re-reading the new document (attempt {attempt + 2}/{retries + 1})")
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=20000)
            except Exception:
                pass


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
        // Language-independent, because the markup is the same in every locale.
        // _cf_chl_opt is the challenge runtime's own options object and the
        // script it loads always comes from /cdn-cgi/challenge-platform/.
        hasChallengePlatform: !!(window._cf_chl_opt
            || document.querySelector('script[src*="/cdn-cgi/challenge-platform/"]')
            || document.querySelector('#challenge-error-text, #challenge-body-text, #cf-please-wait')),
        // Anubis proof-of-work, the other wall these instances use.
        hasAnubis: !!(window.anubis
            || document.querySelector('script[src*="anubis"], #anubis_challenge, img[alt*="Anubis"]')),
    };
}"""


def looks_like_challenge(state: dict, ready_selector_count: int) -> bool:
    """A page is still challenged if the real content never appeared AND the
    page still carries challenge machinery.

    Structure first, prose second. Reading the title was enough only while every
    challenge arrived in English; it is markup that identifies a challenge in
    any locale, and getting this wrong costs the whole run - "not a challenge"
    means give up immediately, on a page that would have cleared.
    """
    if ready_selector_count > 0:
        return False
    if state.get("hasChallengePlatform") or state.get("hasAnubis"):
        return True
    if state.get("hasTurnstile") or state.get("hasChallengeForm"):
        return True
    title = (state.get("title") or "").lower()
    return any(t in title for t in CHALLENGE_TITLES)


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
        count = await safe_evaluate(
            page, "(sel) => document.querySelectorAll(sel).length", ready_selector,
            log=log,
        )
        if count > 0:
            if waited:
                log(f"      cleared after {waited:.0f}s ({count} x {ready_selector})")
            return True

        last = await safe_evaluate(page, CHALLENGE_JS, log=log)
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
        last = await safe_evaluate(page, CHALLENGE_JS, log=log)
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
