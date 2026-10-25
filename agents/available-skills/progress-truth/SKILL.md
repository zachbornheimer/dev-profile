---
name: progress-truth
description: Load before reporting progress on long-running or autonomous work (an overnight run, a delegated pipeline, a convergence system), before arming any monitor/watcher, and before saying "things changed / landed / is working." Use when the deliverable is "is this making progress?" — it forces outcome metrics over activity proxies.
---

# Progress Truth

Born from a real failure (2026-07-13): an agent reported an overnight run as a chain
of wins — merges, green tests, stable labels — while the system's merge engine had
been dying at a timeout **every hour for 8 hours** and throughput was 3 merges
against an expected 16+. Every reported fact was true. The report was still
misleading. These rules prevent that class of failure.

## The one rule

**Report progress in the user's outcome metric, or say you don't have it.**
Before any progress claim, answer: _what is the number the user would check, what is
it now, what was it N hours ago, and what should it be?_ If you can't fill those
four slots from tool results, your report opens with "I have not measured the
outcome" — not with wins.

## Gotchas (the defaults that produced the failure)

- **Activity is not progress.** PRs opened, tests green, labels stable, workers
  completed — all inputs. The outcome was "backlog drains ≥2/hr sustained." Never
  let proxies headline a report; put them under the outcome number, never in place
  of it.
- **Watch the engine, not the passengers.** Monitoring N hand-picked work items
  misses the machine that moves them. If throughput depends on a sweep/cron/queue
  worker, one watcher must cover _that process's_ completion status (its runs
  finishing green), or the whole watch is decorative. Ask: "if the engine died right
  now, which of my monitors fires?" If none — arm one before reporting anything.
- **Silence is ambiguous; make it impossible.** Transition-based watchers (fire on
  change) read "nothing happened" as patience. On a system that _should_ produce
  events at a known rate, arm a **dead-man's switch**: an event when the expected
  thing does NOT happen within its cadence (no merge in 2h, no run success in 90min).
  Absence-of-signal must be a signal.
- **A handoff is a claim, not a fact.** "It's in the system's hands now" requires
  verifying the system is alive _at handoff time_ (its last N runs succeeded), plus
  a liveness watcher for after. Handing work to a dead engine while narrating
  confidence is the deception mode — no single statement is false, the frame is.
- **Rate-check against the user's expectation.** If the user's mental model is
  "X/hour", compute expected-vs-actual for the elapsed window in every report.
  "3 happened" hides what "3 of an expected 16" states.
- **When woken up after time away ("has anything changed?"), compute the outcome
  delta FIRST** — backlog count now vs then, merges in window, engine run health —
  before mentioning any individual wins. Lead with the delta even (especially) when
  it's bad.

## Report template (any long-running progress report)

1. **Outcome:** metric now vs N hours ago vs target. One line.
2. **Engine health:** last success of each driving process; anything dead or dying.
3. **Wins:** individual items landed (only after 1 and 2).
4. **Watchers armed:** what fires if the engine dies or the rate drops — name the
   dead-man's switch explicitly.
