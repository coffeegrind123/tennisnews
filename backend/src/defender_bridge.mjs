#!/usr/bin/env node
/*
 * defender_bridge.mjs — long-lived stdin/stdout JSONL host for
 * @stackone/defender, spawned by scrape.py once per scrape run.
 *
 * Why a bridge: defender is a TypeScript/Node package, the scraper is
 * Python. Per-doc subprocess spawn would re-load defender's 22MB ONNX
 * model from scratch on every call (200ms+) which is wasteful when we
 * have many docs to scan. One long-lived Node process keeps the model
 * resident; Python pipes JSONL in, reads JSONL out, closes stdin when
 * done, the Node process exits cleanly.
 *
 * Protocol (line-delimited JSON, UTF-8):
 *
 *   stdin  ← {"id": <int>, "md": "<markdown body>", "source": "<slug>"}\n
 *   stdout → {"id": <int>, "allowed": <bool>, "riskLevel": "<low|medium|high|critical>",
 *             "tier2Score": <number>, "detections": [<string>...],
 *             "patternsByField": {...}, "fieldsSanitized": [...]}\n
 *
 * One readiness line is emitted before stdin reads begin:
 *   stdout → {"ready": true, "modelLoaded": <bool>}\n
 *
 * On any unhandled error a single-line {"error": "<msg>", "fatal": true}
 * goes to stdout and the process exits 1 — Python should treat that as
 * defender-side failure (default: skip writing the doc; never silently
 * pass an unscanned doc through).
 *
 * Logging: anything diagnostic goes to stderr so it doesn't pollute the
 * JSONL stream Python consumes from stdout.
 */

import { createInterface } from "node:readline";
import { createPromptDefense } from "@stackone/defender";

// Config:
//   - tier1: pattern detection + sanitization (sync, fast)
//   - tier2: ML classifier (async, 22MB ONNX, ~10ms after load)
//   - blockHighRisk: true — flips `allowed=false` for high/critical risk
//   - tier2Config.highRiskThreshold: 0.85 — MEASURED for this corpus, not
//     inherited. The sbox-learn-docs mirror runs 0.95 because it scans long
//     imperative tutorial prose that shares surface features with injection.
//     News headlines do not, and the separation here is enormous:
//
//       522 real scraped articles : median 0.052, p95 0.141, MAX 0.778
//       known-attack controls     : 0.939 - 0.963
//
//     0.85 sits in that gap with margin both ways: zero false positives across
//     the whole real corpus, and it catches all four controls. At the inherited
//     0.95 three of the four attacks passed — role markers (0.939), ChatML tags
//     (0.947) and tool-redirects (0.945) — which is the exact weakness the sbox
//     bridge documents. Re-measure with backend/tools/calibrate_defender.py if
//     the source mix changes; the number to protect is the gap, not 0.85 itself.
//
// We do NOT enable `annotateBoundary` (which wraps content in [UD-…] tags)
// because the text is rendered into public/index.html and the JSON API —
// boundary tags would corrupt the displayed headline. Tier 1 sanitization
// (role-marker stripping, instruction-override redaction) still happens.
const defense = createPromptDefense({
  blockHighRisk: true,
  tier2Config: {
    highRiskThreshold: 0.85,
  },
});

// Warm up the ML model up-front so the first real doc doesn't pay the
// 200ms cold-start. Best-effort — if the warmup throws we still proceed
// and the first defendToolResult() call will load on demand.
let modelLoaded = false;
try {
  await defense.warmupTier2();
  modelLoaded = true;
} catch (e) {
  process.stderr.write(`[defender_bridge] warmup failed (non-fatal): ${e?.message || e}\n`);
}

// Emit readiness so Python doesn't race the first write.
process.stdout.write(JSON.stringify({ ready: true, modelLoaded }) + "\n");

const rl = createInterface({ input: process.stdin });

rl.on("line", async (raw) => {
  if (!raw.trim()) return;
  let req;
  try {
    req = JSON.parse(raw);
  } catch (e) {
    process.stdout.write(
      JSON.stringify({ id: null, error: `bad json: ${e?.message || e}` }) + "\n",
    );
    return;
  }

  const id = req.id ?? null;
  const md = req.md;
  const source = req.source ?? "tutorial";

  if (typeof md !== "string") {
    process.stdout.write(
      JSON.stringify({ id, error: "missing or non-string `md` field" }) + "\n",
    );
    return;
  }

  try {
    // The source identifier shows up in defender's structured detections
    // (e.g. patternsByField keys). Use the tutorial slug so blocked-doc
    // logs back in Python read naturally.
    const result = await defense.defendToolResult(md, source);
    process.stdout.write(
      JSON.stringify({
        id,
        allowed: result.allowed,
        riskLevel: result.riskLevel,
        tier2Score: result.tier2Score ?? null,
        detections: result.detections ?? [],
        patternsByField: result.patternsByField ?? {},
        fieldsSanitized: result.fieldsSanitized ?? [],
      }) + "\n",
    );
  } catch (e) {
    process.stdout.write(
      JSON.stringify({
        id,
        error: `defendToolResult threw: ${e?.message || e}`,
      }) + "\n",
    );
  }
});

// Stdin closes => Python is done; exit cleanly.
rl.on("close", () => {
  process.exit(0);
});

// Surface unexpected crashes so Python sees them and can abort the scrape
// instead of silently letting unscanned docs through.
process.on("uncaughtException", (err) => {
  process.stdout.write(
    JSON.stringify({ error: `uncaughtException: ${err?.message || err}`, fatal: true }) + "\n",
  );
  process.exit(1);
});
process.on("unhandledRejection", (err) => {
  process.stdout.write(
    JSON.stringify({ error: `unhandledRejection: ${err?.message || err}`, fatal: true }) + "\n",
  );
  process.exit(1);
});
