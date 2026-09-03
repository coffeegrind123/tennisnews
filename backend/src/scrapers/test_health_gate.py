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


if __name__ == "__main__":
    unittest.main(verbosity=2)
