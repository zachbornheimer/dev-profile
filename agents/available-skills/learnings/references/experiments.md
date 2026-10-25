# Local experiment results

Nine local invocations: {'failed': 3, 'completed': 6}; completed windows cover 3 distinct real Claude sessions.

| Run                   | Result    | Review candidates | Saved response seconds |
| --------------------- | --------- | ----------------: | ---------------------: |
| dev-profile-1         | failed    |                 0 |                   45.9 |
| dev-profile-2         | completed |                 0 |                 22.849 |
| agentmux-live-3       | completed |                 0 |                 24.572 |
| zq-live-4             | completed |                 0 |                 53.766 |
| agentmux-baseline-5   | completed |                 0 |                 13.553 |
| agentmux-revised-6    | completed |                 3 |                 42.641 |
| dev-profile-revised-7 | failed    |                 0 |                 20.328 |
| dev-profile-revised-8 | failed    |                 0 |                 18.804 |
| dev-profile-bounded-9 | completed |                 0 |                 22.387 |

## What changed

Initial consolidation paraphrased events and mislabeled assistant behavior as user prompt style. A RED test proved assistant-only prompt-act evidence was accepted; the guard now requires human evidence. Consolidation instructions now distinguish reconstructed goals from accepted goals, request actionable lessons, and bound observation/quote lengths. Historical proof replays the saved prompt version, not the latest prompt.

The revised AgentMux run produced three review candidates: user prompting act, task family, and a scoped lesson to confirm intended outcome before edits when implementation was withheld. Satisfaction and measured quality remain unknown. Thresholds were not lowered.

Three failed runs were preserved: schema/JSON/output failures. The final bounded dev-profile rerun completed but all candidates remained below the gate. Model instructions are not guarantees; schema and quote checks fail closed.

The initial AgentMux pruning run retained all 325 input characters and recorded 24.572 seconds across responses. Its no-pruning baseline also retained all 325 and recorded 13.553 seconds. These small windows do not demonstrate compression benefit. Revised extraction changed prompt/output budget, so it is not a controlled quality comparison.

All inference used local Ollama endpoints: Jev System One pruning/verification and GPT-OSS consolidation. No hosted fallback. The raw reports and requests/responses live under `~/.hermes/profiles/zach/cache/scratch/learnings/`; summary: `experiment-summary.json`.

This is a feasibility experiment, not a calibrated satisfaction model. More complete contextual windows and independent session-level labels are required before automatic rule promotion.

## Bounded recovery verification (2026-10-14)

Generation now enforces <=3 observations, <=160-character quotes and category-valid
ratings independently of historical reports. Invalid schema/JSON or a length finish
regenerates the whole response with bounded attempts and token growth. Nothing repairs
or coerces evidence; the original quote/role and Jev gates still decide disposition.

Actual serial local runs under `~/.hermes/profiles/zach/cache/scratch/learnings-fix/`:

| Run                         | Result                                    | Calls | Total recorded call seconds |
| --------------------------- | ----------------------------------------- | ----: | --------------------------: |
| dev-profile-current         | prune ReadTimeout                         |     1 |                      35.053 |
| dev-profile-warm            | consolidation ReadTimeout                 |     2 |                      60.241 |
| counterfactual-live         | completed                                 |     3 |                      46.748 |
| dev-profile-bounded-current | completed; role gate rejected candidate   |     2 |                      27.448 |
| dev-profile-verified        | completed with actual schema-regeneration |     4 |                      51.997 |

All used a 35-second per-request timeout. The final real Claude window 4313-4326
used 1600 initial tokens, +400 growth, 2400 cap, 3 maximum attempts. The first
GPT-OSS response failed validation; the second passed. Jev then scored support
0.9770, usefulness 0.3775 and explicit 0.9526. The candidate remained rejected at
the unchanged 0.8 usefulness threshold. No review candidates or accepted rules
resulted in any new run. Satisfaction and quality stayed unknown.

The labelled normalized counterfactual contains `okay proceed` and assistant
self-praise, with no tool evidence. Its sole prompt-act candidate was rejected
for usefulness (0.2451); satisfaction and measured quality remained unknown.
This is one counterfactual, not a calibrated evaluation dataset.

The real window retained all 807 characters; the counterfactual retained all 59.
These tiny windows show no compression savings. Pruning cost remains visible.
Current retry-sequence proof and counterfactual proof passed; historical default,
dev-profile-bounded-9 and agentmux-revised-6 replay also passed without rewriting
their artifacts. Reading the last historical fixture does not invoke AgentMux.

Regression first reproduced truncated JSON, oversized quotes, category-invalid
ratings, ignored length termination and exhaustion; saved historical failures
dev-profile-1/revised-7/revised-8 also reproduced before the fix. Separate fake
sequence tests verify bounded recovery, timeouts/no fallback, unchanged evidence
gates, exact saved retry requests, timing tampering and missing validation artifacts.
These test responses are explicitly fake and never counted as live results.
