# Self-Improve Schedule

## Recommended cadence

**Weekly — every Monday before the work week starts.**

Rationale: corrections accumulate over 5–7 working days, giving enough distinct
events to distinguish a real pattern from a one-off. Daily runs produce too little
signal per run (the ≥ 3 threshold becomes unreachable). Monthly runs let patterns
blur; by the time they surface, the context that would help you evaluate them is
gone.

## Wiring with /schedule

### Minimal (harvest + summarize only)

```text
/schedule every Monday at 6am: run the self-improve skill — harvest the last 7 days of corrections across all tools, cluster by theme, and show me a summary of recurring patterns with their frequencies. Do not auto-apply anything.
```

### Full adversarial pipeline

```text
/schedule every Monday at 6am:
  /goal: mine the last 7 days of corrections with
  `uv run /Users/zbornheimer/.claude/skills/self-improve/scripts/harvest-corrections.py --days 7`,
  cluster into thematic buckets with parallel subagents, adversarially verify each
  cluster (≥3 threshold, check against existing CLAUDE.md and skills/ rules), and
  present a proposed unified diff for surviving candidates — one diff, ready to
  review. Do not stop until the diff is ready or no candidates survive the gate.
  Turn limit: 25.
```

The cloud routine runs even when your laptop is closed. Per-run output appears in
Claude Code notifications when you next open a session.

## The human-approval gate

The loop always stops before applying changes. The commit sequence is:

1. Harvester emits candidates to stdout → cluster subagents summarize
2. Skeptic subagents kill one-offs and duplicates of existing rules
3. Surviving candidates become a `proposed.patch` unified diff
4. You review, then apply:

```bash
patch -p1 < proposed.patch        # apply
# or edit the diff and apply manually
```

Auto-application is not permitted under any configuration. The model's judgment
on "this is a real pattern" is a necessary but not sufficient input — yours is the
final gate. Rules that land without your eyes are rules you didn't actually adopt.

## Adjusting the look-back window

Pass `--days N` to `harvest-corrections.py`:

| Value       | Use case                               |
| ----------- | -------------------------------------- |
| `--days 7`  | Weekly cadence (default)               |
| `--days 30` | First run, or after a long gap         |
| `--days 1`  | Ad-hoc "what went wrong today"         |
| `--days 90` | Quarterly sweep for slow-burn patterns |

## On-demand invocation

Run anytime outside the schedule:

```bash
uv run /Users/zbornheimer/.claude/skills/self-improve/scripts/harvest-corrections.py --days 30 \
  > /tmp/corrections-$(date +%F).ndjson

# Then drive the cluster + verify pipeline with the self-improve skill:
# "cluster and adversarially verify /tmp/corrections-YYYY-MM-DD.ndjson"
```

## What the gate rejects (and why)

The ≥ 3 distinct-corrections threshold is not arbitrary. In practice, harvested
corrections include:

- **Context-specific instructions** (one repo, one day) — real but not general
- **Already-covered patterns** — the rule exists; the model just broke it
- **Phrasing variants** — "don't" and "please don't" are the same rule
- **Genuine new patterns** — the only survivors worth proposing

The adversarial skeptic handles the first three. The threshold handles noise. Both
must clear before a proposed diff is generated.
