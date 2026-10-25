# TypeSafe in hooks: merge, budget, log

Question wording, primitives (Choice/Score/Noul), thresholds, and "code vs model" live in the
`typesafe-ai-effective-use` skill. This file holds only what is specific to agent-hooks.

## The shape: one owner hook, waves inside it

The dispatcher cannot sequence hooks. `HookSpec` has `name, command, events, agents, timeout, protocol, provides,
on_failure, shell, matcher, env` and nothing like `after`, `stage`, or `priority`. Every matching hook starts at once
and shares nothing, so a second hook cannot wait for the first hook's TypeSafe answer. A result cache would not help:
both hooks miss at the same instant. So "one request, then parallel follow-ups" has to live **inside one hook per
(event, state)**:

```text
owner hook for event E
  prefilter in code (event, length, loop guard, token count, regex)  -> return early, no request
  wave 1: ONE request      every question about the shared primary state, namespaced ids
  decide in code           per-rule threshold; if wave 1 settles it (block), stop here
  wave 2: N requests IN PARALLEL (threads, one total deadline)
                           only follow-ups that need a different state, or are conditional on wave 1 / a prefilter
  merge in code            strongest consequence wins; ONE reason naming every failed rule
  one JSONL row            answers per wave, decision, model, hop, question-set hash
```

Where a question goes:

1. **Same state as the primary:** wave 1, same request. The extra questions are nearly free.
2. **Different state** (`select_project`'s thread plus project list, a bare-prose check): its own request. Do not
   inflate wave 1's state to host it; large irrelevant state is a documented failure mode.
3. **Independent of wave 1's outcome and cheap:** start it at the same time as wave 1, not after. **Conditional**
   (only matters if wave 1 allows, or only past a prefilter): start it after wave 1. That skips the call when wave 1
   blocks and costs one round trip when it does not.
4. **Several follow-ups:** run them together in wave 2. Wall time is the slowest, not the sum.

Why an owner hook beats separate hooks:

- **One verdict, one reason.** The aggregator takes the reason from the first hook in plan order that has any reason,
  so two denying hooks lose one reason. An owner composes them.
- **Shared state is sent once** (judge-turn's state alone is about 5k tokens).
- **Conditional follow-ups skip their call** when wave 1 already decides.
- **One deadline, one fallback chain, one log row.** Each request can fall through to a different model on any hop
  error (402, 400, timeout; see Budgets), so fewer requests means less model skew.

It is **not** a latency win by itself: separate hooks already run in parallel, so wall time is the slowest hook, and
the docs' "12x cheaper, 10x faster" compares sequential calls with one batch, not this dispatcher. Measured Stop cost
is small (about 4.7k input tokens per judgment, fractions of a cent).

The risk: a merged request changes the state shape, so questions and thresholds calibrated on the old shape can
shift. Replay logged requests under the new shape and shadow-run before switching. A builder can still prefilter per
rule by omitting a rule's questions.

## Live example: Stop

`completion-gate.py` -> `TurnJudge` -> `typesafe.py judge-turn`: 12 questions over
`{final_message, user_request, history, evidence}`, one `block_kind`, one reason template per kind. That is the whole
Stop side: one wave-1 request, nothing to batch. (The separate clarity hook was deleted.)

To add a second Stop check later, apply the placement rules above. Same state: add its questions to this request.
Different state or conditional on `judge-turn` allowing: a wave-2 request behind a code prefilter. Either way:

- `TurnVerdict` carries one `block_kind`, and each kind has its own reason template and reject cap (completion chain
  cap 9). Composing two kinds into one reason is a product decision;
- a merged request can shift existing turn answers that gate real blocks (`defers_doable_work`,
  `user_withheld_action`), so replay logged requests under the new shape and diff answers per question, then
  shadow-run for several days logging both answer sets, with thresholds fixed beforehand (comments in `constants.py`);
- touch `turn_judge.py` (questions, `decide_turn`), `constants.py` (`TURN_*`), `completion_gate_turn_judge.py`
  (reason text), `test_turn_judge.py`, and the chezmoi sources of each.

## Prompt side: inventory and why dictation stays separate (measured 2026-10-22)

TypeSafe requests behind one UserPromptSubmit, from `capability run` usage and `hooks.log`:

**Stop side:** `clarity-gate.py` still exists but exits 0 at the top of `__main__` (no TypeSafe call); remove that
`sys.exit(0)` to re-enable. `dictation-rewrite.py` is live.

| hook                                                | calls                                                        | state                                   | note                                                                                                          |
| --------------------------------------------------- | ------------------------------------------------------------ | --------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `dictation-rewrite.py`                              | 1 request, 3 Noul, direct `systemone.ask`                    | the prompt (first 8000 chars)           | only after `tokuin` says > 500 tokens: 54 of 74 logged prompts never reached TypeSafe; 12 judged, 4 rewritten |
| `prompt-submit-capabilities.sh` -> `select_project` | 1                                                            | thread plus every project (up to 16 KB) | state unrelated to the others                                                                                 |
| same -> `suggest_skills_tools_and_mcp`              | 7 on a 698-candidate catalog (kind x 48 000-character batch) | the prompt                              | all `benefit::<name>` Noul, about 65k input tokens                                                            |
| same -> `identify_intent`                           | 1 generative split, then 1 request per part                  | part plus whole prompt                  | per-part state re-sends the whole prompt                                                                      |

Measured: a TypeSafe request takes about 0.65 s and they run in parallel, so `suggest` costs about 4.6 s of wall,
almost all of it the `capability` process start and catalog scan. The `--output xml` re-run that used to follow the
JSON call was a cache hit that still cost 2.7 s serially; the hook now makes the one XML call and derives the
`skill-picks` file from it.

Why the dictation questions are **not** folded into the suggest request: they share a state (the prompt) with it, but
(a) the two live in different hooks and so different processes: running the same `capability` call from both
starts two computations (no single-flight), and merging the hooks would couple a 15 to 40 s generative rewrite to the
fast context hook's timeout; (b) the `tokuin` prefilter keeps 73% of prompts off TypeSafe for dictation, and a
merged request would ask the three questions on every prompt; (c) the saving is one request on about 16% of prompts.
If a second prompt-level judgment ever needs the same prompt and fires on most prompts, extend the capability
request (one `request` state, namespaced question ids) rather than adding a caller.

In wave terms the prompt side is already shaped like the pattern, just spread over two processes: `suggest`'s 7
requests and `select_project` run concurrently inside one `capability` call, and `identify_intent` is a wave 1 (the
generative split) followed by a parallel wave 2 (one request per part). The two real gaps are not missing waves:
the wave-2 requests re-send the whole prompt as state, and the split wave hangs (below).

Open defects found while measuring (not TypeSafe): `identify_intent` fails on every prompt (its generative split
call to `openrouter/qwen/qwen3.8-27b` never answers: 15 s and 90 s timeouts, while a plain chat request to the
same model returns in 1.7 s), so the hook waits its whole 20 s wall for no Intent line. Stop gate:
`completion-gate-judgments.jsonl` shows 1 853 of 17 788 judgments unavailable (http 402 and 400 hops, missing CLI,
missing key).

## Budgets and failure

- The client walks a fallback chain: OpenRouter (`typesafe/jev-1.14`), hosted `api.typesafe.ai`, local Ollama
  (`jev-1.13.0:latest`), each with its own per-hop timeout (turn judge 5 s, default 2 s). Budget a
  **total deadline across hops**, below the hook's `timeout`, below the native timeout (`timeout` + 2 s).
  `TurnJudge` kills its subprocess at 9 s inside a 15 s hook.
- A native hook timeout is fail-open, so a slow TypeSafe call silently disables the gate. Log the fallback reason.
- Fallback skew: `systemone.ask` falls through to the next hop on any hop error (the log shows 402 and 400, not
  429), and later hops use a different model than the thresholds were tuned on. Log `model`, answering
  base URL, per-hop latency, question-set hash, thresholds version.
- Block only on a strong signal for one calibrated rule. Missing key, outage, non-200, garbage, and middle scores
  allow. A blocking Stop hook needs a reject cap and a loop guard (`stop_hook_active` is passed through in the
  payload; agent-hooks does nothing with it).

## Keys

`TYPESAFE_API_KEY`, else Keychain service `typesafe-api-key`; the OpenRouter hop uses `OPENROUTER_API_KEY` or
Keychain `openrouter-api-key`. Each Keychain read is a `security` subprocess (2 s cap) on every hook run.
`typesafe.py install-key` copies the key into the login keychain. `dictation-rewrite.py` also reads
`~/.cache/ai/keys.env`. A missing key fails open silently, so make it visible in the log.

## Logging hygiene

Write one JSONL row per judgment, but store `state` once (not request plus state plus response), cap or rotate the
file, keep the 4xx body in `detail`, redact (messages can contain secrets), and watch the fallback rate with a daily
one-liner over `completion-gate-judgments.jsonl`.

## Where the client lives

`~/.agents/available-skills/typesafe-ai/scripts/` (`typesafe.py` subcommands `judge-turn`, `judge-clarity`,
`interrogate`, `pick-skill`, `install-key`; `systemone.py` for keys and `ask`). Hooks find it through
`~/.agents/hooks/lib/typesafe_location.py`. A result cache keyed by a state hash helps replays and retries; it does
not help two hooks that start at the same instant (that would need single-flight locking, which is more machinery
than merging).
