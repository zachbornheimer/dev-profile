---
name: learnings
description: Use when extracting lessons from a completed or corrected agent session, auditing lost goals or decision lineage, or comparing user satisfaction with independently evidenced output quality.
---

# learnings

Gotcha: hooks and teammate handbacks can appear as user turns. They are not user
approval. “Okay, proceed,” silence, and assistant self-praise establish no satisfaction.
Exact quotes establish provenance, not truth: Jev separately checks context and usefulness.

Run locally (Python 3.12, uv, mise; no API key):

```sh
mise run -C ~/.agents/available-skills/learnings setup
mise run -C ~/.agents/available-skills/learnings extract -- claude:769b80aa \
  --start-line 4300 --end-line 4335 \
  --out ~/.hermes/profiles/zach/cache/scratch/learnings/dev-profile-new
```

Native Claude/Hermes JSONL paths and normalized JSON also work. `--timeout`,
`--window-chars`, `--overlap-chars`, `--max-tokens` bound resources; calls are SERIAL.
Generation enforces <=3 observations, exact quotes <=160 characters, and category-valid
ratings. `--max-attempts` (1-3; default 3), `--token-step` (default 700), and
`--token-cap` (default 3200) bound whole-response regeneration. No JSON surgery,
rating coercion, or evidence truncation. Network/timeouts fail without automatic retry.
Use small reply + correction + followup ranges first. `--baseline` omits semantic
pruning, but retains identical generation and verification. No hosted fallback.

Read `report.json`: sampled observations, exact evidence IDs, source/line/date,
unknown ratings, uncertainty, supersession, typed Jev probabilities, retained sizes.
Private sanitized request/response artifacts accompany it. Possible secrets fail
before inference. Outputs remain local; tool excerpts should be minimal.
Every call's timing and failed generation validation appear in `calls`; raw failed
responses remain in their numbered artifacts. Historical reports retain their original
schema/prompt; `mise run -C ~/.agents/available-skills/learnings proof -- REPORT`
replays exact saved requests, including deterministic regeneration, without inference.

Thresholds are experimental, not calibrated: 0.5 pruning, 0.85 support/explicit,
0.8 usefulness. `review-candidate` means review it, NOT a validated global rule.
Failures return nonzero + failed/unknown report, never accepted rules. Overlapping
windows preserve raw text, but cross-window contradictions need manual source review.
Do not claim measured improvement without held-out labels split by SESSION.

No automatic cm, hooks, memory, or global-policy mutation. Promote only after review.
Workflow and limitations: [HARNESS.md](HARNESS.md).
Research: [references/research.md](references/research.md).
Measured runs and failures: [references/experiments.md](references/experiments.md).
