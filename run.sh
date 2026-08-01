#!/bin/bash
# Tennis News Aggregator
# Usage: ./run.sh [SCRAPE_INTERVAL_MINUTES]
# Env:   PORT=8080  SCRAPER_HTTP_PROXY=http://user:pass@host:port

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INTERVAL=${1:-30}

cleanup() { kill $SERVER_PID 2>/dev/null; exit 0; }
trap cleanup SIGINT SIGTERM

echo "=== Tennis News Aggregator ==="
echo "Scrape interval: ${INTERVAL}m | Server port: ${PORT:-8080}"

# camoufox >=0.5 will not find a pre-downloaded build unless it is registered in
# its multiversion cache layout; without this every browser-scraped source
# returns zero.
if [ -x "$SCRIPT_DIR/backend/camoufox_build/camoufox-bin" ]; then
    python3 "$SCRIPT_DIR/backend/setup_camoufox.py" || {
        echo "WARNING: could not register camoufox build; browser sources will fail" >&2
    }
fi

cd "$SCRIPT_DIR/backend/src"

echo "Running initial scrape..."
# scraper.py exits non-zero when sources are unhealthy; it still writes whatever
# it collected, so serve that rather than aborting under `set -e`.
python3 scraper.py || echo "WARNING: scrape reported unhealthy sources (see data/health.json)" >&2

echo "Starting server..."
python3 server.py &
SERVER_PID=$!

while true; do
    sleep "${INTERVAL}m"
    echo "--- Periodic scrape ---"
    python3 scraper.py || true
done
