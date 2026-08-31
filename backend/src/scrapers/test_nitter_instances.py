"""Offline tests for Nitter instance discovery.

Run: python3 -m unittest scrapers.test_nitter_instances -v   (from backend/src)

Nothing here touches the network. Every fixture is a real response captured on
2026-08-31 from the host named in the test, because the bugs this file exists to
prevent were all misreadings of real bodies rather than logic errors:

  * n.opnxng.com 302s to a hosting blog whose changelog says "Anubis", which
    scored the blog as a solvable interstitial;
  * farside.link's 404 lists every frontend it proxies, so a bare "nitter"
    substring made a redirect service look like an instance;
  * twiiit.com and nitter.cz both 302 onto nt.vern.cc, so one backend occupied
    three slots and its single rate limit looked like three instances dying.

Synthetic HTML would not have caught any of them.
"""

import pathlib
import unittest

from scrapers import nitter_instances as ni


class RegistryFreshnessTest(unittest.TestCase):
    def test_newest_date_wins_over_document_order(self):
        # upptime writes dailyMinutesDown newest-first, but nothing guarantees
        # that, so the parser takes a max rather than the first match.
        blob = '{"dailyMinutesDown": {"2024-03-01": 1, "2024-04-02": 5, "2024-01-09": 3}}'
        self.assertEqual(ni._newest_iso_date(blob), "2024-04-02")

    def test_undated_registry_reports_no_age(self):
        self.assertIsNone(ni._newest_iso_date("no dates in here at all"))
        self.assertIsNone(ni._registry_age_days("no dates in here at all"))

    def test_stale_registry_is_recognised_as_stale(self):
        age = ni._registry_age_days('{"d": {"2024-04-02": 1}}')
        self.assertIsNotNone(age)
        self.assertGreater(age, ni.tunable("NITTER_REGISTRY_MAX_AGE_DAYS"))


class RegistryParsingTest(unittest.TestCase):
    def test_upptime_summary(self):
        payload = [
            {"url": "https://nitter.net", "status": "down"},
            {"url": "https://nitter.cz", "status": "up"},
            {"name": "no url here"},
        ]
        self.assertEqual(
            ni._parse_upptime_summary(payload),
            [("https://nitter.net", "down"), ("https://nitter.cz", "up")],
        )

    def test_d420_empty_hosts_is_not_an_error(self):
        # This is the LIVE shape as of 2026-08-28: the monitor is healthy and
        # reports zero healthy hosts. It must parse to [], not raise.
        payload = {"hosts": [], "last_update": "2026-08-28T14:48:00Z"}
        self.assertEqual(ni._parse_d420(payload), [])

    def test_d420_accepts_both_host_shapes(self):
        self.assertEqual(
            ni._parse_d420({"hosts": ["https://a.example"]}),
            [("https://a.example", "up")],
        )
        self.assertEqual(
            ni._parse_d420({"hosts": [{"url": "https://b.example", "healthy": False}]}),
            [("https://b.example", "down")],
        )

    def test_markdown_table_skips_non_instance_links(self):
        md = (
            "| [nitter.net](https://nitter.net) | [Let's Encrypt]"
            "(https://www.ssllabs.com/ssltest/analyze.html?d=nitter.net) |\n"
            "| [xcancel.com](https://xcancel.com) | [src](https://github.com/zedeus/nitter) |\n"
        )
        got = [u for u, _ in ni._parse_markdown_table(md)]
        self.assertIn("https://nitter.net", got)
        self.assertIn("https://xcancel.com", got)
        self.assertNotIn("https://www.ssllabs.com/ssltest/analyze.html?d=nitter.net", got)
        self.assertNotIn("https://github.com/zedeus/nitter", got)


class NormaliseTest(unittest.TestCase):
    def test_strips_trailing_slash_and_path(self):
        self.assertEqual(ni.normalise("https://nitter.net/")[0], "https://nitter.net")
        self.assertEqual(ni.normalise("https://nitter.net/foo")[0], "https://nitter.net")

    def test_bare_host_gets_a_scheme(self):
        self.assertEqual(ni.normalise("nitter.net")[0], "https://nitter.net")

    def test_credentials_move_from_url_into_a_header(self):
        # The registry really does carry https://nitter:nitter@nitter.ftw.lol.
        # Left in the base it would end up embedded in every scraped tweet link.
        base, auth = ni.normalise("https://nitter:nitter@nitter.ftw.lol")
        self.assertEqual(base, "https://nitter.ftw.lol")
        self.assertEqual(auth, "Basic bml0dGVyOm5pdHRlcg==")

    def test_port_is_preserved(self):
        self.assertEqual(ni.normalise("https://host.example:8080/x")[0],
                         "https://host.example:8080")

    def test_junk_is_rejected(self):
        self.assertEqual(ni.normalise("")[0], "")
        self.assertEqual(ni.normalise("   ")[0], "")


# Captured 2026-08-31. Trimmed to the bytes that decide the classification.
FIXTURES = {
    "cloudflare_403": (
        "<!DOCTYPE html><html><head><title>Just a moment...</title>"
        '<meta http-equiv="refresh" content="390">'
        '<script src="/cdn-cgi/challenge-platform/h/g/orchestrate/chl_page/v1">'
        "</script></head><body>Enable JavaScript and cookies to continue</body></html>"
    ),
    "anubis_418": (
        "<!DOCTYPE html><html><head><title>Checking you are not a bot</title>"
        "</head><body><h1>Checking you are not a bot</h1>"
        '<script>// anubis proof-of-work challenge</script></body></html>'
    ),
    "nitter_timeline": (
        '<html><head><title>José Morgado (@josemorgado)</title></head><body>'
        '<div class="profile-card"></div>'
        '<div class="timeline-item"><div class="tweet-content">a tweet</div></div>'
        '<div class="timeline-item"><div class="tweet-content">another</div></div>'
        "</body></html>"
    ),
    "nitter_empty": (
        '<html><head><meta property="og:site_name" content="nitter"></head>'
        '<body><div class="profile-card"></div><div class="error-panel">'
        "Instance has been rate limited.</div></body></html>"
    ),
    "rate_limited": (
        "<html><head><title>Access denied</title></head><body>"
        "<h1>Error 1015</h1><p>You are being rate limited</p></body></html>"
    ),
    "farside_404": (
        "<html><head><title>Farside</title></head><body>"
        "<p>Redirects to nitter, libreddit, invidious and more.</p>"
        "<h1>404 unknown service</h1></body></html>"
    ),
    "opnxng_blog": (
        "<html><head><title>Opnxng | Blog</title></head><body>"
        "<p>06.08 Switched back to Anubis to stop bots. Go-away is great "
        "software, but we currently have less time to experiment with it.</p>"
        "<p>17.02 Nitter is over. Thanks to @zedeus.</p></body></html>"
    ),
    "cease_and_desist": (
        "<html><head><title>503 Service Unavailable</title></head><body>"
        "<p>Nitter is currently unavailable due to the cease and desist letters "
        "some public instance hosters have recieved.</p></body></html>"
    ),
    "parked": "<html><head><title>Buy this domain</title></head><body>For sale</body></html>",
}


class _FakeResponse:
    def __init__(self, status, body, final_url):
        self.status = status
        self._body = body.encode()
        self._final = final_url

    def read(self, _n=None):
        return self._body

    def geturl(self):
        return self._final

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeOpener:
    """Stands in for urllib's opener. Raises for >=400 the way urllib does, so
    the HTTPError-carries-a-body path is exercised rather than bypassed - that
    path is what keeps a 403 interstitial from being read as a dead host."""

    def __init__(self, status, body, final_url):
        self.status, self.body, self.final = status, body, final_url

    def open(self, req, timeout=None):
        if self.status >= 400:
            from urllib.error import HTTPError
            import io
            raise HTTPError(self.final, self.status, "err", {},
                            io.BytesIO(self.body.encode()))
        return _FakeResponse(self.status, self.body, self.final)


class ClassifyTest(unittest.TestCase):
    def _classify(self, status, body, final_url=None, base="https://x.example"):
        final = final_url or f"{base}/{ni.PROBE_HANDLE}"
        original = ni._opener
        ni._opener = lambda _p: _FakeOpener(status, body, final)
        try:
            return ni.classify(base, None, None)
        finally:
            ni._opener = original

    def test_cloudflare_403_is_a_candidate_not_a_corpse(self):
        # lightbrd.com answers exactly like this and DOES work through camoufox.
        rec = self._classify(403, FIXTURES["cloudflare_403"])
        self.assertEqual(rec["tier"], ni.TIER_CHALLENGE)
        self.assertEqual(rec["http"], 403)
        self.assertGreater(rec["bytes"], 0, "HTTPError body must not be discarded")

    def test_anubis_418_is_a_challenge(self):
        rec = self._classify(418, FIXTURES["anubis_418"])
        self.assertEqual(rec["tier"], ni.TIER_CHALLENGE)

    def test_rendered_timeline_is_the_top_tier(self):
        rec = self._classify(200, FIXTURES["nitter_timeline"])
        self.assertEqual(rec["tier"], ni.TIER_TIMELINE)

    def test_nitter_without_a_timeline_is_demoted_not_dropped(self):
        rec = self._classify(200, FIXTURES["nitter_empty"])
        self.assertEqual(rec["tier"], ni.TIER_EMPTY)

    def test_error_1015_is_rate_limited(self):
        rec = self._classify(200, FIXTURES["rate_limited"])
        self.assertEqual(rec["tier"], ni.TIER_LIMITED)

    def test_http_429_is_rate_limited(self):
        rec = self._classify(429, "<html><body>slow down</body></html>")
        self.assertEqual(rec["tier"], ni.TIER_LIMITED)

    def test_farside_404_is_not_an_instance(self):
        # Regression: a bare "nitter" substring used to promote this to
        # TIER_EMPTY and put a redirect service into the instance list.
        rec = self._classify(404, FIXTURES["farside_404"],
                             final_url="https://farside.link/josemorgado")
        self.assertEqual(rec["tier"], ni.TIER_DEAD)

    def test_redirect_to_a_landing_page_is_dead(self):
        # Regression: n.opnxng.com 302s to its blog, whose changelog mentions
        # Anubis. Matching markers without checking WHERE we landed scored a
        # hosting company's changelog as a solvable interstitial.
        rec = self._classify(200, FIXTURES["opnxng_blog"],
                             final_url="https://n.opnxng.com/",
                             base="https://n.opnxng.com")
        self.assertEqual(rec["tier"], ni.TIER_DEAD)
        self.assertIn("landing page", rec["note"])

    def test_cease_and_desist_page_is_dead(self):
        rec = self._classify(503, FIXTURES["cease_and_desist"])
        self.assertEqual(rec["tier"], ni.TIER_DEAD)

    def test_parked_domain_is_dead(self):
        rec = self._classify(200, FIXTURES["parked"])
        self.assertEqual(rec["tier"], ni.TIER_DEAD)

    def test_network_failure_is_dead_and_names_the_exception(self):
        original = ni._opener

        class Boom:
            def open(self, *a, **k):
                raise OSError("Name or service not known")

        ni._opener = lambda _p: Boom()
        try:
            rec = ni.classify("https://gone.example", None, None)
        finally:
            ni._opener = original
        self.assertEqual(rec["tier"], ni.TIER_DEAD)
        self.assertIn("OSError", rec["note"])

    def test_redirect_target_is_recorded_for_alias_collapsing(self):
        rec = self._classify(418, FIXTURES["anubis_418"],
                             final_url="https://nt.vern.cc/josemorgado",
                             base="https://twiiit.com")
        self.assertEqual(rec["final"], "https://nt.vern.cc")


class OrderingTest(unittest.TestCase):
    """discover()'s ordering, driven through a stubbed probe so it stays offline."""

    def setUp(self):
        # discover() writes its result to the cache, so without this the fake
        # hosts below land in the REAL backend/.cache/nitter_instances.json and
        # the next actual scrape reads back "https://live.example". Caught the
        # hard way: a post-test run resolved to four fixture domains.
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self._saved = (ni.CACHE_DIR, ni.CACHE_PATH)
        ni.CACHE_DIR = pathlib.Path(self._tmp.name)
        ni.CACHE_PATH = ni.CACHE_DIR / "nitter_instances.json"

    def tearDown(self):
        ni.CACHE_DIR, ni.CACHE_PATH = self._saved
        self._tmp.cleanup()

    def _discover(self, records, **env):
        import os
        original_probe, original_registry = ni.probe_all, ni.fetch_registry
        original_env = {k: os.environ.get(k) for k in
                        ("NITTER_BASES", "NITTER_DISCOVERY", "NITTER_SHUFFLE_SEED",
                         "NITTER_MAX_BASES")}
        ni.probe_all = lambda cands, proxy=None: records
        ni.fetch_registry = lambda url, proxy=None: []
        os.environ["NITTER_SHUFFLE_SEED"] = "7"
        for k, v in env.items():
            os.environ[k] = v
        try:
            return ni.discover(use_cache=False)
        finally:
            ni.probe_all, ni.fetch_registry = original_probe, original_registry
            for k, v in original_env.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v

    @staticmethod
    def _rec(base, tier, final=None):
        return {"base": base, "final": final or base, "tier": tier, "http": 200,
                "bytes": 100, "note": "", "elapsed_ms": 1}

    def test_tiers_outrank_the_shuffle(self):
        got = self._discover([
            self._rec("https://empty.example", ni.TIER_EMPTY),
            self._rec("https://challenged.example", ni.TIER_CHALLENGE),
            self._rec("https://live.example", ni.TIER_TIMELINE),
            self._rec("https://limited.example", ni.TIER_LIMITED),
        ])
        self.assertEqual(got, ["https://live.example", "https://challenged.example",
                               "https://limited.example", "https://empty.example"])

    def test_dead_hosts_never_reach_the_list(self):
        got = self._discover([
            self._rec("https://live.example", ni.TIER_TIMELINE),
            self._rec("https://dead.example", ni.TIER_DEAD),
        ])
        self.assertEqual(got, ["https://live.example"])

    def test_aliases_collapse_to_one_slot(self):
        got = self._discover([
            self._rec("https://twiiit.com", ni.TIER_CHALLENGE, "https://nt.vern.cc"),
            self._rec("https://nitter.cz", ni.TIER_CHALLENGE, "https://nt.vern.cc"),
            self._rec("https://nt.vern.cc", ni.TIER_CHALLENGE),
        ])
        self.assertEqual(got, ["https://nt.vern.cc"],
                         "one backend must not occupy three slots")

    def test_canonical_host_beats_its_redirector(self):
        got = self._discover([
            self._rec("https://twiiit.com", ni.TIER_CHALLENGE, "https://nt.vern.cc"),
            self._rec("https://nt.vern.cc", ni.TIER_CHALLENGE),
        ])
        self.assertEqual(got, ["https://nt.vern.cc"])

    def test_all_dead_falls_back_rather_than_returning_nothing(self):
        # An empty list would guarantee zero tweets. The browser can clear walls
        # this probe cannot, so it still gets its chance.
        got = self._discover([self._rec("https://dead.example", ni.TIER_DEAD)])
        self.assertEqual(got, ni.DEFAULT_BASES)
        self.assertEqual(ni.LAST_RUN["status"], "no live instance found")

    def test_max_bases_caps_the_list(self):
        got = self._discover(
            [self._rec(f"https://h{i}.example", ni.TIER_CHALLENGE) for i in range(10)],
            NITTER_MAX_BASES="3")
        self.assertEqual(len(got), 3)

    def test_env_override_bypasses_discovery(self):
        got = self._discover([self._rec("https://live.example", ni.TIER_TIMELINE)],
                             NITTER_BASES="https://only.example/, https://two.example")
        self.assertEqual(got, ["https://only.example", "https://two.example"])
        self.assertEqual(ni.LAST_RUN["status"], "env override")

    def test_discovery_can_be_switched_off(self):
        got = self._discover([self._rec("https://live.example", ni.TIER_TIMELINE)],
                             NITTER_DISCOVERY="0")
        self.assertEqual(got, ni.DEFAULT_BASES)
        self.assertEqual(ni.LAST_RUN["status"], "disabled")

    def test_shuffle_actually_shuffles(self):
        import os
        bucket = [self._rec(f"https://h{i}.example", ni.TIER_CHALLENGE) for i in range(12)]
        orders = set()
        for seed in ("1", "2", "3", "4", "5"):
            os.environ["NITTER_SHUFFLE_SEED"] = seed
            orders.add(tuple(self._discover(list(bucket), NITTER_SHUFFLE_SEED=seed)))
        os.environ.pop("NITTER_SHUFFLE_SEED", None)
        self.assertGreater(len(orders), 1,
                           "a fixed order means one host absorbs every run")


if __name__ == "__main__":
    unittest.main(verbosity=2)
