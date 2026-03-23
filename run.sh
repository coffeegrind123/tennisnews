#!/bin/bash
# Tennis News Aggregator
# Usage: ./run.sh [SCRAPE_INTERVAL_MINUTES]
# Env:   PORT=8080  SCRAPER_HTTP_PROXY=http://user:pass@host:port

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INTERVAL=${1:-30}

cd "$SCRIPT_DIR/backend/src"

cleanup() { kill $SERVER_PID 2>/dev/null; exit 0; }
trap cleanup SIGINT SIGTERM

echo "=== Tennis News Aggregator ==="
echo "Scrape interval: ${INTERVAL}m | Server port: ${PORT:-8080}"

echo "Running initial scrape..."
python3 scraper.py

echo "Starting server..."
python3 server.py &
SERVER_PID=$!

while true; do
    sleep "${INTERVAL}m"
    echo "--- Periodic scrape ---"
    python3 scraper.py || true
done
