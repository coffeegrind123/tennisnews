"""Offline tests for the source registry and for date normalisation.

Run: python3 -m unittest scrapers.test_sources -v   (from backend/src)

Both halves guard SILENT failures - the kind that produce a plausible-looking
page rather than an error:

  * a scrape site whose module is missing raises at import time inside the
    per-site try/except, which records "0 articles" and moves on;
  * a date that does not parse is returned UNCHANGED, and generate_html then
    filters on `date[:10] >= cutoff` as a string comparison. "Tuesday, S" sorts
    above "2026-09-01" because 'T' > '2', so an unparsed date does not drop an
    item - it pins it on the page forever. Measured on Tennis View Magazine's
    Drupal feed, 2026-09-03, whose published_parsed feedparser cannot fill in.
"""

import importlib
import unittest

import scraper
import sites


class SiteRegistryTest(unittest.TestCase):
    def test_every_scrape_site_has_an_importable_module_with_a_scrape(self):
        for site in sites.SITES:
            if site["type"] != "scrape":
                continue
            with self.subTest(site=site["name"]):
                mod = importlib.import_module("scrapers." + site["module"])
                self.assertTrue(callable(getattr(mod, "scrape", None)))

    def test_every_rss_site_has_a_feed_url(self):
        for site in sites.SITES:
            if site["type"] != "rss":
                continue
            with self.subTest(site=site["name"]):
                self.assertTrue(site.get("feed_url", "").startswith("http"))

    def test_no_site_is_neither_rss_nor_scrape(self):
        for site in sites.SITES:
            self.assertIn(site["type"], ("rss", "scrape"), site["name"])

    def test_names_are_unique(self):
        # HEALTH["sources"] is keyed by name, so a duplicate silently discards
        # one source's health record.
        names = [s["name"] for s in sites.SITES]
        self.assertEqual(len(names), len(set(names)))

    def test_the_espn_feed_is_the_tennis_one_not_the_site_wide_top_feed(self):
        # /rss/tennis is ESPN's "TOP" feed and returns NFL stories; only
        # /rss/tennis/news is tennis. Both return 200 with valid XML, so
        # nothing but this assertion distinguishes them.
        espn = next(s for s in sites.SITES if s["name"] == "ESPN Tennis")
        self.assertEqual(espn["feed_url"],
                         "https://www.espn.com/espn/rss/tennis/news")


class DateNormalisationTest(unittest.TestCase):
    def _parsed(self, raw):
        got = scraper.to_helsinki(raw)
        self.assertNotEqual(got, raw, f"{raw!r} was returned unparsed")
        self.assertRegex(got, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}")
        return got

    def test_drupal_dates_parse(self):
        # Tennis View Magazine's RSS, verbatim.
        self.assertTrue(self._parsed("Tuesday, September 1, 2026 - 12:00pm")
                        .startswith("2026-09-01"))
        self.assertTrue(self._parsed("Sunday, August 9, 2026 - 12:49pm")
                        .startswith("2026-08-09"))
        self.assertTrue(self._parsed("Tuesday, September 1, 2026 - 11:33am")
                        .startswith("2026-09-01"))

    def test_am_and_pm_land_in_different_halves_of_the_day(self):
        # The control for the meridiem: if %p were being dropped, both of these
        # would parse and both would be wrong in the same direction.
        morning = self._parsed("Tuesday, September 1, 2026 - 1:00am")
        evening = self._parsed("Tuesday, September 1, 2026 - 1:00pm")
        self.assertLess(morning, evening)

    def test_tennis_canada_listing_dates_parse(self):
        self.assertTrue(self._parsed("September 2, 2026").startswith("2026-09-02"))
        self.assertTrue(self._parsed("August 31, 2026").startswith("2026-08-31"))

    def test_espn_rfc822_dates_parse(self):
        self._parsed("Thu, 3 Sep 2026 10:35:20 EST")

    def test_formats_that_already_worked_still_work(self):
        # Regression guard: the Drupal rules rewrite the string for everyone.
        self._parsed("2026-09-03T10:35:20+00:00")
        self._parsed("Mar 23, 2026 8:15 AM UTC")
        self._parsed("2026-09-03")
        self._parsed("3h")

    def test_an_unparseable_date_is_still_returned_unchanged(self):
        # Not a regression - it is the documented contract, and the reason the
        # string-compare filter is dangerous. Asserted so the danger stays
        # visible rather than being rediscovered.
        self.assertEqual(scraper.to_helsinki("not a date at all"),
                         "not a date at all")

    def test_an_unparsed_date_would_pass_the_recency_filter(self):
        # THE reason the Drupal rules exist. This is the mechanism, asserted
        # directly: a garbage date does not drop an item, it pins it forever.
        self.assertGreaterEqual("Tuesday, S", "2026-09-01")


if __name__ == "__main__":
    unittest.main(verbosity=2)
