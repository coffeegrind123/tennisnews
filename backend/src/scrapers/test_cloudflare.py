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

from scrapers.cloudflare import looks_like_challenge


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
