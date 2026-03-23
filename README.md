# Tennis News Aggregator

Simple tennis news feed that scrapes ~37 sites and serves a plain HTML page designed for LLM consumption. Includes a curated Twitter feed section from 12 tennis-focused accounts.

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

37 tennis news sites from [Feedspot Top 40](https://news.feedspot.com/tennis_news_websites/):
- 12 via RSS feeds (feedparser)
- 25 via browser scraping (camoufox) with per-site tailored modules

12 curated Twitter accounts scraped via xcancel.com proxy.
