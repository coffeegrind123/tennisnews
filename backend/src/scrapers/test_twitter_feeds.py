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


if __name__ == "__main__":
    unittest.main(verbosity=2)
