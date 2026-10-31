---
name: diagnose
description: Use when a live system is wedged, hung, slow, flapping, returning 5xx, or otherwise misbehaving and the next step is diagnosis rather than a code change. Load before restarting, killing, or applying a guessed fix. Also when the user says diagnose, differential diagnosis, why is this wedged, trace this failure, collect diagnostic data, or /diagnose.
user-invokable: true
---

# Diagnose

Rule hypotheses **out**. After Snapshot, TypeSafe picks the next move. Horses first.

## REQUIRED SUB-SKILL

`typesafe-ai` — load it. Live docs are source of truth for API shape.

## When not this

| Need                                           | Use instead      |
| ---------------------------------------------- | ---------------- |
| Bug in code or design; structural fix          | `debug-protocol` |
| How does X work; evidence-backed answer        | `investigate`    |
| PagerDuty/Sentry page; enrich then disposition | `oncall`         |
| Prove a change worked                          | `verify`         |
| Add or fix telemetry                           | `observability`  |

This skill finds the live-system cause. After the cause is proven, `debug-protocol` then `verify`.

## The loop

**Symptom → Snapshot → Map → Differential → TypeSafe next move.** Repeat. One action per turn.

1. **Symptom.** One sentence from the user's view. Not the cause.
2. **Snapshot.** Capture state before any mutation. Timeout every probe. A hang is the finding. Never restack a hung command.
3. **Map.** If the repo has `docs/failure-domains.md` or runbooks, that map is the prior. Else: the service, its deps, the last change.
4. **Differential.** Falsifiable hypotheses. A claim you cannot disprove is not a hypothesis. Publish the board every turn.
5. **Next move.** Write board JSON. Run `python3 <this-skill>/scripts/next_move.py --board board.json`. Execute only the returned `do`. Derive the script path from this SKILL.md directory, not cwd. Do not rank tests in prose.

Stop-the-bleed only when `do` is `mitigate`. Guessed restart is not mitigation.

Board fields, `do` values, and composition gates: `references/typesafe.md`. Catalog: the script.

## Snapshot

Timeout every probe (start at 5–10s; raise only with a reason). A hang is the finding; do not stack a duplicate. Record: time, host, pid, load, disk, mem, fds, recent change, one targeted log query.

Do not: restart, kill, dump all logs, `tail -f` without a bound, rerun the command that already hung.

## Differential board (every turn)

```text
Symptom: <one sentence>
Ruled out: <H> — <test that killed it>
Still open:
  1. <H>
  2. <H>
Next: <do from next_move.py>  test: <test_id>  layer: <layer>
Mitigation: none | <reversible action, proven why>
```

## Horses

Priors for filling board `open` hypotheses and candidate `tests`; TypeSafe / `next_move.py` still picks `do`.

1. What changed (deploy, config, cert, schema, flag, DNS).
2. A dependency, not the service you are staring at.
3. Saturation: disk, mem, fds, locks, queues, wedged mount.
4. DNS / TLS / clock / auth.
5. Hung client, leftover namespace, wrong probe target.
6. The probe itself.

## Trace one request

Pick one failing request. Follow it hop by hop (time-division: total latency = sum of sync parts; the largest unexplained slice is next). Targeted query, not a log dump. Method checklists: `references/methods.md`.

## Gotchas

| Default                                 | Instead                                                                                  |
| --------------------------------------- | ---------------------------------------------------------------------------------------- |
| Restart / kill first                    | Snapshot. Restart only as proven reversible mitigation.                                  |
| CLI hung ⇒ daemon dead                  | Timeout is a finding about the _probe_. Check the process independently.                 |
| Slow = stuck                            | Measure progress (CPU, WAL, counters) before intervening.                                |
| Correlation = causation                 | One falsifying test. Co-timed events are a hypothesis.                                   |
| Check everything sequentially           | One group-killing test. Split-half the remaining set.                                    |
| Last time was X                         | Board starts from this snapshot, not last week's cause.                                  |
| More logs                               | Targeted query for the one request / one window.                                         |
| Ranking in prose / "I'll just pick NFS" | `next_move.py`. It resolves the key from env, keychain, then 1Password. No LLM fallback. |

## After the cause

Hand off to `debug-protocol` for the structural fix, then `verify` (sustain the end-state; two clean samples is the floor). Do not declare healthy on one favorable reading.

Sources: `references/sources.md`.
