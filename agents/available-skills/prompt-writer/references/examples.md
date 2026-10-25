# Worked examples

Loose ask on the left, finished order on the right. Every required slot is filled.

## Dictated mess (execution-process)

Loose ask: "use the execution process I want a skill that makes our labor prompts
much less shitty, look at how the harness actually invokes them and use current
model guidance"

Work order:

- intent: prompt-writer compiles dictated/messy labor requests into lean
  outcome-first work orders that match how this harness actually dispatches
  workers, using current official model guidance rather than prompting folklore
- target: `prompt-writer/SKILL.md` and `references/`; thin `execution-process`
  alias if slash-invocation needs its own name
- blast-radius: do not fold execute+verify into prompt-writer (those stay
  orchestrator + `verify`); do not rewrite unrelated skills; do not research
  prompt folklore on every invocation
- inputs: current `prompt-writer/SKILL.md`; how the harness lists/invokes skills;
  OpenAI/Anthropic current official guidance (research gate: freshness matters)
- done-when: `rg -n 'If this skill was invoked as' ~/.claude/skills/prompt-writer/SKILL.md`
  prints nothing in-transcript; `rg -n 'Then \*\*do the work\*\*' ~/.claude/skills/execution-process/SKILL.md`
  shows a match; `rg -n '/execution-process' ~/.claude/skills/prompt-writer/SKILL.md`
  does not match the YAML `description:` line; `rg -n 'Invented intent' ~/.claude/skills/prompt-writer/references/adversary.md`
  shows a match
- verify-how: run those four `rg` commands; a compile-only handoff must not load
  `verify`
- model: sonnet, effort: default
- isolation: worktree
- turn cap: 20, token budget: ~40k

## Bug fix

Loose ask: "the plan-rank calc is off for the senior-life product, go fix it"

Work order:

- intent: correct plan-rank calculation for senior-life so Go output matches Perl
- target: `go/zyins/engine/checks/selfmodifying/` (rank logic), test in `models/`
- blast-radius: senior-life rank path only; don't touch other products' rank
  logic or the check-dispatch framework
- inputs: `CONSISTENCY_CASE=<failing case #>` trace output; the four-stage
  parity-debugging protocol in project `CLAUDE.md`
- done-when: a test proven RED against the bug (asserts the correct rank) passes
  GREEN after the fix, AND `go test ./models/... -run TestConsistency -count=1`
  shows zero senior-life rank diffs
- verify-how: run the named test, capture red-then-green; re-run the consistency
  case and confirm the diff is gone
- model: sonnet, effort: default
- isolation: worktree
- turn cap: 20, token budget: ~40k

## Read-only explanation

Loose ask: "how does the eapp builder actually publish a schema to production"

Work order:

- intent: a written explanation of the schema-publish path from builder save to
  production `everest.json`, so we know where to add a new capability
- target (read-only): `eapp-system/` — builder save handlers, publish job, S3/CDN
  write step
- blast-radius: none (read-only; no edits)
- inputs: start from `eapp-system/app/Http/Controllers` publish-related
  controllers; note prior finding in memory `eapp_builder_capability_gaps`
- done-when: a summary answering (1) what triggers a publish, (2) what
  transforms the schema, (3) where the artifact lands, (4) how staging vs prod
  differ — each claim cites a file:line
- verify-how: spot-check two cited file:line claims against the actual source
- model: sonnet (explore agent), effort: default
- isolation: none (read-only, no worktree needed)
- turn cap: 15, token budget: ~25k

## Adversarial review

Loose ask: "review the carrier-echo PR before I merge it, I don't fully trust it"

Work order:

- intent: an adversarial, skeptic-tuned review of the carrier-echo PR that finds
  real defects before merge, not a rubber stamp
- target: PR #<n> in `eapp-system` (or the named repo) — full diff
- blast-radius: read-only review; any fix goes back to the PR author, not
  applied directly by the reviewer
- inputs: the PR diff, linked ticket, `pr-review` skill, prior finding
  `carrier-echo-three-layer-debug`
- done-when: a verdict (APPROVE / REQUEST CHANGES) with every finding tagged
  MAJOR/MINOR/LOW and a file:line citation; for REQUEST CHANGES, a proposed
  fix cycle per the `pr-review` skill's 3-cycle protocol
- verify-how: confirm every finding's file:line exists in the diff; confirm CI
  status was actually queried, not assumed
- model: sonnet (reviewer agent, fresh context), effort: default
- isolation: none (read-only)
- turn cap: 25, token budget: ~50k

## Mechanical fan-out

Loose ask: "go through all our repos and tell me which ones still have npm
lockfiles instead of pnpm"

Work order:

- intent: a table of every repo under `~/Developer/Software-Automation-Holdings/`
  with its lockfile type, so we know which repos still need the pnpm migration
- target: mechanical fan-out across all repos in that org folder — read
  `package-lock.json` / `pnpm-lock.yaml` presence only, no edits
- blast-radius: read-only; do not modify any lockfile or run install
- inputs: `~/Developer/Software-Automation-Holdings/` repo list (`ls -d */`)
- done-when: a script (not a per-repo agent turn) has produced a CSV of
  `repo,lockfile_type,last_modified` for every repo in the folder
- verify-how: spot-check 3 rows in the CSV against `ls` on the real repo
- model: haiku — the worker writes and runs a shell/Python script; no
  judgment calls needed per repo
- isolation: none (read-only sweep)
- turn cap: 10, token budget: ~10k
