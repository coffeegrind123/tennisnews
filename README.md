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

12 curated Twitter accounts scraped via Nitter. The primary instance is
`lightbrd.com`; it sits behind a Cloudflare managed challenge, which
`scrapers/cloudflare.py` waits out (and clicks through, when a Turnstile widget
is actually rendered). If an instance cannot be cleared the scraper falls through
an ordered list of alternatives rather than silently reporting zero tweets.
Override the order with `NITTER_BASES=https://a,https://b`.

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
