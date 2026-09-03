"""Offline tests for interstitial detection.

Run: python3 -m unittest scrapers.test_cloudflare -v   (from backend/src)

Getting this wrong is not a near miss. `looks_like_challenge` returning False
means "there is no wall here, give up now", so a challenge the browser would
have cleared in ten seconds is abandoned in three - and with it the whole run.

The state dicts below are what the page actually reported in CI on 2026-09-01,
including the Korean one. That page appeared the moment camoufox started using
geoip=True: with a coherent fingerprint Cloudflare serves the interstitial in
the language of the exit IP's country, and the exit rotates per connection, so
"the title says 'Just a moment...'" stopped being true several times an hour.
"""

import unittest

from scrapers.cloudflare import (
    is_browser_gone,
    is_navigation_race,
    looks_like_challenge,
    page_is_dead,
    safe_evaluate,
)


def state(**kw):
    base = {"title": "", "url": "", "len": 0, "body": "", "hasTurnstile": False,
            "hasChallengeForm": False, "hasChallengePlatform": False,
            "hasAnubis": False}
    base.update(kw)
    return base


class ChallengeDetectionTest(unittest.TestCase):
    def test_korean_interstitial_is_a_challenge(self):
        # Verbatim from CI. English title matching called this "no challenge".
        self.assertTrue(looks_like_challenge(
            state(title="잠시만 기다리십시오…", len=26854,
                  body="nitter.freedit.eu 보안 확인 수행 중 이 웹 사이트는 보안 서비스를 사용하여",
                  hasChallengePlatform=True), 0))

    def test_english_interstitial_is_still_a_challenge(self):
        self.assertTrue(looks_like_challenge(
            state(title="Just a moment...", len=27005, hasChallengePlatform=True), 0))

    def test_title_alone_still_works_without_the_markup(self):
        # Belt and braces: an interstitial variant that carries no recognisable
        # markup but does say so in an English title.
        self.assertTrue(looks_like_challenge(state(title="Just a moment..."), 0))

    def test_a_localised_page_with_no_markup_is_not_guessed_at(self):
        # The honest limit of prose matching, and why structure is the
        # authority: nothing here identifies a challenge, so nothing should be
        # claimed. Documents the boundary rather than pretending there is none.
        self.assertFalse(looks_like_challenge(state(title="잠시만 기다리십시오…"), 0))

    def test_anubis_proof_of_work_is_a_challenge(self):
        self.assertTrue(looks_like_challenge(state(hasAnubis=True), 0))

    def test_turnstile_widget_is_a_challenge(self):
        self.assertTrue(looks_like_challenge(state(hasTurnstile=True), 0))

    def test_rendered_content_outranks_every_signal(self):
        # If the timeline is on the page, the challenge is behind us no matter
        # what leftover markup says. Waiting on a page that already has content
        # would burn the budget for nothing.
        self.assertFalse(looks_like_challenge(
            state(title="Just a moment...", hasChallengePlatform=True,
                  hasTurnstile=True), 20))

    def test_an_ordinary_page_is_not_a_challenge(self):
        # The control. Without it every assertion above passes trivially.
        self.assertFalse(looks_like_challenge(
            state(title="José Morgado (@josemorgado) / nitter", len=48000,
                  body="Journalist & tennis commentator"), 0))

    def test_a_nitter_error_page_is_not_a_challenge(self):
        # "No auth tokens" must reach fatal_body_reason, not be mistaken for a
        # wall worth waiting behind.
        self.assertFalse(looks_like_challenge(
            state(title="nitter", body="Instance has no auth tokens"), 0))


class _NavigatingPage:
    """A page that raises the navigation race for its first `fails` evaluates.

    Modelled on the real thing rather than invented: the message is the exact
    string playwright produced in CI on 2026-08-25 and 2026-09-02.
    """

    RACE = ("Page.evaluate: Execution context was destroyed, most likely "
            "because of a navigation")

    def __init__(self, fails=1, result="content", exc=None):
        self.fails = fails
        self.result = result
        self.exc = exc
        self.calls = 0
        self.load_state_waits = 0

    async def evaluate(self, script, *args):
        self.calls += 1
        if self.calls <= self.fails:
            raise (self.exc or RuntimeError(self.RACE))
        return self.result

    async def wait_for_load_state(self, state, timeout=None):
        self.load_state_waits += 1


class NavigationRaceTest(unittest.IsolatedAsyncioTestCase):
    """Cloudflare clearing its own challenge is a NAVIGATION, and a poll in
    flight when it happens dies with the old document. That is what success
    looks like from the inside, and it used to abort the entire Twitter phase:
    2026-09-02 lost all 12 accounts and all 5 instances 9.6s into the first
    profile; 2026-08-25 threw on the re-read one line AFTER the challenge
    finally cleared.
    """

    def test_the_race_is_recognised(self):
        self.assertTrue(is_navigation_race(RuntimeError(_NavigatingPage.RACE)))
        self.assertTrue(is_navigation_race(
            RuntimeError("Cannot find context with specified id")))

    def test_a_real_error_is_not_mistaken_for_it(self):
        # The control. Without it the matcher could return True for everything
        # and every assertion above would still pass.
        self.assertFalse(is_navigation_race(RuntimeError("Target page, context "
                                                         "or browser has been closed")))
        self.assertFalse(is_navigation_race(RuntimeError("Timeout 30000ms exceeded")))

    async def test_a_navigation_is_re_read_not_raised(self):
        page = _NavigatingPage(fails=1, result="timeline")
        self.assertEqual(await safe_evaluate(page, "() => 1", log=lambda m: None),
                         "timeline")
        self.assertEqual(page.calls, 2)
        # Re-reading immediately would race the same navigation again.
        self.assertEqual(page.load_state_waits, 1)

    async def test_arguments_survive_the_retry(self):
        # The selector-count poll and the tweet extractor both pass an argument;
        # dropping it on retry would silently return the wrong thing.
        seen = []

        class P(_NavigatingPage):
            async def evaluate(self, script, *args):
                seen.append(args)
                return await super().evaluate(script, *args)

        page = P(fails=1, result=[{"text": "x"}])
        await safe_evaluate(page, "(max) => max", 5, log=lambda m: None)
        self.assertEqual(seen, [(5,), (5,)])

    async def test_an_unrelated_error_is_re_raised_immediately(self):
        page = _NavigatingPage(fails=1, exc=RuntimeError("Target closed"))
        with self.assertRaises(RuntimeError):
            await safe_evaluate(page, "() => 1", log=lambda m: None)
        self.assertEqual(page.calls, 1)

    async def test_a_page_that_never_settles_still_raises(self):
        # Swallowing this would report an endlessly navigating page as an empty
        # result, which is the failure mode that hides a broken instance.
        page = _NavigatingPage(fails=99)
        with self.assertRaises(RuntimeError):
            await safe_evaluate(page, "() => 1", retries=2, log=lambda m: None)
        self.assertEqual(page.calls, 3)


class BrowserGoneTest(unittest.TestCase):
    """Told apart from a navigation race because the two need OPPOSITE
    responses: a race is retried on the same page, a dead browser must stop the
    caller and blame nothing."""

    def test_the_playwright_wordings_are_recognised(self):
        for msg in ("Page.goto: Target page, context or browser has been closed",
                    "TargetClosedError: Target closed",
                    "Browser has been closed",
                    "Browser has disconnected"):
            self.assertTrue(is_browser_gone(RuntimeError(msg)), msg)

    def test_recoverable_failures_are_not_mistaken_for_it(self):
        # The control, and the important half: if this returned True for a
        # timeout, one slow site would abort the whole run.
        for msg in ("Timeout 30000ms exceeded",
                    "net::ERR_NAME_NOT_RESOLVED",
                    "Execution context was destroyed, most likely because of a "
                    "navigation"):
            self.assertFalse(is_browser_gone(RuntimeError(msg)), msg)

    def test_the_two_readings_never_both_claim_the_same_exception(self):
        for msg in ("Target page, context or browser has been closed",
                    "Execution context was destroyed",
                    "Timeout 30000ms exceeded"):
            e = RuntimeError(msg)
            self.assertFalse(is_browser_gone(e) and is_navigation_race(e), msg)

    def test_page_is_dead_reads_is_closed(self):
        class P:
            def __init__(self, v): self.v = v
            def is_closed(self): return self.v
        self.assertTrue(page_is_dead(P(True)))
        self.assertFalse(page_is_dead(P(False)))

    def test_a_page_without_is_closed_is_assumed_alive(self):
        # Test doubles and older stubs have no is_closed; assuming DEAD there
        # would abort every run that used one.
        self.assertFalse(page_is_dead(object()))

    def test_a_page_whose_is_closed_raises_is_treated_as_dead(self):
        class P:
            def is_closed(self): raise RuntimeError("connection closed")
        self.assertTrue(page_is_dead(P()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
