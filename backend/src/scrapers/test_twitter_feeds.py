"""Offline tests for the Nitter profile loader.

Run: python3 -m unittest scrapers.test_twitter_feeds -v   (from backend/src)

Nothing here touches the network or a browser; `_FakePage` stands in for the
camoufox page. The bug this file exists to prevent is not a logic error anyone
would spot by reading:

  Cloudflare's managed challenge is proof-of-work, and a reload DISCARDS it -
  "Refreshing the page will restart the security verification and may take
  longer", in Cloudflare's own words on the page. The retry path called
  page.goto again, so an attempt that had spent 75 seconds solving the
  challenge was thrown away and restarted with a 25 second budget. The
  instance was then written off as "not clearing" and abandoned for the run.

Measured 2026-09-01: nitter.freedit.eu - at the time the only instance with
working X auth tokens - clears in 60-100s on ONE uninterrupted load, and served
a full timeline the moment it did. Every run for the previous three weeks had
been reloading it out of its own solution.
"""

import unittest

from scrapers import twitter_feeds as tf


class _FakePage:
    """The two calls _load_timeline makes on a page, plus a goto counter."""

    def __init__(self, url="", blob="", tweets=None):
        self.url = url
        self._blob = blob
        self._tweets = tweets if tweets is not None else []
        self.gotos = []

    async def goto(self, url, **kwargs):
        self.gotos.append(url)
        self.url = url

    async def evaluate(self, script, *args):
        if "title:" in script:
            return {"title": "", "body": self._blob}
        return self._tweets

    async def wait_for_timeout(self, ms):
        return None


class ResumeInsteadOfReloadTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._saved = tf.wait_for_challenge

    def tearDown(self):
        tf.wait_for_challenge = self._saved

    def _cleared(self, ok=True):
        async def fake(page, selector, timeout_s=75, log=print):
            return ok
        tf.wait_for_challenge = fake

    async def test_resuming_does_not_reload_the_page(self):
        # THE regression test. A reload here restarts the proof-of-work.
        self._cleared()
        page = _FakePage(url="https://nitter.freedit.eu/josemorgado",
                         tweets=[{"text": "a tweet long enough to keep", "date": "",
                                  "link": "/x/status/1", "is_retweet": False}])
        got = await tf._load_timeline(page, "https://nitter.freedit.eu",
                                      "josemorgado", 60, navigate=False)
        self.assertEqual(page.gotos, [], "the retry must not re-navigate")
        self.assertEqual(len(got), 1)

    async def test_the_first_attempt_does_navigate(self):
        # Control: without this, "no goto" above could just mean goto is broken.
        self._cleared()
        page = _FakePage(tweets=[])
        await tf._load_timeline(page, "https://nitter.freedit.eu", "josemorgado", 60)
        self.assertEqual(page.gotos, ["https://nitter.freedit.eu/josemorgado"])

    async def test_resume_refuses_when_the_browser_is_somewhere_else(self):
        # A goto that failed outright leaves the browser on the PREVIOUS
        # instance's page; resuming there would read that instance's verdict as
        # this one's.
        self._cleared()
        page = _FakePage(url="https://nt.vern.cc/someone-else")
        got = await tf._load_timeline(page, "https://nitter.freedit.eu",
                                      "josemorgado", 60, navigate=False)
        self.assertIsNone(got)
        self.assertEqual(page.gotos, [])

    async def test_a_tokenless_instance_is_fatal_before_the_challenge_wait(self):
        # nt.vern.cc, verbatim. Must raise rather than burn the budget.
        self._cleared(ok=False)
        page = _FakePage(blob="Instance has no auth tokens, or is fully rate limited.")
        with self.assertRaises(tf.InstanceUnusable):
            await tf._load_timeline(page, "https://nt.vern.cc", "josemorgado", 150)

    async def test_a_1015_is_rate_limiting_not_uselessness(self):
        # Different exception, because it needs the opposite response: this
        # instance is working and throttling, not incapable.
        self._cleared(ok=False)
        page = _FakePage(blob="Error 1015 You are being rate limited")
        with self.assertRaises(tf.RateLimited):
            await tf._load_timeline(page, "https://lightbrd.com", "josemorgado", 150)

    async def test_an_ordinary_challenge_is_neither(self):
        # The control for both: a plain interstitial must simply return None so
        # the caller waits longer, not abandon a recoverable instance.
        self._cleared(ok=False)
        page = _FakePage(blob="Just a moment... Performing security verification")
        got = await tf._load_timeline(page, "https://nitter.kareem.one", "josemorgado", 150)
        self.assertIsNone(got)


class BudgetTest(unittest.TestCase):
    def test_the_first_load_gets_longer_than_the_measured_clear_time(self):
        # freedit cleared between 60s and 100s; a budget at or under that is how
        # three weeks of runs missed it by seconds.
        self.assertGreater(tf.CHALLENGE_TIMEOUT_S, 100)

    def test_the_phase_cannot_outlast_the_workflow_step(self):
        # The scrape step is capped at 35 minutes and the article half needs
        # ~13 of them. Being killed there writes NOTHING, articles included.
        self.assertLessEqual(tf.PHASE_BUDGET_S, 20 * 60)


class _ScriptedPage:
    """A page driven by a per-URL script, for the whole-phase tests.

    `script` maps a handle to either a list of raw tweet dicts, or an Exception
    instance to raise from the evaluate that reads the timeline.
    """

    def __init__(self, script, closed_after=None):
        self.url = ""
        self.script = script
        self.gotos = []
        self.closed_after = closed_after
        self._closed = False

    def is_closed(self):
        return self._closed

    async def goto(self, url, **kwargs):
        self.gotos.append(url)
        self.url = url

    async def evaluate(self, script, *args):
        handle = self.url.rsplit("/", 1)[-1]
        if "title:" in script:
            return {"title": "", "body": ""}
        outcome = self.script.get(handle, [])
        if self.closed_after is not None and len(self.gotos) >= self.closed_after:
            self._closed = True
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def wait_for_timeout(self, ms):
        return None

    async def wait_for_load_state(self, state, timeout=None):
        return None


def _tweet(text="a tweet long enough to be kept by the extractor"):
    return [{"text": text, "date": "2026-09-03 10:00", "link": "/x/status/1",
             "is_retweet": False}]


RACE = RuntimeError("Page.evaluate: Execution context was destroyed, most "
                    "likely because of a navigation")


class PhaseSurvivesABrowserErrorTest(unittest.IsolatedAsyncioTestCase):
    """A browser error on ONE profile must cost that profile, not the run.

    Measured in CI twice. 2026-09-02 10:36: the navigation race escaped `scrape`
    9.6 seconds into the first account on nitter.freedit.eu, so the remaining 11
    accounts and the remaining 4 instances were never tried, 0 tweets were
    written, and the run went red on the health gate - while the article half had
    already collected 520 items. 2026-08-25 14:50 was the same escape, thrown on
    the re-read one line after the challenge had finally cleared.
    """

    def setUp(self):
        self._saved_wait = tf.wait_for_challenge
        self._saved_resolve = tf.resolve_bases
        self._saved_record = tf.nitter_instances.record_verification
        self.verdicts = []

        async def cleared(page, selector, timeout_s=75, log=print):
            return True
        tf.wait_for_challenge = cleared
        tf.nitter_instances.record_verification = (
            lambda base, ok, reason="", **kw: self.verdicts.append((base, ok, reason)))
        tf.ACCOUNT_DELAY_MS = 0

    def tearDown(self):
        tf.wait_for_challenge = self._saved_wait
        tf.resolve_bases = self._saved_resolve
        tf.nitter_instances.record_verification = self._saved_record
        tf.ACCOUNT_DELAY_MS = 4000

    def _bases(self, *bases):
        tf.resolve_bases = lambda proxy_url=None: list(bases)

    async def test_one_racing_profile_does_not_lose_the_other_eleven(self):
        self._bases("https://nitter.freedit.eu")
        handles = [a["handle"] for a in tf.ACCOUNTS]
        script = {h: _tweet() for h in handles}
        script[handles[0]] = RACE          # exactly the 2026-09-02 shape
        got = await tf.scrape(_ScriptedPage(script))
        self.assertEqual(len({t["handle"] for t in got}), len(handles) - 1)
        self.assertNotIn(handles[0], {t["handle"] for t in got})

    async def test_a_race_records_no_verdict_against_the_instance(self):
        # A page that navigated mid-read proves nothing about the host. Writing a
        # failure here would demote the only instance that works.
        self._bases("https://nitter.freedit.eu")
        handles = [a["handle"] for a in tf.ACCOUNTS]
        script = {h: _tweet() for h in handles}
        script[handles[0]] = RACE
        await tf.scrape(_ScriptedPage(script))
        self.assertEqual([v for v in self.verdicts if v[1] is False], [])

    async def test_the_challenge_budget_moves_to_the_next_account(self):
        # The account that died mid-navigation never tested the interstitial, so
        # the next one is still the first real attempt: it must get the long
        # budget, not the 25s cookie-riding one. Under the old `i == 0` test it
        # got 25s and the instance was written off.
        self._bases("https://nitter.freedit.eu")
        budgets = []

        async def spy(page, selector, timeout_s=75, log=print):
            budgets.append(timeout_s)
            return True
        tf.wait_for_challenge = spy
        handles = [a["handle"] for a in tf.ACCOUNTS]
        script = {h: _tweet() for h in handles}
        script[handles[0]] = RACE
        await tf.scrape(_ScriptedPage(script))
        self.assertEqual(budgets[0], tf.CHALLENGE_TIMEOUT_S)
        self.assertEqual(budgets[1], tf.CHALLENGE_TIMEOUT_S,
                         "the account after a race is still the first real attempt")
        self.assertEqual(budgets[2], tf.ACCOUNT_TIMEOUT_S)

    async def test_a_racing_instance_still_falls_through_to_the_next_one(self):
        self._bases("https://nitter.freedit.eu", "https://lightbrd.com")
        handles = [a["handle"] for a in tf.ACCOUNTS]
        page = _ScriptedPage({h: RACE for h in handles})

        # Second instance works: rebuild the script once the walk moves on.
        original_goto = page.goto

        async def goto(url, **kwargs):
            if "lightbrd.com" in url:
                page.script = {h: _tweet() for h in handles}
            await original_goto(url, **kwargs)
        page.goto = goto

        got = await tf.scrape(page)
        self.assertEqual(len({t["handle"] for t in got}), len(handles))
        self.assertTrue(all("lightbrd.com" in t["link"] for t in got))

    async def test_a_closed_page_keeps_what_was_already_collected(self):
        # The one case where continuing is pointless: every later account would
        # raise the same thing. Stop, but return the tweets in hand rather than
        # throwing them away.
        self._bases("https://nitter.freedit.eu", "https://lightbrd.com")
        handles = [a["handle"] for a in tf.ACCOUNTS]
        script = {h: _tweet() for h in handles}
        script[handles[2]] = RACE
        page = _ScriptedPage(script, closed_after=3)
        got = await tf.scrape(page)
        self.assertEqual(len(got), 2)
        self.assertEqual(len(page.gotos), 3, "no further profiles after the page died")

    async def test_every_profile_racing_is_still_a_failure(self):
        # The control. If the guard swallowed everything, a totally broken phase
        # would report success with zero tweets and the health gate would go
        # green on an empty feed.
        self._bases("https://nitter.freedit.eu")
        with self.assertRaises(RuntimeError):
            await tf.scrape(_ScriptedPage({a["handle"]: RACE for a in tf.ACCOUNTS}))


class DeadBrowserBlamesNobodyTest(unittest.IsolatedAsyncioTestCase):
    """A crash in the ARTICLE half must not be recorded as a Nitter failure.

    Run 33784201641, 2026-09-03 17:42: the browser died at site 18 of 21
    (asiantennis.com). The Twitter phase then walked all six instances in 50
    milliseconds - every goto raised TargetClosedError, every one was swallowed
    as "no timeline rendered", and every host got a permanent "interstitial did
    not clear" verdict written to data/nitter_verified.json. Two of the six were
    lightbrd.com and nitter.freedit.eu, the only hosts that serve tweets.

    One crash, six false verdicts, and the verdicts outlive the run.
    """

    TARGET_CLOSED = "Page.goto: Target page, context or browser has been closed"

    def setUp(self):
        self._saved_wait = tf.wait_for_challenge
        self._saved_resolve = tf.resolve_bases
        self._saved_record = tf.nitter_instances.record_verification
        self.verdicts = []

        async def cleared(page, selector, timeout_s=75, log=print):
            return True
        tf.wait_for_challenge = cleared
        tf.nitter_instances.record_verification = (
            lambda base, ok, reason="", **kw: self.verdicts.append((base, ok, reason)))
        tf.resolve_bases = lambda proxy_url=None: [
            "https://lightbrd.com", "https://nitter.freedit.eu",
            "https://nt.vern.cc", "https://nuku.trabun.org"]
        tf.ACCOUNT_DELAY_MS = 0

    def tearDown(self):
        tf.wait_for_challenge = self._saved_wait
        tf.resolve_bases = self._saved_resolve
        tf.nitter_instances.record_verification = self._saved_record
        tf.ACCOUNT_DELAY_MS = 4000

    def _dead_page(self, closed=True, after=0):
        test = self

        class DeadPage(_ScriptedPage):
            def __init__(self):
                super().__init__({})
                self._n = 0

            def is_closed(self):
                return closed and self._n >= after

            async def goto(self, url, **kwargs):
                self._n += 1
                if self._n > after:
                    raise RuntimeError(test.TARGET_CLOSED)
                self.gotos.append(url)
                self.url = url
        return DeadPage()

    async def test_a_page_dead_before_the_phase_raises_without_touching_an_instance(self):
        page = self._dead_page()
        with self.assertRaises(RuntimeError):
            await tf.scrape(page)
        self.assertEqual(self.verdicts, [], "no host may be blamed for a dead browser")
        self.assertEqual(page.gotos, [], "a corpse must not be walked round six hosts")

    async def test_a_browser_that_dies_mid_phase_blames_no_instance(self):
        # Alive for the first profile, dead from the second on.
        handles = [a["handle"] for a in tf.ACCOUNTS]
        page = self._dead_page(after=1)
        page.script = {h: _tweet() for h in handles}
        got = await tf.scrape(page)
        self.assertEqual(len(got), 1, "the tweets collected before the crash are kept")
        self.assertEqual([v for v in self.verdicts if v[1] is False], [],
                         "a crash is not evidence against any host")

    async def test_the_good_verdict_earned_before_the_crash_survives(self):
        # The control for the assertion above: verdicts are not simply disabled.
        handles = [a["handle"] for a in tf.ACCOUNTS]
        page = self._dead_page(after=1)
        page.script = {h: _tweet() for h in handles}
        await tf.scrape(page)
        self.assertEqual([v for v in self.verdicts if v[1] is True][0][0],
                         "https://lightbrd.com")

    async def test_target_closed_is_told_apart_from_an_ordinary_goto_failure(self):
        # The control that keeps the detector honest: a DNS failure is still a
        # per-request failure and must still cost the instance its verdict.
        handles = [a["handle"] for a in tf.ACCOUNTS]

        class DnsFailPage(_ScriptedPage):
            async def goto(self, url, **kwargs):
                raise RuntimeError("net::ERR_NAME_NOT_RESOLVED")

        page = DnsFailPage({h: _tweet() for h in handles})
        with self.assertRaises(RuntimeError):
            await tf.scrape(page)
        self.assertTrue([v for v in self.verdicts if v[1] is False],
                        "a real per-request failure must still be recorded")


if __name__ == "__main__":
    unittest.main(verbosity=2)
