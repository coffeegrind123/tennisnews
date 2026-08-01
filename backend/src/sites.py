"""
Tennis news site registry.
Each site is either 'rss' (parsed via feedparser) or 'scrape' (parsed via per-site module).
Scrape sites have a dedicated async function in scrapers/<name>.py
"""

SITES = [
    {"name": "ATP Tour", "url": "https://www.atptour.com/en/news", "type": "scrape", "module": "atp_tour"},
    {"name": "Tennis.com", "url": "https://www.tennis.com/news", "type": "scrape", "module": "tennis_com"},
    {"name": "Tennis World USA", "url": "https://www.tennisworldusa.org/", "type": "scrape", "module": "tennis_world_usa"},
    {"name": "Tennis Connected", "url": "https://tennisconnected.com/", "type": "rss", "feed_url": "https://tennisconnected.com/feed/"},
    {"name": "Tennishead", "url": "https://tennishead.net/tennis/news/", "type": "scrape", "module": "tennishead"},
    {"name": "Lob & Smash", "url": "https://lobandsmash.com/", "type": "rss", "feed_url": "https://lobandsmash.com/feed"},
    {"name": "Tennis Majors", "url": "https://www.tennismajors.com/", "type": "rss", "feed_url": "https://www.tennismajors.com/feed"},
    {"name": "Tennis Now", "url": "https://www.tennisnow.com/", "type": "rss", "feed_url": "https://www.tennisnow.com/feed/"},
    {"name": "Tennis Australia", "url": "https://www.tennis.com.au/news-and-events/news-and-features/all-news", "type": "scrape", "module": "tennis_australia"},
    {"name": "Tennis Infinity", "url": "https://tennis-infinity.com/", "type": "scrape", "module": "tennis_infinity"},
    {"name": "Australian Open", "url": "https://ausopen.com/news", "type": "scrape", "module": "australian_open"},
    {"name": "Perfect Tennis", "url": "https://www.perfect-tennis.com/", "type": "rss", "feed_url": "https://www.perfect-tennis.com/feed/"},
    {"name": "US Open", "url": "https://www.usopen.org/en_US/news/index.html", "type": "scrape", "module": "us_open"},
    {"name": "Wimbledon", "url": "https://www.wimbledon.com/en_GB/news/index.html", "type": "scrape", "module": "wimbledon"},
    {"name": "ESPN Tennis", "url": "https://www.espn.com/tennis/", "type": "scrape", "module": "espn_tennis"},
    {"name": "Novak Djokovic", "url": "https://novakdjokovic.com/en/n/news/", "type": "scrape", "module": "novak_djokovic"},
    {"name": "Tennis Canada", "url": "https://www.tenniscanada.com/news", "type": "scrape", "module": "tennis_canada"},
    {"name": "USTA Florida", "url": "https://www.ustaflorida.com/news/", "type": "scrape", "module": "usta_florida"},
    {"name": "World Tennis Magazine", "url": "https://worldtennismagazine.com/", "type": "rss", "feed_url": "https://worldtennismagazine.com/feed"},
    {"name": "10sBalls", "url": "https://10sballs.com/", "type": "rss", "feed_url": "https://10sballs.com/feed/"},
    {"name": "Rafael Nadal Fans", "url": "https://rafaelnadalfans.com/", "type": "scrape", "module": "rafael_nadal_fans"},
    {"name": "Tennis Panorama", "url": "https://www.tennispanorama.com/", "type": "scrape", "module": "tennis_panorama"},
    {"name": "Tennis View Magazine", "url": "http://www.tennisviewmag.com/tennis-view-magazine/news", "type": "scrape", "module": "tennis_view_magazine"},
    {"name": "Brisbane International", "url": "https://www.brisbaneinternational.com.au/", "type": "scrape", "module": "brisbane_international"},
    {"name": "Asian Tennis Federation", "url": "https://www.asiantennis.com/news/", "type": "scrape", "module": "asian_tennis_federation"},
    {"name": "Tennis Ireland", "url": "https://www.tennisireland.ie/", "type": "rss", "feed_url": "https://www.tennisireland.ie/feed"},
    {"name": "Tennis Europe", "url": "https://www.tenniseurope.org/newslist/News", "type": "scrape", "module": "tennis_europe"},
    {"name": "Swiss Indoors Basel", "url": "https://www.swissindoorsbasel.ch/en/tournament/tournament-news/", "type": "scrape", "module": "swiss_indoors"},
    {"name": "DuckDuckGo News", "url": "https://duckduckgo.com/?q=tennis&iar=news&df=d", "type": "scrape", "module": "duckduckgo_news"},

    # Added 2026-08-01. Each was checked for: reachable feed, parseable entries,
    # a newest item under 21 days old, and >=50% of entries actually about
    # tennis (rules out general-sport feeds filed under a tennis URL).
    {"name": "Tennis365", "url": "https://www.tennis365.com/tennis-news", "type": "rss", "feed_url": "https://www.tennis365.com/feed"},
    {"name": "Ubitennis", "url": "https://www.ubitennis.net/", "type": "rss", "feed_url": "https://www.ubitennis.net/feed/"},
    {"name": "Last Word on Tennis", "url": "https://lastwordonsports.com/tennis/", "type": "rss", "feed_url": "https://lastwordonsports.com/tennis/feed/"},
    {"name": "Open Court", "url": "https://opencourt.ca/", "type": "rss", "feed_url": "https://opencourt.ca/feed/"},
    {"name": "Tennis Nerd", "url": "https://tennisnerd.net/", "type": "rss", "feed_url": "https://tennisnerd.net/feed"},
    {"name": "Guardian Tennis", "url": "https://www.theguardian.com/sport/tennis", "type": "rss", "feed_url": "https://www.theguardian.com/sport/tennis/rss"},
    {"name": "BBC Tennis", "url": "https://www.bbc.co.uk/sport/tennis", "type": "rss", "feed_url": "https://feeds.bbci.co.uk/sport/tennis/rss.xml"},
    {"name": "Yahoo Sports Tennis", "url": "https://sports.yahoo.com/tennis/", "type": "rss", "feed_url": "https://sports.yahoo.com/tennis/rss/"},
    {"name": "Racquet Magazine", "url": "https://racquetmag.com/", "type": "rss", "feed_url": "https://racquetmag.com/feed/"},
    {"name": "Women's Tennis Blog", "url": "https://www.womenstennisblog.com/", "type": "rss", "feed_url": "https://www.womenstennisblog.com/feed/"},
]
