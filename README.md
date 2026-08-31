# Tennis News Aggregator

Simple tennis news feed that scrapes 39 sites and serves a plain HTML page designed for LLM consumption. Includes a curated Twitter feed section from 12 tennis-focused accounts.

## Setup

```bash
pip install feedparser camoufox
```

Camoufox needs its browser binary. On first run it will download automatically, or you can place a pre-built `camoufox_build/` directory in `backend/`.

## Usage

```bash
# One-time scrape only
cd backend/src && python3 scraper.py

# Server only (serve existing data)
cd backend/src && python3 server.py

# Both + periodic refresh (default every 30 min)
./run.sh

# Custom interval (10 min)
./run.sh 10

# With proxy
SCRAPER_HTTP_PROXY=http://user:pass@host:port ./run.sh

# Custom port
PORT=3000 ./run.sh
```

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `http://localhost:8080/` | Full HTML feed with articles + Twitter section |
| `http://localhost:8080/?q=keyword` | Search articles and tweets |
| `http://localhost:8080/?source=ESPN` | Filter by source name |
| `http://localhost:8080/api/articles` | JSON API for articles |
| `http://localhost:8080/api/articles?q=djokovic` | JSON search |
| `http://localhost:8080/api/tweets` | JSON API for tweets |
| `http://localhost:8080/api/tweets?q=sinner` | JSON tweet search |

## Sources

39 tennis news sites, defined in `backend/src/sites.py`:
- 18 via RSS feeds (feedparser)
- 21 via browser scraping (camoufox) with per-site tailored modules

12 curated Twitter accounts scraped via Nitter. Most instances sit behind a
Cloudflare managed challenge or an Anubis proof-of-work wall, which
`scrapers/cloudflare.py` waits out (and clicks through, when a Turnstile widget
is actually rendered). If an instance cannot be cleared the scraper falls through
an ordered list of alternatives rather than silently reporting zero tweets.

The instance list is discovered per run by `scrapers/nitter_instances.py` rather
than hardcoded. It merges candidate URLs from public registries, probes each one
over plain HTTP, and returns only the hosts that answered - best tier first,
shuffled within a tier. Shuffling is functional, not cosmetic: instances rate
limit per client after a few profile loads, so a fixed order means one host
absorbs every run and hits its 1015 at the same account every time.

**A registry's own `status` field is not trusted.** Measured 2026-08-31, the
upptime registry the module reads has not been written since 2024-04-02, and of
the 37 hosts it still marks `"up"`, 18 fail DNS outright and none serve a
timeline. Registries supply candidate URLs; the live probe decides what "up"
means. When a registry's newest datapoint is older than
`NITTER_REGISTRY_MAX_AGE_DAYS` its status field is ignored entirely.

What each run actually walked, and why, lands in `data/health.json` under
`twitter.instances` - so "0 tweets" can be told apart from "0 instances", which
need completely different fixes.

Override the order with `NITTER_BASES=https://a,https://b` (bypasses discovery),
or set `NITTER_DISCOVERY=0` to use the built-in list. Other knobs are documented
at the top of `scrapers/nitter_instances.py`.

Offline tests for the discovery logic:
`cd backend/src && python3 -m unittest scrapers.test_nitter_instances`

### Current status (2026-08-31)

Nitter is close to dead upstream. The project repo was archived 2026-08-26, X
Corp sent cease-and-desist letters around 2026-08-24 (xcancel.com and
nitter.catsarch.com both serve notices saying so), and the d420 monitor reports
zero healthy hosts. The previous hardcoded list had rotted through completely:
nitter.poast.org no longer resolves, nitter.net serves a stub, privacyredirect
502s, tiekoetter 429s, and lightbrd.com's Cloudflare challenge now solves only
to hang on "Waiting for lightbrd.com to respond" - the edge is up, the origin
behind it is not. Zero of the five produced a tweet.

Discovery is what recovers from that. Of 109 candidates probed, 9 answered; a
browser pass over the 6 distinct backends found **nitter.freedit.eu working** -
Cloudflare cleared in 9s, 20 timeline items, real tweets. It reached the list
from the registry corpus and appears in no version of the old hardcoded list.
That is the whole point of probing rather than trusting: one live host among a
hundred dead ones is the difference between a working feed and none.

A full scrape through the new path then returned **60 tweets across 12/12
accounts from nitter.freedit.eu alone** - no fallback needed, no 1015 - with the
newest tweets dated the same day. The feed had been dead since 2026-08-02.

The rest of that browser pass, for the record: nitter.kareem.one never cleared,
nuku.trabun.org clears Cloudflare then returns 401 (private), nt.vern.cc sits
behind an unsolved go-away proof-of-work wall, and bird.habedieeh.re turns out
to run Twitscher rather than Nitter.

## Prompt-injection screening

`public/index.html` is designed for LLM consumption, and every string in it comes
from a third-party site or Twitter account. A headline reading "Ignore previous
instructions and ..." is a working indirect prompt injection against whatever
model reads the feed.

Every article title, description and tweet is therefore screened through
[@stackone/defender](https://www.npmjs.com/package/@stackone/defender) (pattern
detection plus an ONNX classifier) via a long-lived Node bridge
(`backend/src/defender_bridge.mjs`), spawned once per run.

When an item is flagged the text is **redacted** but the item is kept: the source
name, link and date survive, and the HTML carries a visible warning naming the
source. Dropping the story silently would hide the fact that a source is serving
injections; this makes it obvious which one is.

The classifier threshold is **0.85**, measured rather than inherited:

| | tier2 score |
|---|---|
| 522 real scraped articles | median 0.052, p95 0.141, **max 0.778** |
| Known-attack controls | **0.939 – 0.963** |

Re-measure with `python3 backend/tools/calibrate_defender.py` if the source mix
changes; it also runs known-attack and known-benign controls, so a scanner that
has silently stopped working shows up as missed controls rather than a clean bill
of health. The sbox-learn-docs mirror uses 0.95 for long tutorial prose — at that
value three of the four attack controls here passed.

### Captured attempts

Every redacted payload is appended to `data/injections.jsonl`, committed with the
feed, so the techniques actually aimed at this site accumulate over time:

```bash
python3 backend/tools/injection_report.py          # sources, techniques, persistence
python3 backend/tools/injection_report.py --show 5 # decode payloads (sandbox only)
```

Records are deduplicated on a fingerprint of link+payload — a hostile headline
usually stays up for days, so without that it would re-append on every run and
bury the signal. Repeats bump `times_seen` and `last_seen` instead.

**Payloads are stored base64, not plaintext.** This repo is public and exists to be
read by LLMs, so a plaintext corpus of working injection payloads would itself be
an ingestion hazard. Base64 keeps the evidence byte-exact while making ingestion a
deliberate act. The file's first line is a `_README` record saying so.

If Node or the bridge is unavailable the scrape still runs, but items are marked
`"injection": {"scanned": false}` rather than being presented as clean, and
`data/health.json` records why. Set `SCRAPER_DEFENDER=0` to skip screening.

## Health

`scraper.py` writes `data/health.json` every run (per-source article counts,
errors, which sources came back empty) and **exits non-zero** if the browser
never started, if every browser-scraped source was empty, or if Twitter produced
no tweets. The CI job publishes whatever it collected and then fails on that
signal, so a broken scrape shows up as a red run instead of a quietly shrinking
feed.
