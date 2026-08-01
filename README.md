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

## Health

`scraper.py` writes `data/health.json` every run (per-source article counts,
errors, which sources came back empty) and **exits non-zero** if the browser
never started, if every browser-scraped source was empty, or if Twitter produced
no tweets. The CI job publishes whatever it collected and then fails on that
signal, so a broken scrape shows up as a red run instead of a quietly shrinking
feed.
