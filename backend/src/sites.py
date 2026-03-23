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
    {"name": "Tennis-X", "url": "https://www.tennis-x.com/", "type": "rss", "feed_url": "https://feeds.feedburner.com/tennisx"},
    {"name": "Tennishead", "url": "https://tennishead.net/tennis/news/", "type": "scrape", "module": "tennishead"},
    {"name": "Lob & Smash", "url": "https://lobandsmash.com/", "type": "rss", "feed_url": "https://lobandsmash.com/feed"},
    {"name": "Tennis Majors", "url": "https://www.tennismajors.com/", "type": "rss", "feed_url": "https://www.tennismajors.com/feed"},
    {"name": "Tennis Now", "url": "https://www.tennisnow.com/", "type": "rss", "feed_url": "https://www.tennisnow.com/feed/"},
    {"name": "Tennis News Blog", "url": "https://the-tennisnews.blogspot.com/", "type": "rss", "feed_url": "https://the-tennisnews.blogspot.com/feeds/posts/default"},
    {"name": "Tennis Australia", "url": "https://www.tennis.com.au/news-and-events/news-and-features/all-news", "type": "scrape", "module": "tennis_australia"},
    {"name": "Tennis Infinity", "url": "https://tennis-infinity.com/", "type": "scrape", "module": "tennis_infinity"},
    {"name": "Australian Open", "url": "https://ausopen.com/news", "type": "scrape", "module": "australian_open"},
    {"name": "Perfect Tennis", "url": "https://www.perfect-tennis.com/", "type": "rss", "feed_url": "https://www.perfect-tennis.com/feed/"},
    {"name": "US Open", "url": "https://www.usopen.org/en_US/news/index.html", "type": "scrape", "module": "us_open"},
    {"name": "Wimbledon", "url": "https://www.wimbledon.com/en_GB/news/index.html", "type": "scrape", "module": "wimbledon"},
    {"name": "ESPN Tennis", "url": "https://www.espn.com/tennis/", "type": "scrape", "module": "espn_tennis"},
    {"name": "Novak Djokovic", "url": "https://novakdjokovic.com/en/n/news/", "type": "scrape", "module": "novak_djokovic"},
    {"name": "Tennisbuzz", "url": "https://tennisbuzz.net/", "type": "scrape", "module": "tennisbuzz"},
    {"name": "Tennis Canada", "url": "https://www.tenniscanada.com/news", "type": "scrape", "module": "tennis_canada"},
    {"name": "USTA Florida", "url": "https://www.ustaflorida.com/news/", "type": "scrape", "module": "usta_florida"},
    {"name": "World Tennis Magazine", "url": "https://worldtennismagazine.com/", "type": "rss", "feed_url": "https://worldtennismagazine.com/feed"},
    {"name": "10sBalls", "url": "https://10sballs.com/", "type": "rss", "feed_url": "https://10sballs.com/feed/"},
    {"name": "Rafael Nadal Fans", "url": "https://rafaelnadalfans.com/", "type": "scrape", "module": "rafael_nadal_fans"},
    {"name": "Tennis Panorama", "url": "https://www.tennispanorama.com/", "type": "scrape", "module": "tennis_panorama"},
    {"name": "Racquet Industry Research", "url": "https://www.racquetindustryresearch.org/news/", "type": "scrape", "module": "racquet_industry_research"},
    {"name": "Tennis View Magazine", "url": "http://www.tennisviewmag.com/tennis-view-magazine/news", "type": "scrape", "module": "tennis_view_magazine"},
    {"name": "Brisbane International", "url": "https://www.brisbaneinternational.com.au/", "type": "scrape", "module": "brisbane_international"},
    {"name": "Asian Tennis Federation", "url": "https://www.asiantennis.com/news/", "type": "scrape", "module": "asian_tennis_federation"},
    {"name": "Tennis Ireland", "url": "https://www.tennisireland.ie/", "type": "rss", "feed_url": "https://www.tennisireland.ie/feed"},
    {"name": "The Slice", "url": "https://www.theslicetennis.com/articles", "type": "scrape", "module": "the_slice"},
    {"name": "Tennis Threads", "url": "https://tennisthreads.net/", "type": "rss", "feed_url": "https://tennisthreads.net/feed"},
    {"name": "Chandos Tennis Club", "url": "https://chandosltc.com/category/news/", "type": "rss", "feed_url": "https://chandosltc.com/feed"},
    {"name": "Great Missenden LTC", "url": "https://www.gmltc.com/", "type": "scrape", "module": "great_missenden"},
    {"name": "Tennis Europe", "url": "https://www.tenniseurope.org/newslist/News", "type": "scrape", "module": "tennis_europe"},
    {"name": "Swiss Indoors Basel", "url": "https://www.swissindoorsbasel.ch/en/tournament/tournament-news/", "type": "scrape", "module": "swiss_indoors"},
]
