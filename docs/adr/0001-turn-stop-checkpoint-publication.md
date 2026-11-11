# ADR 0001: Turn-stop checkpoint publication: per-repo enrollment, unique ref, hooks on

| Field              | Value                                                                                                                |
| ------------------ | -------------------------------------------------------------------------------------------------------------------- |
| Status             | Accepted, 2026-11-09                                                                                                 |
| Ticket             | ZYS-9028 (this record). Implemented by ZYS-9023. Related: ZYS-8564, ZYS-9029, ZYS-9030, ZYS-9031, ZYS-9035, ZYS-7609 |
| dev-profile base   | `cce6da0a5d57a14118f1f90f7777cb563fc6eabf`                                                                           |
| Tool versions read | git 2.49.1, mise 2026.11.4, omp `build-20261109145358-38be738`                                                       |
| Scope              | Documentation only. This ADR ships no code and no enrollment file. ZYS-9023 ships both.                              |

Key words MUST, MUST NOT, SHOULD and MAY are used as in RFC 2119. Every rule carries a fixture id (`F<n>`, section 11). ZYS-9023 is not done until each fixture passes.

## 1. Context

`bin/dev-profile-done` publishes agent work today. Observed behavior at the base commit:

| Behavior                                                                      | Line(s) in `bin/dev-profile-done` |
| ----------------------------------------------------------------------------- | --------------------------------- |
| A hook-disable environment variable is set for the whole script               | 58                                |
| The remote is hard-coded to `origin`                                          | 82-83                             |
| Everything is staged with `git add -A`                                        | 413, 463, 658                     |
| Commits are created with a skip-hooks flag                                    | 419, 464, 658                     |
| The push refspec is `spec="${tip}:refs/heads/${ref}"`                         | 801                               |
| Pushes use a skip-hooks flag, one with a lease-force                          | 805, 808                          |
| A plain push also uses a skip-hooks flag                                      | 811                               |
| The local tracking ref is written with `update-ref refs/remotes/origin/<ref>` | 819                               |
| A remote ref is deleted with a lease                                          | 1120                              |

Three more facts drive the design:

- The `wt land` heuristic (`config/worktrunk.toml` line 188) decides what lands from commit shape alone. It has no notion of who owns a ref.
- The `preserve-local-git` skill forbids destroying local work. It does not say who owns a remote ref.
- The hk configuration (`hk/hk.pkl`) already runs `pre-push` for every ref, with no ref filter. Its `pre-commit` step `no-commit-to-default-branch` protects the default branch.

The result: a turn can publish unreviewed, unsigned, unhooked work to a name that already exists, and a force can overwrite it. This ADR replaces that path for turn-stop checkpoints with one contract.

## 2. Decision summary

| Topic      | Decision                                                                                                 |
| ---------- | -------------------------------------------------------------------------------------------------------- |
| Opt-in     | Per repository, via an owner-edited enrollment file. The shipped file has zero enrolled repositories.    |
| Ref        | A new unique ref under `refs/heads/agent-checkpoints/`. Never an existing name. Never forced.            |
| Hooks      | On, always. The publisher runs the normal hk `pre-push`. A rejection is a reported outcome, not a retry. |
| Event      | `agent_end` with `willContinue !== true`. Never `session_stop`.                                          |
| Host       | An omp extension at `apps/omp/extensions/`, deployed by a tracked dotfiles entry in `config/mise.toml`.  |
| Heavy work | A detached worker, not the event handler.                                                                |
| Dotfiles   | Report-only `mise dot pull`; per-path conflict handling.                                                 |

## 3. Contract rules

### 3.1 Ownership

| Id   | Rule                                                                                                                                                                                                                                                                                                                                                                             | Test |
| ---- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---- |
| R1.1 | A repository is published only if its canonical identity appears in the enrollment file with `enabled = true`. Absence means `blocked-not-enrolled`.                                                                                                                                                                                                                             | F1   |
| R1.2 | The publisher MUST own the ref it pushes: the ref name is generated by the publisher and is under `refs/heads/agent-checkpoints/`. It MUST NOT push to any other namespace.                                                                                                                                                                                                      | F5   |
| R1.3 | If the repository matches more than one enrollment entry, the outcome is `blocked-ambiguous-ownership`. The publisher MUST NOT choose.                                                                                                                                                                                                                                           | F1   |
| R1.4 | If the resolved push destination differs from the enrolled `canonical` destination, the outcome is `blocked-destination-changed`.                                                                                                                                                                                                                                                | F8   |
| R1.5 | If the destination is public and the entry does not declare `visibility = "public"`, the outcome is `blocked-visibility-changed`. If visibility cannot be read, the outcome is `blocked-visibility-unverified`. This slice records visibility in the enrollment entry and does not verify it: it emits neither `blocked-visibility-changed` nor `blocked-visibility-unverified`. | F8   |

### 3.2 Ref

| Id   | Rule                                                                                                                                                   | Test   |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | ------ |
| R2.1 | The ref follows the grammar in section 6 and is at most 200 bytes.                                                                                     | F2     |
| R2.2 | The ref embeds the full 40-hex commit SHA. Same SHA, same ref.                                                                                         | F6     |
| R2.3 | If the destination already advertises the ref at the same SHA, the outcome is `verified-present`. Nothing is pushed.                                   | F6     |
| R2.4 | If the ref exists at a different SHA, or a D/F conflict exists, the outcome is `blocked-collision`. The publisher MUST NOT overwrite, delete or force. | F6, F7 |
| R2.5 | The publisher MUST NOT write `refs/remotes/*` for the checkpoint. Success is proved by `ls-remote` read-back only.                                     | F2     |

### 3.3 Hooks

| Id   | Rule                                                                                                                        | Test |
| ---- | --------------------------------------------------------------------------------------------------------------------------- | ---- |
| R3.1 | Every git command the publisher runs MUST run with hooks enabled. No skip-hooks flag. No hook-disable environment variable. | F9   |
| R3.2 | A hook rejection yields `blocked-hook-rejected` with the report in section 9. No retry, no bypass.                          | F10  |
| R3.3 | The publisher MUST NOT use a force flag or a lease-force in any form.                                                       | F9   |

### 3.4 First-increment scope

| Id   | Rule                                                                                                                                      | Test |
| ---- | ----------------------------------------------------------------------------------------------------------------------------------------- | ---- |
| R4.1 | Only committed work is published. The publisher never runs `git add` and never creates a commit. ZYS-8564 and ZYS-9023 create the commit. | F15  |
| R4.2 | The commit MUST be signed. An unsigned commit yields `blocked-unsigned` and is never retried with signing disabled.                       | F15  |
| R4.3 | Only the commits unique to the checkpoint (section 7.3) are published. A commit outside the provenance list yields `blocked-provenance`.  | F11  |
| R4.4 | Secrets are checked by the existing hk gitleaks step. A hit yields `blocked-secrets`.                                                     | F10  |

### 3.5 Pending state

| Id   | Rule                                                                                                         | Test |
| ---- | ------------------------------------------------------------------------------------------------------------ | ---- |
| R5.1 | A job is `pending` while its state is `queued`, `pushing`, or `pushed` without a successful read-back.       | F13  |
| R5.2 | A pending job MUST be reported as pending, never as published. Only `verified` may be reported as published. | F13  |
| R5.3 | A pending job older than 24 h becomes `expired`. It is reported, not silently dropped.                       | F20  |

## 4. Enrollment configuration

| Item                  | Value                                                                                                                                           |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Source in dev-profile | `config/agent-checkpoints/enrollment.toml`                                                                                                      |
| Live path             | `~/.config/agent-checkpoints/enrollment.toml`                                                                                                   |
| Dotfiles mode         | `source = "<repo path>"`: the live path is a symlink to the repo file, so edits go through the repository (the file is still owner-edited only) |
| Editor                | The owner only. No agent, hook, or script edits the file.                                                                                       |
| Schema version        | `schema_version = 1`                                                                                                                            |

Schema:

| Key                       | Type                      | Meaning                                                                                                                                                                                                                                  |
| ------------------------- | ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `schema_version`          | integer                   | Must be `1`. Any other value: the publisher reads nothing and reports `blocked-not-enrolled`.                                                                                                                                            |
| `[repos."<slug>"]`        | table                     | One table per enrolled repository.                                                                                                                                                                                                       |
| `path`                    | string                    | Any checkout or worktree of the repository (leading `~/` allowed). Repository identity is the realpath of its git common dir. Two entries with the same path, or two enabled entries with the same canonical destination, are ambiguous. |
| `canonical`               | string                    | The exact effective push URL (as `git remote get-url --push` prints it) of the remote the publisher may push to. Compared with the resolved destination (R1.4).                                                                          |
| `enabled`                 | bool                      | `false` disables publication without removing the entry.                                                                                                                                                                                 |
| `visibility`              | `"private"` or `"public"` | Declared visibility (R1.5).                                                                                                                                                                                                              |
| `destination`             | string                    | Name of a `[destinations."<name>"]` entry. Not read by this slice; used by ZYS-9038.                                                                                                                                                     |
| `[destinations."<name>"]` | table                     | Typed destination: `kind`, `canonical`, `branch`, `mode`. Not read by this slice; used by ZYS-9038.                                                                                                                                      |

Shipped initial file, to be created by ZYS-9023, not by this ADR:

```toml
# Enrollment for turn-stop checkpoint publication (apps/omp/extensions/agent-checkpoint-publish.ts).
# The owner edits this file; no agent, hook or script does. Nothing is published unless an enabled
# [repos.*] table below matches the repository AND its effective push URL equals `canonical`.
# A remote name, a credential, a URL substring or an org membership never enrolls a repository.
schema_version = 1

# One table per repository. The table name becomes <repo-slug> in the published ref:
#   refs/heads/agent-checkpoints/<repo-slug>/<branch-slug>/<turn-id>-<sha40>
#
# [repos."example-repo"]
# enabled = true
# path = "~/Developer/Personal/example-repo"          # any checkout or worktree of the repository
# canonical = "https://github.com/example/example-repo.git"  # the exact effective push URL
# visibility = "private"                                # "private" or "public"; recorded, not verified
```

This ADR does not ship that file. The initial state of the system is zero enrolled repositories: with no entry, every turn ends with `blocked-not-enrolled` and no push happens.

## 5. Host, event, files

| Item           | Value                                                                                                                                                                                                                                                                                                                                                        |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Host           | omp extension API                                                                                                                                                                                                                                                                                                                                            |
| Extension file | `apps/omp/extensions/agent-checkpoint-publish.ts`                                                                                                                                                                                                                                                                                                            |
| Deployed to    | `~/.omp/agent/extensions/agent-checkpoint-publish.ts`                                                                                                                                                                                                                                                                                                        |
| Deployment     | A repo-sourced dotfiles entry in `config/mise.toml`: `"~/.omp/agent/extensions/agent-checkpoint-publish.ts" = { source = "~/Developer/Personal/dev-profile/apps/omp/extensions/agent-checkpoint-publish.ts" }`. `mode = "track"` tracks a live file where it is and never deploys from the repo, so it is not used. The extension is one self-contained file |
| Event          | `agent_end`, acting only when `willContinue !== true` (precedent: `apps/omp/extensions/herdr-omp-agent-state.ts` lines 499-509)                                                                                                                                                                                                                              |
| Not used       | `session_stop`: it can block and re-prompt, and its continuation is capped (`SESSION_STOP_CONTINUATION_CAP` = 8)                                                                                                                                                                                                                                             |
| Not used       | A row in `hooks.toml`, and the agent-hooks runner: it is archived (`isArchived: true`)                                                                                                                                                                                                                                                                       |

| Id   | Rule                                                                   | Test |
| ---- | ---------------------------------------------------------------------- | ---- |
| R5.4 | The extension MUST return without acting when `willContinue === true`. | F14  |
| R5.5 | The extension MUST NOT register a `session_stop` handler.              | F14  |

## 6. Ref grammar and outcomes

Grammar:

```text
refs/heads/agent-checkpoints/<repo-slug>/<branch-slug>/<turn-id>-<sha40>
```

| Part            | Rule                                                                            |
| --------------- | ------------------------------------------------------------------------------- |
| `<repo-slug>`   | Lowercase `[a-z0-9-]`, derived from the canonical identity, `/` replaced by `-` |
| `<branch-slug>` | Lowercase `[a-z0-9-]`, derived from the source branch                           |
| `<turn-id>`     | `t` plus a zero-padded turn counter                                             |
| `<sha40>`       | The full 40-hex commit SHA                                                      |
| Total length    | At most 200 bytes                                                               |
| Validation      | The short name MUST pass `git check-ref-format --branch`                        |

Example (short name):

```text
agent-checkpoints/zachbornheimer-dev-profile/relay-zys-9028-adr/t0042-cce6da0a5d57a14118f1f90f7777cb563fc6eabf
```

Outcomes:

| Outcome                         | Meaning                                                                                                  |
| ------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `verified`                      | Pushed, and `ls-remote` shows the ref at the SHA                                                         |
| `verified-present`              | The ref was already at the SHA. No push.                                                                 |
| `blocked-collision`             | The ref exists at a different SHA (`different-sha`), or a directory/file conflict exists (`df-conflict`) |
| `blocked-not-enrolled`          | No enabled enrollment entry                                                                              |
| `blocked-ambiguous-ownership`   | More than one entry matches                                                                              |
| `blocked-destination-changed`   | Resolved destination differs from `canonical`                                                            |
| `blocked-visibility-changed`    | Destination is public but not declared public                                                            |
| `blocked-visibility-unverified` | Visibility could not be read                                                                             |
| `blocked-namespace`             | The computed ref is outside `refs/heads/agent-checkpoints/`                                              |
| `blocked-missing-baseline`      | The destination advertises no tip the publisher can compare to                                           |
| `blocked-unrelated-ancestry`    | The commit shares no ancestry with any advertised tip                                                    |
| `blocked-provenance`            | A commit outside the provenance list would be pushed                                                     |
| `blocked-secrets`               | The secret scan found a hit                                                                              |
| `blocked-unsigned`              | A commit to publish is not signed                                                                        |
| `blocked-hook-rejected`         | hk `pre-push` or another hook rejected the push                                                          |
| `blocked-remote-rejected`       | The remote refused the ref                                                                               |
| `blocked-isolation-unavailable` | The worker cannot run isolated (no `setsid` or `flock`)                                                  |
| `blocked-timeout`               | An attempt exceeded 35 min                                                                               |
| `blocked-remote-unreachable`    | The destination did not answer                                                                           |

## 7. Design points

### 7.1 Push destination

The publisher MUST derive the destination from `git push --dry-run -v`, run `ls-remote` on the same URL, and push to that exact URL.

- `git ls-remote <remote>` reads the fetch URL, not `pushurl`. Using the remote name for read-back can check the wrong repository.
- `pushInsteadOf` is ignored when `pushurl` is set for that remote. The dry run reports what git will really use.
- The push and the read-back use the same resolved URL string. Fixtures F3 (pushurl) and F4 (insteadOf) cover both.

### 7.2 D/F conflicts

A directory/file conflict arises when a ref such as `agent-checkpoints/a/b` exists and a push wants `agent-checkpoints/a/b/c`, or the reverse. The publisher MUST check for a prefix or extension of the new ref in the `ls-remote` listing before it pushes and report `blocked-collision` with detail `df-conflict`. The local tracking ref is not proof of remote state. If the listing cannot be read, the detail is `tracking-ref-unavailable` and the outcome is `blocked-remote-unreachable`.

### 7.3 Eligibility base

- The destination-advertised tips MUST be present locally. If none is, `blocked-missing-baseline`.
- The publisher computes `git rev-list <sha> --not <advertised tips>`. That set MUST be a subset of the provenance list recorded by ZYS-8564 and ZYS-9023. Any other commit yields `blocked-provenance`.
- hk keeps its own changed-file computation (`bin/dev-profile-changed-files`; `hk/hk.pkl` lines 16-27 and 499-507). gitleaks is configured at line 510. The publisher does not replace them.

### 7.4 Signing

The publisher verifies signatures. It never creates commits and never turns signing off. An unsigned commit yields `blocked-unsigned`. A retry with signing disabled is forbidden. ZYS-8564 and ZYS-9023 create the signed commit.

### 7.5 Stop budget

omp's extension handler deadline is `EXTENSION_HANDLER_TIMEOUT_MS` = 30000 ms (30 s). `session_shutdown` gets 2000 ms. These were read by static inspection of omp `build-20261109145358-38be738`, not by a run. ZYS-9023 MUST re-check the deadline on the deployed omp.

The handler MUST finish well under 30 s. It only enrolls-check, computes the ref, writes a job record, and launches the worker. The worker does the slow, hook-gated push. hk `pre-push` has `timeout = "30m"`, so the worker gets 35 min per attempt.

## 8. Integration

| Step | Where   | Action                                                                                                     |
| ---- | ------- | ---------------------------------------------------------------------------------------------------------- |
| 1    | Handler | On `agent_end` with `willContinue !== true`, resolve the repository and read the enrollment file           |
| 2    | Handler | Write the job record `queued`; start the worker detached with `setsid`; return                             |
| 3    | Worker  | Take `flock` on the job key; re-derive destination (7.1); check ownership, collision, eligibility, signing |
| 4    | Worker  | Set `pushing`; run the normal push with hooks on; on success set `pushed`                                  |
| 5    | Worker  | `ls-remote` read-back on the same URL; set `verified` or a `blocked-*` / `failed` outcome                  |

Job record:

| Item          | Value                                                                                |
| ------------- | ------------------------------------------------------------------------------------ |
| Path          | `~/.local/state/agent-checkpoints/jobs/<sha256(repo NUL ref NUL sha)>.json`          |
| Mode          | 0600, written atomically (temp file plus rename)                                     |
| States        | `queued`, `pushing`, `pushed`, `verified`; terminal: `verified`, `failed`, `expired` |
| Heartbeat     | Worker updates every 60 s; stale after 180 s                                         |
| Attempt limit | 35 min per attempt, at most 3 attempts in total                                      |
| TTL           | 24 h, then `expired`                                                                 |
| Prune         | Terminal records older than 7 days                                                   |
| Env guard     | `AGENT_CHECKPOINT_PUBLISH=1` is set in the worker                                    |

| Id   | Rule                                                                                                                                             | Test    |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ------- |
| R8.1 | Idempotent: the same key never creates a second job or second push. A rerun on `verified` reports `verified-present`.                            | F6, F12 |
| R8.2 | A job with a stale heartbeat is taken over by the next worker under `flock`.                                                                     | F12     |
| R8.3 | No recursion: a worker that sees `AGENT_CHECKPOINT_PUBLISH=1` MUST NOT launch another publication, and the handler MUST NOT act inside a worker. | F14     |

## 9. This is not a hook bypass

- hk's `["pre-push"]` step (`hk/hk.pkl` lines 499-507) has no ref filter. A checkpoint push runs the same checks as any push.
- `pre-commit` (line 496) keeps `no-commit-to-default-branch`. Checkpoints are never on the default branch.
- hk's `timeout = "30m"` bounds the gate. The worker waits for it.

A rejection report (`blocked-hook-rejected`) MUST contain: the exit code, the last 20 lines of hook output, the ref and the SHA, and a statement that local work is intact. There is no retry on a hook rejection. A human or a new commit changes the input.

## 10. Dotfiles propagation (mise dot)

The extension (`apps/omp/extensions/agent-checkpoint-publish.ts`) reports exactly one mise reconciliation outcome per `agent_end`. It is separate from the repository checkpoint outcome and never collapsed into it.

Outcome states, most severe first (precedence `blocked` > `pending` > `scheduled` > `verified`; the extension reports the most severe state that matches, exactly one):

| State       | Meaning                                                                                                                                                                                                                          |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `blocked`   | A condition needs the owner. Every blocked condition is listed, each with its path(s).                                                                                                                                           |
| `pending`   | `history.pending_operations` > 0, or `history.sync.pending_applications` is non-empty, or the extension's own reconciliation job is queued (`mise dot sync` exceeded the handler's 12 s ceiling; a detached worker finishes it). |
| `scheduled` | At least one unsaved path exists, every unsaved path is manual-save, and the watchdog stamp exists and is younger than the cadence. A fully clean machine is not `scheduled`; it takes the verify path.                          |
| `verified`  | Evidence per R10.8.                                                                                                                                                                                                              |

Blocked reasons, in reporting order:

| Reason                | Condition                                                                                                                                                                                                |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `conflict`            | `history.sync.conflicts` is non-empty. Per path the report prints `mise dot conflicts <path>`, then `mise dot pull --take-remote <path>` or `mise dot pull --keep-local <path>`.                         |
| `failing`             | `history.sync.last_error` or `failing_since` is non-null.                                                                                                                                                |
| `offline`             | The origin is unreachable.                                                                                                                                                                               |
| `fetch-only`          | `history.sync.mode` is not `sync`. This is the configured adopt state on Relay boxes and is an honest blocked.                                                                                           |
| `unsaved`             | An unsaved path that is not manual-save: `autosave != false` in the newest checkpoint coverage entries from `mise dot history show --json`.                                                              |
| `manual-save-overdue` | A manual-save path is unsaved while the watchdog stamp `$MISE_HISTORY_LOG_DIR/manual-save.stamp` is missing or at least 24 h old. Cadence env `MISE_HISTORY_MANUAL_SAVE_EVERY_S`, default 86400.         |
| `destination-changed` | `history.sync.origin` differs from the declared canonical, the `[destinations."mise-history"]` table of `config/agent-checkpoints/enrollment.toml`. A missing declaration is also `destination-changed`. |

Mapping from the retired five-name vocabulary (`mise-in-sync`, `scheduled`, `mise-conflict`, `not-propagated`, `mise-offline`): `mise-in-sync` is `verified`; `scheduled` is `scheduled`; `mise-conflict` is `blocked` / `conflict`; `not-propagated` is `blocked` / `fetch-only`; `mise-offline` is `blocked` / `offline`.

| Id    | Rule                                                                                                                                                                                                                                                                                                                                                                                                        | Test               |
| ----- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------ |
| R10.1 | The extension never edits `~/.local/state/mise/history/` by hand and never touches the watchdog stamp. It never runs `mise dot save`, `mise dot recover` or `mise dot bootstrap`, and never passes `--allow-plaintext-history`.                                                                                                                                                                             | F16                |
| R10.2 | Report-only: the extension never runs `mise dot pull`, because pull rewrites live files mid-session. It reports the per-path commands (R10.3) and the owner runs them.                                                                                                                                                                                                                                      | F17                |
| R10.3 | On a conflict, the report names each path and prints `mise dot conflicts <path>`, then `mise dot pull --take-remote <path>` or `mise dot pull --keep-local <path>`, one path at a time. The extension resolves nothing. Pull's own checkpoint keeps both sides recoverable via `mise dot undo`.                                                                                                             | F17                |
| R10.4 | A manual-save path (for example `~/.gitconfig`) that is unsaved while the watchdog stamp exists and is younger than the cadence is `scheduled`. Once the stamp is missing or at least 24 h old it is `blocked` / `manual-save-overdue`. The extension never touches the stamp mtime. The cadence follows `bin/dev-profile-mise-history-watchdog` lines 224-243.                                             | F17                |
| R10.5 | If the dotfiles origin is fetch-only (`history.sync.mode` is not `sync`), the outcome is `blocked` / `fetch-only`. It is never `verified`.                                                                                                                                                                                                                                                                  | F18                |
| R10.6 | If the dotfiles origin differs from the declared canonical, or no canonical is declared, the outcome is `blocked` / `destination-changed`.                                                                                                                                                                                                                                                                  | F16                |
| R10.7 | Re-verify these rules on mise 2026.11.5. The first verification was on mise 2026.11.4, where `mise dot sync` writes no live files. The hermetic suite `bun test apps/omp/extensions/agent-checkpoint-publish.test.ts` is the re-verification vehicle; run it on each mise version.                                                                                                                          | n/a                |
| R10.8 | `verified` requires, after exactly one `mise dot sync`: conflicts empty, no blocked condition, `pending_operations == 0`, and `git ls-remote <history.sync.origin> refs/heads/<history.sync.branch>` equal to the local history repository HEAD. Sync exit code 0 or a `--best-effort` warning is not evidence. No mise outcome is reported at all when `mise` is not on PATH or `history.enabled != true`. | F16, F17, F18, F19 |

## 11. Fixtures

| Id  | Scenario                                                                                                                           | Expected outcome                                                                                                                                                     |
| --- | ---------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| F1  | Repository not in the enrollment file; and two matching entries                                                                    | `blocked-not-enrolled`; `blocked-ambiguous-ownership`                                                                                                                |
| F2  | Happy path: enrolled, signed, hooks pass                                                                                           | `verified`; no `refs/remotes/*` written                                                                                                                              |
| F3  | Remote has a `pushurl` different from the fetch URL                                                                                | Push and read-back both use the push URL                                                                                                                             |
| F4  | `pushInsteadOf` rewrites the URL                                                                                                   | Dry-run URL is used for push and read-back                                                                                                                           |
| F5  | Computed ref outside `refs/heads/agent-checkpoints/`                                                                               | `blocked-namespace`                                                                                                                                                  |
| F6  | Ref exists at same SHA; ref exists at a different SHA                                                                              | `verified-present`; `blocked-collision` (`different-sha`)                                                                                                            |
| F7  | Directory/file conflict with an existing ref                                                                                       | `blocked-collision` (`df-conflict`)                                                                                                                                  |
| F8  | Destination, or its visibility, changed or unreadable                                                                              | `blocked-destination-changed`, `blocked-visibility-changed`, `blocked-visibility-unverified`                                                                         |
| F9  | Scan the worker's git invocations                                                                                                  | No skip-hooks flag, no hook-disable variable, no force flag                                                                                                          |
| F10 | hk `pre-push` fails; gitleaks hits                                                                                                 | `blocked-hook-rejected` with report; `blocked-secrets`                                                                                                               |
| F11 | Commit outside the provenance list; no baseline; unrelated ancestry                                                                | `blocked-provenance`; `blocked-missing-baseline`; `blocked-unrelated-ancestry`                                                                                       |
| F12 | Worker killed mid-push, then restarted                                                                                             | Stale heartbeat taken over; one push                                                                                                                                 |
| F13 | Job in `queued`, `pushing`, `pushed`                                                                                               | Reported as pending, never published                                                                                                                                 |
| F14 | `willContinue === true`; handler inside a worker; slow push                                                                        | Handler returns at once; no recursion; handler under 30 s                                                                                                            |
| F15 | Unsigned commit                                                                                                                    | `blocked-unsigned`; no retry with signing off                                                                                                                        |
| F16 | Dotfiles origin differs from declared canonical, or no `[destinations."mise-history"]` declaration                                 | `blocked` with reason `destination-changed`                                                                                                                          |
| F17 | Per-path conflict; unsaved manual-save path with a young watchdog stamp; unsaved manual-save path with a missing or 24 h old stamp | `blocked` with reason `conflict`, per-path commands printed, both versions recoverable via `mise dot undo`; `scheduled`; `blocked` with reason `manual-save-overdue` |
| F18 | Dotfiles origin is fetch-only (`history.sync.mode` is not `sync`)                                                                  | `blocked` with reason `fetch-only`; never `verified`                                                                                                                 |
| F19 | Dotfiles origin offline                                                                                                            | `blocked` with reason `offline`                                                                                                                                      |
| F20 | Retry exhaustion and 24 h expiry                                                                                                   | `failed` after 3 attempts; `expired` after 24 h                                                                                                                      |

## 12. Acceptance map

| Ticket criterion                                                                                 | Section                     |
| ------------------------------------------------------------------------------------------------ | --------------------------- |
| 1. Contract items 1-5 as testable rules                                                          | 3                           |
| 2. Enrollment path, schema, editor, tracking, zero repositories                                  | 4                           |
| 3. Extension file, dotfile entry, `agent_end`/`willContinue`, not `session_stop`, no agent-hooks | 5                           |
| 4. Ref grammar and outcomes                                                                      | 6                           |
| 5. Integration, timeout design, job record, no recursion                                         | 7.5, 8                      |
| 6. Five design points                                                                            | 7                           |
| 7. Item 6 rules                                                                                  | 10                          |
| 8. Not a hook bypass, rejection report                                                           | 9                           |
| 9. Fixture list                                                                                  | 11                          |
| 10. Merged to the default branch and linked from ZYS-9023 with the merge SHA                     | Delivery record on ZYS-9023 |

## 13. Consequences and non-goals

Consequences:

- Turn-stop publication needs one owner-edited file before any repository publishes. That is one more step per repository, and it is the point.
- Checkpoint refs accumulate on the destination. Pruning is the owner's decision and is out of scope.
- A slow hk run no longer blocks a turn. The cost is that publication is pending for up to 35 min per attempt.

Non-goals:

- Changing `bin/dev-profile-done`, `config/mise.toml`, the hk configuration, `hooks.toml`, or anything under `~/.agents`. ZYS-9023 does that.
- Creating commits or staging files in the publisher.
- Publishing to the default branch, or to any ref the publisher does not own.

## 14. Verify

```bash
adr=docs/adr/0001-turn-stop-checkpoint-publication.md
for p in 'refs/heads/agent-checkpoints/' 'verified-present' 'blocked-collision' 'pushurl' 'pushInsteadOf' 'pending' 'D/F' '30 ?m' '30 ?(s|000 ?ms)' 'agent_end' 'willContinue' 'apps/omp/extensions/' 'config/mise.toml' 'archived' 'zero enrolled|no repositor(y|ies) (is |are )?enrolled' 'mise dot pull' 'mise dot conflicts' 'fetch-only' 'scheduled' 'blocked-unsigned'; do
  grep -qE -- "$p" "$adr" || echo "MISSING: $p"
done
git check-ref-format --branch 'agent-checkpoints/zachbornheimer-dev-profile/relay-zys-9028-adr/t0042-cce6da0a5d57a14118f1f90f7777cb563fc6eabf'
```
