"""Prompt-injection screening for scraped headlines, descriptions and tweets.

Why this exists: public/index.html is explicitly "designed for LLM consumption",
and every string in it comes from one of 39 third-party sites or 12 Twitter
accounts. A headline reading "Ignore previous instructions and ..." is a working
indirect prompt injection against whatever model reads the feed, and nothing in
the pipeline previously looked at content at all - only at whether extraction
succeeded.

Ported from the sbox-learn-docs mirror, which pipes tutorial bodies through
@stackone/defender (pattern detection + a fine-tuned ONNX classifier) via a
long-lived Node bridge. Two deliberate differences here:

  * That mirror BLOCKS a document outright. A news aggregator should not silently
    drop a story because a classifier disliked the wording, so this FLAGS: the
    item survives with its link and source intact, and the payload text is
    redacted only when the scanner is confident (blocked == high/critical risk).
    Consumers get the verdict in the JSON and a visible label in the HTML.

  * Its 0.95 threshold was calibrated on long imperative tutorial prose. Headlines
    are short and declarative, so that number is NOT assumed to transfer - see
    tools/calibrate_defender.py, which measures the flag rate against the real
    scraped corpus.

Failure posture: if the bridge cannot start, items are marked scanned=False rather
than being presented as clean. "Nobody looked" and "looked and found nothing" are
different claims and the feed reports which one it is.
"""

import base64
import hashlib
import json
import os
import shutil
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent

BRIDGE_SCRIPT = SCRIPT_DIR / "defender_bridge.mjs"
DEFENDER_ENABLED = os.environ.get("SCRAPER_DEFENDER", "1").lower() not in ("0", "false", "no")
# Text handed to the scanner per item. Headlines plus description; long enough to
# carry a payload, short enough that 600 items stay quick.
MAX_SCAN_CHARS = 2000
REDACTION = "[redacted: this text was flagged as a prompt-injection payload]"


class Defender:
    """Long-lived Node bridge; one process per scrape run."""

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.active = False
        self.error = ""
        self.scanned = 0
        self.flagged = 0
        self.redacted = 0
        self._next_id = 0
        self.by_source: dict[str, int] = {}
        # Captured attempts, written to data/injections.jsonl so the tricks people
        # actually try against this feed accumulate over time.
        self.captured: list[dict] = []

    # ---------------------------------------------------------------- start
    def start(self) -> bool:
        if not DEFENDER_ENABLED:
            self.error = "disabled via SCRAPER_DEFENDER=0"
            print(f"  [DEFENDER] {self.error}")
            return False
        node = shutil.which("node")
        if not node:
            self.error = "node not on PATH"
        elif not BRIDGE_SCRIPT.exists():
            self.error = f"bridge script missing at {BRIDGE_SCRIPT}"
        if self.error:
            print(f"  [DEFENDER] UNAVAILABLE ({self.error}) - items will be marked unscanned")
            return False

        try:
            self.proc = subprocess.Popen(
                [node, str(BRIDGE_SCRIPT)], cwd=BACKEND_DIR,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                bufsize=1, text=True, encoding="utf-8",
            )
        except Exception as e:
            self.error = f"spawn failed: {type(e).__name__}: {e}"
            print(f"  [DEFENDER] UNAVAILABLE ({self.error})")
            return False

        def _drain():
            for line in self.proc.stderr:  # type: ignore[union-attr]
                print(f"  [DEFENDER] stderr: {line.rstrip()}")

        threading.Thread(target=_drain, daemon=True).start()

        ready_line = self.proc.stdout.readline()  # type: ignore[union-attr]
        if not ready_line:
            self.error = "bridge exited before readiness (is `npm install` done in backend/?)"
            print(f"  [DEFENDER] UNAVAILABLE ({self.error})")
            self.proc = None
            return False
        try:
            ready = json.loads(ready_line)
        except Exception as e:
            self.error = f"malformed readiness line {ready_line!r}: {e}"
            print(f"  [DEFENDER] UNAVAILABLE ({self.error})")
            self.proc = None
            return False
        if not ready.get("ready"):
            self.error = f"unexpected readiness line {ready_line!r}"
            print(f"  [DEFENDER] UNAVAILABLE ({self.error})")
            self.proc = None
            return False

        self.active = True
        print(f"  [DEFENDER] ready (modelLoaded={ready.get('modelLoaded')})")
        return True

    # ----------------------------------------------------------------- scan
    def _scan(self, text: str, source: str) -> dict | None:
        if not self.active or not self.proc:
            return None
        self._next_id += 1
        req = {"id": self._next_id, "md": text[:MAX_SCAN_CHARS], "source": source}
        try:
            self.proc.stdin.write(json.dumps(req) + "\n")  # type: ignore[union-attr]
            self.proc.stdin.flush()  # type: ignore[union-attr]
            line = self.proc.stdout.readline()  # type: ignore[union-attr]
        except Exception as e:
            self.active = False
            self.error = f"bridge write/read failed mid-run: {type(e).__name__}: {e}"
            print(f"  [DEFENDER] {self.error} - remaining items unscanned")
            return None
        if not line:
            self.active = False
            self.error = "bridge closed mid-run"
            print(f"  [DEFENDER] {self.error} - remaining items unscanned")
            return None
        try:
            return json.loads(line)
        except Exception:
            return None

    def screen(self, item: dict, text_fields=("title", "description")) -> dict:
        """Screen one article/tweet in place. Adds an `injection` record."""
        joined = "\n".join(str(item.get(f) or "") for f in text_fields).strip()
        if not joined:
            item["injection"] = {"scanned": False, "reason": "no text"}
            return item

        source = item.get("source_name") or item.get("handle") or "unknown"
        res = self._scan(joined, str(source))
        if res is None or "error" in res:
            item["injection"] = {
                "scanned": False,
                "reason": self.error or (res or {}).get("error", "scan unavailable"),
            }
            return item

        self.scanned += 1
        allowed = bool(res.get("allowed", True))
        risk = res.get("riskLevel", "unknown")
        detections = res.get("detections") or []
        record = {
            "scanned": True,
            "risk": risk,
            "score": res.get("tier2Score"),
            "detections": detections[:6],
        }

        if not allowed:
            # High/critical confidence: neutralise the payload but KEEP the item,
            # so the feed still shows that this source published something and a
            # reader can follow the link to judge for themselves.
            self.flagged += 1
            self.redacted += 1
            self.by_source[str(source)] = self.by_source.get(str(source), 0) + 1
            # Capture the attempt BEFORE redacting - the payload is the evidence.
            #
            # Stored base64 rather than plaintext: this repo is public and its whole
            # purpose is LLM consumption, so a corpus of live injection payloads
            # sitting in readable text is itself an ingestion hazard for anything
            # crawling the repo. b64 keeps it exact and analysable while making
            # accidental ingestion a deliberate act. `preview` stays plaintext but
            # truncated, for human triage.
            self.captured.append({
                "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source": str(source),
                "source_url": item.get("source_url", ""),
                "link": item.get("link", ""),
                "risk": risk,
                "score": res.get("tier2Score"),
                "detections": detections,
                "patterns": res.get("patternsByField") or {},
                "fields": [f for f in text_fields if item.get(f)],
                "payload_b64": base64.b64encode(joined.encode("utf-8")).decode("ascii"),
                "preview": joined[:200].replace("\n", " "),
                # Identity for dedup: the same payload from the same URL should not
                # append a fresh record on every run.
                "fingerprint": hashlib.sha256(
                    (str(item.get("link", "")) + "|" + joined).encode("utf-8")
                ).hexdigest()[:16],
            })
            for f in text_fields:
                if item.get(f):
                    item[f] = REDACTION
            record["redacted"] = True
        # NOTE: do NOT branch on riskLevel. defender reports "medium" for almost
        # everything, including headlines scoring 0.03 - keying off it flagged
        # 100% of a 582-item corpus. `allowed` (driven by the calibrated 0.85
        # score threshold) is the signal; riskLevel is recorded for context only.

        item["injection"] = record
        return item

    # ----------------------------------------------------------------- stop
    def stop(self) -> dict:
        if self.proc:
            try:
                self.proc.stdin.close()  # type: ignore[union-attr]
                self.proc.wait(timeout=10)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None
        summary = {
            "available": self.active or self.scanned > 0,
            "error": self.error,
            "scanned": self.scanned,
            "flagged": self.flagged,
            "redacted": self.redacted,
            "by_source": dict(sorted(self.by_source.items(), key=lambda kv: -kv[1])),
            "captured": len(self.captured),
        }
        self.active = False
        return summary
