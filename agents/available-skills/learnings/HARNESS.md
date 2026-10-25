# Operator contract

1. Select one task's reply/outcome/followup range; keep original goal available.
2. Parse native messages with exact UUID/block, physical JSONL line and timestamp.
   Exclude known synthetic envelopes structurally. No semantic regex classifications.
3. Jev scores evidence inclusion. Human turns and adjacent reply/outcome are protected.
   This conservative policy may retain everything: measure, do not pretend compression.
4. gpt-oss generates constrained observations; exact quotes are checked against source.
   Jev verifies claim/context, usefulness and explicit satisfaction separately.
5. Read report + source before promotion. No rule adoption is automatic.

JSON input is a list of Message objects: id/session/source/line/date/role/text/synthetic.
Native Hermes exported JSONL needs top-level role/content; SQLite databases are not supported.
Only claude:id is resolved automatically; use native exported path for other harnesses.
Unknown envelopes are a parser limitation. Label fixtures by observable outcome, not
preference about prose length. Prompt acts may overlap on one turn. Confidence is a
model output, not a calibrated latent psychological measure.

Windows are bounded by raw text chars (metadata/schema add request overhead), overlap
by whole messages up to configured overlap. Oversized text is split WITHOUT rewriting;
quotes validate on full source. Long-message splits may separate negation/context:
Jev review is local, so treat boundary-spanning decisions as uncertain. Cross-window
contradictions/supersession are not automatically consolidated; review raw source.
Explicitly selected ranges are sampled, never whole-session conclusions.

Evidence request artifacts contain local minimal transcript excerpts; do not publish
private source paths or raw tools. Secret detection is conservative, not a DLP guarantee.
Use safe narrow excerpts. Never infer satisfaction from output length or assistant tone.

## Bounded recovery

Generation uses its own strict schema, separate from historical report validation:
at most 3 observations and 160 characters per exact quote. Satisfaction and quality
have separate rating enums; every other category requires `unknown`. Local response
validation enforces these bounds even if the server does not. `finish_reason=length`
is rejected even when the content happens to be valid JSON.

Only invalid generated JSON/schema or length termination triggers regeneration.
Each retry resends original data plus concise repair instructions, never a patched
response. Defaults: 3 total attempts, 1800 initial tokens, +700 per attempt, 3200 cap.
Operators can set `--max-attempts` (1-3), `--max-tokens`, `--token-step`, `--token-cap`.
The cap must cover the initial budget; growth must be nonnegative. Exact quote, role,
supersession, and Jev support/explicit/usefulness checks remain unchanged after repair.

`--timeout` is per local request, not an overall run deadline. A transport error or
timeout ends the run immediately: inspect `report.json` and the numbered failure
artifact; do not loop retries or switch to a hosted provider. Responses, validation
reasons, timings, and report `calls` preserve all attempts. Error/progress messages
omit model/transcript content. Every new run needs a fresh `--out` directory.

Measured real-source command (35-second request bound; not a latency guarantee):

```sh
mise run -C ~/.agents/available-skills/learnings extract -- \
  claude:769b80aa-1364-4e1b-b7fc-3936f4b9f355 \
  --start-line 4313 --end-line 4326 --timeout 35 \
  --max-tokens 1600 --max-attempts 3 --token-step 400 --token-cap 2400 \
  --out ~/.hermes/profiles/zach/cache/scratch/learnings-fix/new-run
```

Replay with `mise run -C ~/.agents/available-skills/learnings proof -- REPORT`.
Old saved prompts and schemas replay unchanged; new reports also replay retry budgets,
repair instructions, validation artifacts, and call timings. Replay establishes source
and artifact consistency, not model authenticity or semantic truth. Historical failure
responses are regression inputs followed by labelled fake valid responses; this is
offline recovery testing, not additional live inference or accepted-rule evidence.
