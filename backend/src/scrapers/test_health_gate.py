"""Offline tests for the exit-code gate in scraper.report_health.

Run: python3 -m unittest scrapers.test_health_gate -v   (from backend/src)

The gate has to hold two opposite lines at once, and the whole file is about
where the boundary sits:

  * a run that quietly collects nothing must FAIL, because reporting that as
    success is what let the browser half rot undetected for months;
  * a single zero-tweet run must NOT fail, because as of late August 2026 the
    Nitter ecosystem is being shut down by X Corp cease-and-desist letters and
    the two surviving instances are individually flaky. Red-lining an otherwise
    perfect 330-article run on one flaky instance trains everyone to ignore the
    red.

So the Twitter half is graded on a streak, and the streak lives in the
data/health.json that CI commits every run.
"""

import json
import tempfile
import unittest
from pathlib import Path

import scraper


class HealthGateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._saved_dir = scraper.DATA_DIR
        scraper.DATA_DIR = Path(self._tmp.name)
        self._saved_health = json.loads(json.dumps(scraper.HEALTH))
        scraper.HEALTH.update({
            "browser_ok": True,
            "browser_error": "",
            "sources": {"A Site": {"count": 5, "error": ""}},
            "twitter": {"tweets": 60, "accounts": 12, "error": ""},
        })

    def tearDown(self):
        scraper.DATA_DIR = self._saved_dir
        scraper.HEALTH.clear()
        scraper.HEALTH.update(self._saved_health)
        self._tmp.cleanup()

    def _prior(self, zero_streak):
        (scraper.DATA_DIR / "health.json").write_text(
            json.dumps({"twitter": {"tweets": 0, "zero_streak": zero_streak}}))

    def _run(self, sites=(("A Site", 5),), articles=5):
        return scraper.report_health([{"name": n} for n, _ in sites], articles)

    def _written(self):
        return json.loads((scraper.DATA_DIR / "health.json").read_text())

    # --- the streak ------------------------------------------------------
    def test_a_healthy_run_passes_and_clears_the_streak(self):
        self._prior(2)
        self.assertEqual(self._run(), 0)
        self.assertEqual(self._written()["twitter"]["zero_streak"], 0)

    def test_the_first_zero_tweet_run_warns_but_does_not_fail(self):
        # THE regression test. This run collected every article it was asked
        # for; failing it teaches the team that red means nothing.
        scraper.HEALTH["twitter"] = {"tweets": 0, "accounts": 0, "error": "no tweets"}
        self.assertEqual(self._run(), 0)
        self.assertEqual(self._written()["twitter"]["zero_streak"], 1)

    def test_the_streak_accumulates_across_runs(self):
        self._prior(1)
        scraper.HEALTH["twitter"] = {"tweets": 0, "accounts": 0, "error": "no tweets"}
        self.assertEqual(self._run(), 0)
        self.assertEqual(self._written()["twitter"]["zero_streak"], 2)

    def test_sustained_silence_still_fails(self):
        # The other half of the boundary: rot must not hide behind the grace.
        self._prior(scraper.TWITTER_ZERO_STREAK_FATAL - 1)
        scraper.HEALTH["twitter"] = {"tweets": 0, "accounts": 0, "error": "no tweets"}
        self.assertEqual(self._run(), 1)

    def test_a_missing_previous_health_file_starts_the_streak_at_one(self):
        # First run on a fresh checkout, or the file never committed.
        scraper.HEALTH["twitter"] = {"tweets": 0, "accounts": 0, "error": "x"}
        self.assertEqual(self._run(), 0)
        self.assertEqual(self._written()["twitter"]["zero_streak"], 1)

    def test_a_corrupt_previous_health_file_does_not_crash_the_gate(self):
        (scraper.DATA_DIR / "health.json").write_text("{ not json")
        scraper.HEALTH["twitter"] = {"tweets": 0, "accounts": 0, "error": "x"}
        self.assertEqual(self._run(), 0)

    # --- everything the streak must NOT soften ---------------------------
    def test_a_dead_browser_still_fails_immediately(self):
        scraper.HEALTH["browser_ok"] = False
        scraper.HEALTH["browser_error"] = "launch failed"
        self.assertEqual(self._run(), 1)

    def test_zero_articles_from_the_browser_half_still_fails_immediately(self):
        self.assertEqual(self._run(articles=0), 1)

    def test_the_article_gate_is_independent_of_the_twitter_streak(self):
        # A full haul of tweets does not excuse an empty article scrape.
        scraper.HEALTH["twitter"] = {"tweets": 60, "accounts": 12, "error": ""}
        self.assertEqual(self._run(articles=0), 1)


class PageReplacementTest(unittest.IsolatedAsyncioTestCase):
    """A replacement page must keep counting into the RUN's counters.

    install_navigation_policy's wrapper closes over the stats dict it is given,
    so a fresh dict on the replacement page orphans everything counted before
    the crash - and the end-of-run [NAV]/[ASSETS] lines would then describe only
    the last page rather than the run, while looking perfectly normal.
    """

    class FakePage:
        def __init__(self):
            self.routes = []
            self.goto = self._goto

        async def _goto(self, url, **kwargs):
            return None

        async def route(self, pattern, handler):
            self.routes.append(pattern)

    class FakeBrowser:
        def __init__(self, page):
            self._page = page
            self.pages_made = 0

        async def new_page(self):
            self.pages_made += 1
            return self._page

    async def test_the_replacement_shares_the_run_counters(self):
        nav = {"floored": 7, "retried": 2, "retry_saved": 1, "budget_exhausted": 0}
        assets = {"blocked": 500, "allowed": 100}
        page = self.FakePage()
        browser = self.FakeBrowser(page)
        got = await scraper.new_configured_page(browser, 30000, nav, assets)
        self.assertIs(got, page)
        self.assertEqual(browser.pages_made, 1)
        self.assertEqual(nav["floored"], 7, "counts from before the crash survive")
        self.assertEqual(assets["blocked"], 500)

    async def test_the_replacement_is_floored_and_routed_like_the_original(self):
        # A bare replacement page would re-time-out on every proxied listing and
        # download every image on a metered proxy - a recovery worse than the
        # crash.
        page = self.FakePage()
        nav = {"floored": 0, "retried": 0, "retry_saved": 0, "budget_exhausted": 0}
        assets = {"blocked": 0, "allowed": 0}
        await scraper.new_configured_page(self.FakeBrowser(page), 30000, nav, assets)
        self.assertTrue(hasattr(page, "arm_nav_floor"), "nav policy not installed")
        self.assertEqual(page.routes, ["**/*"], "asset blocker not installed")

    async def test_the_asset_blocker_is_skipped_when_it_was_never_on(self):
        page = self.FakePage()
        nav = {"floored": 0, "retried": 0, "retry_saved": 0, "budget_exhausted": 0}
        await scraper.new_configured_page(self.FakeBrowser(page), 30000, nav, None)
        self.assertEqual(page.routes, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
