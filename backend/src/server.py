#!/usr/bin/env python3
"""
Simple HTTP server for tennis news feed.
Supports ?q=keyword and ?source=name query parameters for filtering.
"""

import json
import html as html_lib
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PROJECT_DIR = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_DIR / "data"
PORT = int(__import__("os").environ.get("PORT", "8080"))


def load_articles() -> list[dict]:
    path = DATA_DIR / "articles.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def load_tweets() -> list[dict]:
    path = DATA_DIR / "tweets.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def filter_articles(articles: list[dict], query: str = "", source: str = "") -> list[dict]:
    results = articles
    if query:
        q = query.lower()
        results = [
            a for a in results
            if q in a["title"].lower() or q in a.get("description", "").lower()
        ]
    if source:
        s = source.lower()
        results = [a for a in results if s in a["source_name"].lower()]
    return results


def filter_tweets(tweets: list[dict], query: str = "") -> list[dict]:
    if not query:
        return tweets
    q = query.lower()
    return [t for t in tweets if q in t["title"].lower()]


def render_html(articles: list[dict], tweets: list[dict], query: str = "", source: str = "") -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    all_articles = load_articles()
    all_tweets = load_tweets()
    sources = sorted(set(a["source_name"] for a in all_articles))

    filter_info = ""
    if query:
        filter_info = f' | Search: "{html_lib.escape(query)}"'
    if source:
        filter_info += f' | Source: "{html_lib.escape(source)}"'

    rows = []
    for a in articles:
        t = html_lib.escape(a["title"])
        d = html_lib.escape(a.get("description", ""))
        l = html_lib.escape(a["link"])
        s = html_lib.escape(a["source_name"])
        dt = html_lib.escape(a.get("date", ""))
        rows.append(
            f'<div class="a">'
            f'<h2><a href="{l}">{t}</a></h2>'
            f'<p class="s">Source: {s}</p>'
            f'{f"<p>{d}</p>" if d else ""}'
            f'{f"<p class=d>{dt}</p>" if dt else ""}'
            f"</div>"
        )

    tweet_rows = []
    for tw in tweets:
        t = html_lib.escape(tw["title"])
        l = html_lib.escape(tw.get("link", ""))
        author = html_lib.escape(tw.get("author", ""))
        handle = html_lib.escape(tw.get("handle", ""))
        dt = html_lib.escape(tw.get("date", ""))
        tweet_rows.append(
            f'<div class="tw">'
            f'<p class="tw-author"><b>@{handle}</b> ({author})</p>'
            f'<p>{t}</p>'
            f'<p class="d"><a href="{l}">{dt}</a></p>'
            f"</div>"
        )

    source_links = " | ".join(
        f'<a href="?source={html_lib.escape(s)}">{html_lib.escape(s)}</a>'
        for s in sources
    )

    q_val = html_lib.escape(query)

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Tennis News Feed</title>
<style>body{{font-family:sans-serif;max-width:900px;margin:0 auto;padding:1em}}
.a{{border-bottom:1px solid #ccc;padding:0.5em 0}}.s{{color:#666;font-size:0.9em}}
.d{{color:#999;font-size:0.8em}}h2{{font-size:1.1em;margin:0.3em 0}}
p{{margin:0.2em 0}}a{{color:#1a6}}nav{{margin:1em 0;font-size:0.85em}}
form{{margin:1em 0}}input{{padding:0.3em;width:300px}}
.tw{{border-bottom:1px solid #eee;padding:0.4em 0}}.tw-author{{color:#555;font-size:0.9em}}
h1.section{{margin-top:2em;border-top:2px solid #333;padding-top:0.5em}}</style></head>
<body>
<h1>Tennis News Feed</h1>
<p>Updated: {now} | {len(articles)} articles{filter_info} | <a href="/">All ({len(all_articles)})</a> | <a href="#twitter">{len(tweets)} tweets</a></p>
<form method="get"><input type="text" name="q" value="{q_val}" placeholder="Search articles and tweets...">
<button type="submit">Search</button></form>
<nav>Sources: {source_links}</nav>
{"".join(rows)}
<h1 class="section" id="twitter">Tennis Twitter Feed</h1>
<p>{len(tweets)} tweets from {len(set(tw.get('handle','') for tw in tweets))} accounts</p>
{"".join(tweet_rows)}
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/api/articles":
            articles = load_articles()
            q = params.get("q", [""])[0]
            src = params.get("source", [""])[0]
            if q or src:
                articles = filter_articles(articles, q, src)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(articles, ensure_ascii=False).encode())
            return

        if parsed.path == "/api/tweets":
            tweets = load_tweets()
            q = params.get("q", [""])[0]
            if q:
                tweets = filter_tweets(tweets, q)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(tweets, ensure_ascii=False).encode())
            return

        if parsed.path in ("/", "/index.html"):
            articles = load_articles()
            tweets = load_tweets()
            q = params.get("q", [""])[0]
            src = params.get("source", [""])[0]
            if q or src:
                articles = filter_articles(articles, q, src)
            if q:
                tweets = filter_tweets(tweets, q)
            body = render_html(articles, tweets, q, src)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode())
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {format % args}")


def main():
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Tennis News server on http://0.0.0.0:{PORT}")
    print(f"  HTML:   http://localhost:{PORT}/")
    print(f"  API:    http://localhost:{PORT}/api/articles")
    print(f"  Tweets: http://localhost:{PORT}/api/tweets")
    print(f"  Search: http://localhost:{PORT}/?q=djokovic")
    server.serve_forever()


if __name__ == "__main__":
    main()
