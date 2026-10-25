# TypeSafe next move

Call after Snapshot, before any test, restart, or “I think it’s X”.

## Call

1. Write board JSON: `symptom`, `since`, `map`, `snapshot` (`facts`, `hangs`), `ruled_out`, `open`, `tests`, `mitigation`.
2. `python3 <this-skill>/scripts/next_move.py --board board.json` — path from this skill’s directory, not cwd.
3. Do only `do`. If `do` is `run_test`, run `command` for `test_id`.

`--print-request` prints the POST body and exits 0 (no network). Question catalog is in the script.

Key, never printed: `TYPESAFE_API_KEY`, then login keychain `typesafe-api-key`, then 1Password Personal item "Typesafe AI API key". Missing from all three → exit 2. No LLM fallback.

Live API: [docs.typesafe.ai/api.md](https://docs.typesafe.ai/api.md) — `POST /v1/systemone`, `model: jev-latest`. Noul is `{type,noul}` (no confidence). Choice is `{type,choice,probabilities,confidence}`.

## Read `do`

| `do`             | Action                                                            |
| ---------------- | ----------------------------------------------------------------- |
| `run_test`       | Run `command`. Timeout. A hang is the finding.                    |
| `snapshot_more`  | More facts. No test, restart, or cause.                           |
| `add_hypotheses` | Open set cannot explain the facts. Add horses, rewrite the board. |
| `declare_cause`  | One hypothesis fits. Hand off to `debug-protocol`.                |
| `mitigate`       | Proven reversible stop-the-bleed already on the board.            |

## Composition gates (code, not the model)

- `mitigate` and `mitigation_proven` < 0.7 → `run_test`
- `declare_cause` and max `fits__*` < 0.75 → `run_test`
- `run_test` and (`next_test` is `none` or confidence < 0.35) → `snapshot_more` if snapshot thin, else cheapest read-only test by `seconds`
- Never `mitigate` a guessed Colima/docker restart
