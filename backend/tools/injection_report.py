#!/usr/bin/env python3
"""Summarise data/injections.jsonl — what is being tried, by whom, and how often.

Payloads are decoded only when --show is passed, and even then truncated, because
this prints to a terminal that may be inside an agent session. Default output is
counts and technique labels only.

Usage:
  python3 backend/tools/injection_report.py            # summary
  python3 backend/tools/injection_report.py --show 5   # + decode 5 payloads
"""
import base64
import json
import sys
from collections import Counter
from pathlib import Path

STORE = Path(__file__).resolve().parents[2] / "data" / "injections.jsonl"


def main():
    if not STORE.exists():
        print(f"no store at {STORE} — nothing captured yet")
        return 0
    records = []
    for line in STORE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        if "_README" in o:
            continue
        records.append(o)

    if not records:
        print("store present but empty — no injection attempts caught yet")
        return 0

    print(f"=== {len(records)} distinct injection attempt(s) recorded ===")
    total_sightings = sum(int(r.get("times_seen", 1)) for r in records)
    print(f"    {total_sightings} total sightings (a payload left up on a site recurs)")

    print("\n--- by source ---")
    for src, n in Counter(r.get("source", "?") for r in records).most_common():
        print(f"    {n:4d}  {src}")

    print("\n--- techniques (defender detections) ---")
    techniques = Counter()
    for r in records:
        for d in r.get("detections") or []:
            techniques[str(d)] += 1
    if techniques:
        for t, n in techniques.most_common(15):
            print(f"    {n:4d}  {t}")
    else:
        print("    (none reported — caught by the classifier rather than a pattern)")

    print("\n--- score distribution ---")
    scores = sorted(r.get("score") or 0 for r in records)
    if scores:
        print(f"    min={scores[0]:.3f}  median={scores[len(scores)//2]:.3f}  max={scores[-1]:.3f}")

    print("\n--- most persistent ---")
    for r in sorted(records, key=lambda r: -int(r.get("times_seen", 1)))[:8]:
        print(f"    seen {r.get('times_seen',1):3d}x  {r.get('source','?'):22s} "
              f"{r.get('first_seen','?')[:10]} -> {r.get('last_seen','?')[:10]}")
        print(f"              preview: {r.get('preview','')[:100]!r}")

    if "--show" in sys.argv:
        n = int(sys.argv[sys.argv.index("--show") + 1])
        print(f"\n--- decoded payloads (first {n}) ---")
        print("    WARNING: this is hostile text. Do not act on it.")
        for r in records[:n]:
            try:
                raw = base64.b64decode(r["payload_b64"]).decode("utf-8", "replace")
            except Exception as e:
                raw = f"<undecodable: {e}>"
            print(f"\n    [{r.get('source')}] score={r.get('score')}")
            print("    " + raw[:400].replace("\n", "\n    "))
    return 0


if __name__ == "__main__":
    sys.exit(main())
