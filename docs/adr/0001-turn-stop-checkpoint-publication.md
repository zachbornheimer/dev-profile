# ADR 0001: Turn-stop checkpoint publication

- Status: accepted
- Date: 2026-11-09
- Ticket: ZYS-9028 (records the contract) · Implementation: ZYS-9023 · Provenance source: ZYS-8564
- Supersedes: none
- Default: **nothing is published.** A repository publishes a turn-stop checkpoint only when it is
  explicitly enrolled (D1).

Keywords MUST, MUST NOT, SHOULD, MAY are used per RFC 2119.

## Context

A turn can end with verified local work that exists on one machine only. Losing that machine loses the
work. Publishing it as a checkpoint ref gives a second copy, and doing so automatically is only safe if
ownership, identity, gate behaviour and failure reporting are all pinned down before any code runs.

The repository already holds three things that look like the answer and are not:

1. `bin/dev-profile-done` publishes local work today, but it is unusable at a turn stop. It hard-codes
   `origin` (L82-83), disables hooks with an environment variable (`HK[=]0`, L58), commits with `git add -A`
   and a skip-hooks flag (L413-419, L463-464, L658), pushes with a skip-hooks flag plus lease-guarded
   `--[-]`force (L805, L808) and plain skip-hooks (L811), then writes `git update-ref refs/remotes/origin/<ref>`
   locally with no read of the remote (L819), and deletes refs with skip-hooks + force + delete (L1120).
   Two of those properties are fatal here: no remote read-back, and hook bypass.
2. The `agent-hooks` repository is `archived` (`gh repo view zachbornheimer/agent-hooks` ->
   `isArchived: true`). `apps/omp/extensions/run-agent-hooks.ts` is a generated shim to that archived
   dispatcher (Stop timeout 28000 ms, L32; `session_stop` L227; `session_shutdown` fallback L243). It MUST NOT
   be reused or extended, and no row is added to either `hooks.toml`.
3. `config/worktrunk.toml` L188 (`land`) infers ownership from `owner == zachbornheimer` or a substring of the
   remote URL, and `~/.agents/available-skills/preserve-local-git/SKILL.md` states a manual policy. Neither
   defines ownership. Both are left untouched.

Two budgets shape the design and are verified, not assumed:

- omp enforces `EXTENSION_HANDLER_TIMEOUT_MS` = 30 000 ms for every extension event except `session_shutdown`
  (2 000 ms); an overrun is reported as `Extension <path> timed out after <ms>ms`
  (build `build-20261109145358-38be738`). ZYS-9023 MUST re-check the number on the deployed build and the
  design MUST hold if it is shorter.
- `hk`, the pre-push gate, has a `timeout = "30m"` (30 m). A gated push therefore cannot run inside a
  handler that has 30 s.

So the two halves are split: a cheap handler at turn end, and a detached worker that owns the gated push.

## Decision

### D1 Ownership is per-repository enrollment (contract item 1)

Enrollment file: **`config/agent-checkpoints/enrollment.toml`** in `zachbornheimer/dev-profile`, deployed to
`~/.config/agent-checkpoints/enrollment.toml` by a `mode = "track"` `[dotfiles]` entry in `config/mise.toml`
(the pattern of L193-203 that already deploys `~/.omp/agent/extensions/*.ts`). It is tracked in dotfiles, so
it is reviewable and versioned; it is not local-only. Only the owner edits it.

It ships with **zero enrolled repositories**: the file has `schema_version` and no `[repos.*]` table at all.
Which repositories are enrolled later is ZYS-9031's decision, not this ADR's; the path and schema are fixed here.

| key | type | meaning | required |
| --- | --- | --- | --- |
| `schema_version` | integer | MUST be `1`; any other value rejects the whole file | yes |
| `repos."<owner>/<name>".canonical` | string | canonical repository identity: `github.com/<owner>/<name>`, lowercase, no scheme, no `.git` | yes |
| `repos."<owner>/<name>".push_url` | string | the normalized **effective** push URL (rule below), `https://` form | yes |
| `repos."<owner>/<name>".visibility` | string | `public`, `private` or `internal`: the visibility the destination MUST report before a push | yes |
| `repos."<owner>/<name>".namespace` | string | allowed checkpoint namespace; MUST start with `refs/heads/agent-checkpoints/`, MUST end with `/`, and may only narrow that prefix | yes |

Normalization for both `push_url` and every URL the publisher derives: scheme lowercased; host lowercased;
default port dropped; trailing `.git` and trailing `/` stripped; path case kept. Comparison is exact string
equality after normalization. `canonical` is additionally derived by dropping the scheme.

Rules:

- `Test: F1`. A repository MUST have an enrollment entry before any ref is pushed. Absent entry:
  `blocked-not-enrolled`, nothing pushed.
- An unknown key, a missing required key, a non-`1` `schema_version`, or a malformed URL MUST reject the whole
  file (fail closed): `blocked-enrollment-invalid`.
- A remote name, a writable credential, a substring match on the remote URL (the `wt land` heuristic), or
  membership in the owner's org MUST NOT authorize a publish.
- The publisher MUST inspect every effective fetch and push URL before deciding: `url.*.insteadOf`,
  `url.*.pushInsteadOf`, every `remote.<n>.pushurl` (a remote may hold several), `remote.pushDefault`, and
  `branch.<name>.pushRemote`. When these produce more than one distinct effective push URL for the ref under
  consideration: `blocked-ambiguous-ownership`. When the effective push URL differs from the enrolled
  `push_url`: `blocked-destination-changed`.
- A destination whose visibility differs from the enrolled `visibility`, or cannot be read:
  `blocked-visibility-changed` / `blocked-visibility-unverified`. The check is repeated by the worker
  immediately before the push, because enrollment is a statement about a moment.
- The computed ref MUST be inside the enrolled `namespace`: otherwise `blocked-namespace`.

### D2 Checkpoint ref grammar and outcomes (contract item 2)

```
refs/heads/agent-checkpoints/<repo-slug>/<branch-slug>/<turn-id>-<sha>
```

| component | rule |
| --- | --- |
| `repo-slug` | `canonical` with every `/` replaced by `-`; `[a-z0-9-]`, at most 63 bytes |
| `branch-slug` | the source branch with every `/` replaced by `-`; `[A-Za-z0-9._-]`, at most 63 bytes |
| `turn-id` | the turn/checkpoint identity, `[A-Za-z0-9._-]{1,64}`, no component equal to `.` or `..`, no leading `-` |
| `sha` | the 40-character lowercase hex checkpoint SHA |

The whole ref is at most 200 bytes and MUST pass `git check-ref-format refs/heads/<...>` (and its short form
MUST pass `git check-ref-format --branch <...>`). Example, valid under `git check-ref-format --branch`:

```
agent-checkpoints/zachbornheimer-dev-profile/relay-zys-9028-adr/01a3f2c9b7-e7c1d2a3b4f5061728394a5b6c7d8e9f0a1b2c3d
```

The full ref is that string with `refs/heads/` in front.

Rules:

- `Test: F4`, `Test: F6`. The ref MUST be keyed to both the turn and the checkpoint SHA, so that a repeat
  publish of the same checkpoint is a no-op and a different checkpoint can never occupy the same ref.
- `Test: F4`. The publisher MUST NOT target the default branch, a source branch, or any ref outside D2's
  grammar. It MUST NOT delete, MUST NOT move, and MUST NOT push with a force or lease option. Ref lifetime and
  cleanup are ZYS-9030's decision; this increment never expires a ref.
- `Test: F2`. Existence MUST be checked by reading the destination itself,
  `git ls-remote <effective-push-url> <ref>`, never a local remote-tracking ref. A local
  `refs/remotes/<remote>/<ref>` is not proof of publication: with a remote branch `agent-checkpoints` present,
  git failed to write `refs/remotes/origin/agent-checkpoints` while
  `refs/remotes/origin/agent-checkpoints/<id>` existed, so the tracking ref can be absent while the remote
  holds the branch, and present while the push is still rejected.
- `Test: F6`. The exact ref already exists at the intended SHA: `verified-present`, an idempotent success. No
  push is performed and the local commit is unchanged.
- `Test: F4`, `Test: F5`. Any other existing ref blocks: `blocked-collision`, with sub-reason `different-sha`
  when the ref exists at another SHA, and `df-conflict` when a directory/file conflict prevents the ref from
  existing (a remote branch named `agent-checkpoints` rejects `agent-checkpoints/<id>` with
  `remote rejected ... failed to update ref`). A collision is reported, never retried in any form.

Outcome vocabulary. Every result the publisher records is exactly one of these:

| outcome | meaning |
| --- | --- |
| `published-verified` | push landed and the destination read-back returned the ref at the checkpoint SHA |
| `verified-present` | the exact ref was already at that SHA; success, nothing pushed |
| `pending` | a job exists in `queued`, `pushing` or `pushed` and no read-back has confirmed it; **never** counted as preserved |
| `failed` | a terminal failure carrying exactly one `blocked-*` reason below |
| `expired` | the job outlived its bounded lifetime (D10) without a terminal state |
| `scheduled` | a divergence inside a `manual-save` window; not a failure (D11) |
| `fetch-only` | the sync destination is in `fetch-only` mode, so nothing is propagated (D11) |

Every `blocked-*` reason, each a terminal `failed`:

| reason | raised when |
| --- | --- |
| `blocked-not-enrolled` | no enrollment entry for the repository |
| `blocked-enrollment-invalid` | the enrollment file has an unknown key, a missing key, a bad `schema_version` or a malformed URL |
| `blocked-ambiguous-ownership` | more than one distinct effective push URL for the ref |
| `blocked-destination-changed` | the effective push URL differs from the enrolled `push_url` |
| `blocked-visibility-changed` | destination visibility differs from the enrolled `visibility` |
| `blocked-visibility-unverified` | destination visibility could not be read |
| `blocked-namespace` | the computed ref is outside the enrolled `namespace` |
| `blocked-collision` | the ref exists at another SHA (`different-sha`) or a D/F conflict prevents it (`df-conflict`) |
| `blocked-missing-baseline` | no destination-advertised tip the publisher can resolve locally |
| `blocked-unrelated-ancestry` | a newly introduced commit is not in this turn's provenance list |
| `blocked-provenance` | no provenance list for the turn, or it is internally inconsistent |
| `blocked-secrets` | the secret scan reported a finding in the introduced content |
| `blocked-unsigned` | the checkpoint commit could not be signed and the requirement is to preserve signing |
| `blocked-hook-rejected` | a hook rejected the commit or the push |
| `blocked-remote-rejected` | the destination refused the ref for any non-hook reason |
| `blocked-remote-unreachable` | the destination could not be read or reached |
| `blocked-isolation-unavailable` | a throwaway worktree could not be created at the checkpoint SHA |
| `blocked-timeout` | the worker exceeded its per-attempt budget |

### D3 Hooks and signing stay on (contract item 3)

- `Test: F7`. Normal `pre-commit`, `commit-msg` and `pre-push` hooks MUST stay enabled for every commit and
  push this design performs. The design MUST NOT pass a skip-hooks flag, MUST NOT set a hook-disable
  environment variable, MUST NOT request a hook exemption, and MUST NOT change branch protection.
- `Test: F7`. The design MUST NOT push with a force option, a lease option or a delete, and MUST NOT write a
  remote-tracking ref by hand. `bin/dev-profile-done` does three of these today (L805, L808, L819, L1120); none
  of that code is reused.
- Signing MUST be preserved. A checkpoint commit that cannot be signed is `blocked-unsigned`: local work
  intact, nothing published, and no retry with signing disabled. `commit.gpgsign` is never overridden.
- `Test: F7`. A rejected commit or push is `blocked-hook-rejected`, reported with the exit code, the last 20
  lines of the hook output, the ref and the checkpoint SHA, with local work intact and no automatic retry. The
  operator decides what happens next.

### D4 First increment: publish only a provenance-verified checkpoint (contract item 4)

- `Test: F4`. The publisher MUST publish only an already-created checkpoint commit that this turn created. It
  MUST NOT commit, stage, stash or amend anything, and MUST NOT publish uncommitted work: that is reported by
  ZYS-9023, not staged. Whether uncommitted work warns or auto-commits is ZYS-8564's decision.
- `Test: F3`. Every newly introduced commit and object MUST be shown eligible for the destination. A moved
  HEAD, a created branch, or a `git show-ref` snapshot is not proof.
- Eligibility base: the tips the destination itself advertises (`git ls-remote <effective-push-url>`, resolved
  against the local object database) plus every commit of the checkpoint's own turn. Formally:
  `git rev-list <sha> --not <destination-tips>` MUST be a subset of this turn's provenance list. An empty
  range means the destination already holds the commit: the idempotent `verified-present` path applies.
- No destination tip resolvable locally: `blocked-missing-baseline`. A commit in that range absent from the
  provenance list: `blocked-unrelated-ancestry`. No provenance list at all: `blocked-provenance`.
- `Test: F3`. `hk`'s own base is a different base and is stated here so nobody conflates them: `pre-push`
  judges the files introduced against the mainline that `bin/dev-profile-changed-files` resolves (judging
  introduced files only, `hk/hk.pkl` L16-27), and its gitleaks stage scans the pushed range (L510). The
  publisher's eligibility base is the destination-advertised tips above. Both run; neither replaces the other.
- `Test: F7`. A secret-scan finding blocks with `blocked-secrets`.
- Integration with ZYS-8564 remains required for the full goal (which local commits count as this turn's, and
  how a turn's provenance is captured).

### D5 `pending` is not preservation (contract item 5)

- A queued background job is `pending`. It MUST NOT be reported, or counted anywhere, as preserved,
  published or backed up. Only `published-verified` and `verified-present` claim preservation.
- The job status MUST be durable and idempotent, and MUST have a bounded lifetime (D10).

### D6 Publication destination: one address for check and push (open point 1)

`git ls-remote <remote>` reads the **fetch** URL, not `remote.<n>.pushurl`. Reproduced: with
`remote.origin.url = A` and `remote.origin.pushurl = B`, a ref present only on B made `git ls-remote origin`
list nothing. Separately (git 2.49.1), with `url.<A>.pushInsteadOf = <B>` plus `remote.origin.pushurl = <B>`,
a push to the explicit URL `<B>` landed on A, a push through the remote name `origin` landed on B, and
`git config --get-url --push origin` printed B: git ignores `pushInsteadOf` for a remote that carries an
explicit `pushurl`. Both facts mean "check by URL, push by remote name" can address two different servers.

Decision: derive the destination **once**, from what a push actually resolves, and then use that one address
for both operations.

1. Resolve with `git push --dry-run -v` against the remote, and read the URL git reports for the push. That URL
   is the effective push URL.
2. Compare it, normalized per D1, with the enrolled `push_url`. Mismatch: `blocked-destination-changed`.
3. Check with `git ls-remote <that-url> <ref>`; push with `git push <that-url> <sha>:<ref>`.
4. The publisher MUST NOT push through a remote name while checking an explicit URL, or the reverse. It MUST
   NOT assume `git config --get-url --push`, `git remote get-url`, or a dry run alone agrees with the others:
   the dry run's reported URL is authoritative, the others are corroboration only.
5. `Test: F2`, `Test: F3`. Multiple `pushurl` values, a `pushInsteadOf` rewrite, `remote.pushDefault` and
   `branch.*.pushRemote` all feed the same comparison; disagreement is `blocked-ambiguous-ownership`.

### D7 Directory/file collision is a collision, not a retry (open point 2)

- `Test: F5`. A remote branch at `agent-checkpoints` blocks `agent-checkpoints/<id>`; git answers
  `remote rejected ... failed to update ref`. This is `blocked-collision` with `df-conflict`, terminal, and is
  never retried, neither as the same ref nor with a shorter one.
- The same D/F condition prevents git from writing the remote-tracking ref locally, so D2's rule holds
  absolutely: only the destination read counts, and the report MUST state which read produced the answer.
- The report for a collision names the conflicting ref, its SHA when readable, and the fact that the remote
  was read directly rather than inferred from local refs.

### D8 Signing in a key-less container (open point 4)

- Reproduced on this box: with `commit.gpgsign` on and key `0D74...` absent, `git commit` fails
  (`gpg: skipped ... No secret key`, `failed to write commit object`).
- A checkpoint commit that cannot be signed is `blocked-unsigned`: local work intact, nothing published, and
  the ADR forbids retrying with signing disabled. The sandbox condition is reported, not worked around.
- Who does what: ZYS-8564 and ZYS-9023 create the checkpoint commit and own its signature. The publication
  path in this ADR only *verifies* provenance and signature; it never creates a commit and never re-signs one.

### D9 Stop budget and event choice (open point 5)

- Verified: the handler deadline is 30 000 ms (`EXTENSION_HANDLER_TIMEOUT_MS`, every event except
  `session_shutdown` at 2 000 ms); the `hk` `pre-push` gate's own timeout is `30m`. A gated publish inside a
  handler cannot finish, and an overrunning handler is killed with a timeout message.
- Therefore the handler's budget is 30 s of cheap work and the gate-bearing push belongs to a detached
  worker. The handler's own budget target is under 5 s of external I/O.
- `Test: F8`. Event: **`agent_end`**, acting only when `willContinue !== true`, so a pause that will resume the
  same turn does not publish a half-turn checkpoint.
- **Not** `session_stop`. Its handlers can block a turn and re-prompt it, and omp caps that at
  `SESSION_STOP_CONTINUATION_CAP` = 8. A publish failure would then become a conversation loop, and a
  checkpoint feature MUST NOT be able to extend or restart a turn.

### D10 Integration: cheap handler, detached worker, durable job (contract item 5)

Host: an OMP-native extension at **`apps/omp/extensions/agent-checkpoint-publish.ts`** in
`zachbornheimer/dev-profile`, deployed to `~/.omp/agent/extensions/agent-checkpoint-publish.ts` by a
`mode = "track"` `[dotfiles]` entry in **`config/mise.toml`** (pattern of L193-203). It does not use the
archived `agent-hooks` dispatcher, does not reuse `apps/omp/extensions/run-agent-hooks.ts`, and has no row in
either `hooks.toml`.

| step | runs in | budget |
| --- | --- | --- |
| re-entry guard (environment marker + job key) | handler | immediate |
| provenance lookup, enrollment, effective-URL check, ref computation | handler | under 1 s |
| one bounded `git ls-remote` of the destination | handler | 5 s hard cap |
| write the job record, spawn the worker detached (`setsid`) | handler | under 1 s |
| one status line to the turn output | handler | immediate |
| eligibility proof, secret scan, visibility re-check, throwaway linked worktree at the checkpoint SHA, hooks-enabled push, `ls-remote` read-back | worker | 35 min per attempt |

The handler MUST NOT push, MUST NOT run `hk`, and MUST NOT wait for the worker. It MUST wrap its whole body in
a `try`/`catch` and MUST NOT return a blocking or continuation result.

Job record: `~/.local/state/agent-checkpoints/jobs/<sha256(repo NUL ref NUL sha)>.json`, mode 0600, written by
atomic rename.

| field | meaning |
| --- | --- |
| `state` | `queued` -> `pushing` -> `pushed` -> `verified`; terminals `verified`, `failed`, `expired` |
| `outcome` | the D2 outcome string; `pending` while the state is non-terminal |
| `attempts` | incremented per attempt, at most 3 |
| `created_at`, `updated_at`, `expires_at` | `expires_at` = `created_at` + 24 h |
| `reason`, `detail` | the `blocked-*` reason and its evidence, for a `failed` job |

- `Test: F9`. Idempotent re-run: the key is derived only from repository, ref and SHA, so a repeated publish,
  a restarted worker or a crashed handler resumes the recorded state and never pushes the same ref twice.
  Nothing is spawned while a live worker holds the job's `flock`.
- `Test: F10`. `queued`, `pushing` and `pushed` are all `pending`: only a read-back that returns the ref at the
  SHA makes a job `verified`.
- A job older than 24 h that has not reached a terminal state becomes `expired`; records older than 7 days are
  pruned. `expired` is reported as a failure to verify, never as preserved.
- No recursive stop loop: the worker is a plain detached process, never an agent session, so it cannot end a
  turn and cannot trigger the handler. The handler's re-entry marker blocks a second enqueue for the same job
  key inside one turn.
- `Test: F11`. Destination unreachable, and the turn is offline: `blocked-remote-unreachable`, terminal for
  that attempt, with the local commit untouched and the job record left readable.

### D11 Dotfiles origin (contract item 6)

- `Test: F12`. (a) Origin authorisation. The dotfiles origin `github.com/zachbornheimer/dotfiles`, branch
  `history`, MUST be authorised by its own typed enrollment entry, not by the git-repository schema in D1
  (`kind = "mise-history"`), or by the existing mise origin declaration in
  `~/.config/mise/config.local.toml`. A git-repo enrollment MUST NOT authorise it and it MUST NOT authorise a
  git-repo checkpoint.
- (b) At a turn stop, `mise dot pull` is **report-only**. It rewrites live files, it writes nothing while a
  path has unsaved edits, staged changes or an unresolved conflict, it accepts no path filter, it saves a
  checkpoint first, and `mise dot undo` reverses it. The turn-stop path MUST NOT run it unattended.
- `Test: F13`. (c) Conflicts are resolved per path: `mise dot conflicts <path>` to inspect, then
  `mise dot pull --take-remote <path>` or `mise dot pull --keep-local <path>`. No blanket all-path flag is
  used. "Both sides preserved" means the losing version remains recoverable, not that both versions are live.
- `Test: F12`. (d) Divergence of a `manual-save` path such as `~/.gitconfig` (24 h cadence,
  `bin/dev-profile-mise-history-watchdog` L224-243 at `cce6da0a`) reports the outcome `scheduled`: it is
  waiting for its window, which is neither a conflict nor a blocker.
- (e) In `fetch-only` mode nothing is pushed, so local config changes are **not** propagated. The outcome MUST
  be `fetch-only`, and it MUST NOT be reported as preserved or as propagated. This box is in that mode today
  (`https://github.com/zachbornheimer/dotfiles.git`, branch `history`, declared in
  `~/.config/mise/config.local.toml`); installed mise here is 2026.11.4 while the owner cites 2026.11.5, so
  ZYS-9023 MUST re-verify `mise dot` semantics on the target machine before relying on any of (b)-(e).

### D12 Why the checkpoint namespace is not a hook bypass, and what a rejection reports

- `refs/heads/agent-checkpoints/<...>` is an ordinary branch ref. `hk`'s `["pre-push"]` step
  (`hk/hk.pkl` L499-507: `fix = true`, `stash = "git"`, `timeout = "30m"`) carries no ref filter, so it runs
  for any pushed ref, checkpoint namespace included. The design adds no exemption, no allow-list entry, and no
  special-case refspec: the push is a plain `git push <url> <sha>:<ref>` through the same hooks every other
  push goes through.
- `Test: F7`. When `hk` rejects the push, the job becomes `failed` with `blocked-hook-rejected` and the report
  states: the exit code, the last 20 lines of hook output, the ref, the checkpoint SHA, and that the local
  commit and worktree are untouched. Nothing is retried automatically, and the report is the whole of what the
  turn learns.

### D13 Fixtures ZYS-9023 must keep or add

One fixture per row; each MUST rule above cites the row that proves it. ZYS-9023 owns the suite; this ADR owns
the list. A rule whose fixture is missing is unproven.

| id | fixture |
| --- | --- |
| F1 | bare-repo remote; enrollment present, absent and invalid |
| F2 | `pushurl` differing from `url`: check and push address the same server, or block |
| F3 | `insteadOf` / `pushInsteadOf` rewrite; dry-run URL versus `get-url --push` disagreement |
| F4 | existing-ref collision at a different SHA; exact-ref idempotency boundary |
| F5 | directory/file collision: remote branch `agent-checkpoints` versus `agent-checkpoints/<id>` |
| F6 | same-SHA idempotency: `verified-present`, zero pushes, local commit unchanged |
| F7 | forbidden flags absent (hooks, force, lease, delete, hand-written tracking refs); hook rejection report |
| F8 | event choice: `willContinue !== true` publishes, a continuing turn does not; handler overrun of 30 s |
| F9 | retry and restart recovery: a `pending` job resumes, `flock` prevents a second worker, 3 attempts, 24 h expiry |
| F10 | uncertain push: `pushing`/`pushed` with no read-back stays `pending`, never preservation |
| F11 | offline sync: destination unreachable reports `blocked-remote-unreachable`, local work intact |
| F12 | concurrent change: destination moves between check and push; `manual-save` window reports `scheduled` |
| F13 | per-path conflict: `mise dot conflicts`, `--take-remote`, `--keep-local`, no blanket flags |

## Consequences

- Publication is opt-in per repository, so the default failure mode of this feature is "nothing happens". The
  cost is that a new repository stays unpublished until the owner edits one file.
- Turn-end work is bounded and never gates a turn. The cost is a window in which a job reads `pending`; the
  report says `pending` and never says preserved.
- Hooks and signing are not relaxed anywhere, so a key-less sandbox reports `blocked-unsigned` and a gate
  failure reports `blocked-hook-rejected` instead of publishing anyway.
- Two bases exist on purpose: the publisher's destination-advertised tips, and `hk`'s mainline-relative
  introduced-file judgement. Neither is derived from the other.

## Non-goals

Implementing the extension, the enrollment deployment or the mise reconciliation (ZYS-9023). Changing
credentials, permissions, branch protection, `hk` policy or any global security setting. Enrolling any real
repository (ZYS-9031). Ref retention and cleanup (ZYS-9030). Warn versus auto-commit for uncommitted work
(ZYS-8564). Porting or deleting existing `agent-hooks` rows or the shim extension (ZYS-9035).

## Links

- Blocks: ZYS-9023 (implementation and fixtures).
- Related: ZYS-8564 (provenance and commit creation), ZYS-9029 (`fetch-only` explanation), ZYS-9030 (ref
  lifetime), ZYS-9031 (which repositories to enroll), ZYS-9035 (fate of the archived `agent-hooks`
  consumers), ZYS-7609 (live dispatcher loads a repository `hooks.toml`; likely obsolete after ZYS-9035).

## Acceptance map

| criterion | where |
| --- | --- |
| 1 contract items 1-5 as testable rules | D1, D2, D3, D4, D5 |
| 2 enrollment path and schema, zero enrolled repositories | D1 |
| 3 extension file, dotfile entry, `agent_end`, not `session_stop`, no archived dispatcher | D9, D10 |
| 4 ref grammar and every outcome | D2 |
| 5 handler versus worker, durable job record, no recursion | D10 |
| 6 the five open design points, handler deadline, event choice | D6, D7, D4, D8, D9 |
| 7 contract item 6 as testable rules | D11 |
| 8 hook-bypass explanation and rejection report | D12 |
| 9 fixture list | D13 |
| 10 merged to the default branch and linked from ZYS-9023 | this file's commit and the ZYS-9023 comment |

## Verify

Run in `dev-profile` at the merged commit, with `<adr>` = `docs/adr/0001-turn-stop-checkpoint-publication.md`:

```bash
test -f <adr> && git log -1 --format=%H -- <adr>

for p in 'refs/heads/agent-checkpoints/' 'verified-present' 'blocked-collision' 'pushurl' 'pushInsteadOf' \
         'pending' 'D/F' '30 ?m' '30 ?(s|000 ?ms)' 'agent_end' 'willContinue' 'apps/omp/extensions/' \
         'config/mise.toml' 'archived' 'zero enrolled|no repositor(y|ies) (is |are )?enrolled' \
         'mise dot pull' 'mise dot conflicts' 'fetch-only' 'scheduled' 'blocked-unsigned'; do
  grep -qE -- "$p" <adr> || { echo "MISSING: $p"; exit 1; }
done

grep -nE -- '--[-]no-verify|HK[=]0|--[-]force|force[-]with[-]lease' <adr>   # prohibitions only; no direct token appears

git check-ref-format --branch 'agent-checkpoints/zachbornheimer-dev-profile/relay-zys-9028-adr/01a3f2c9b7-e7c1d2a3b4f5061728394a5b6c7d8e9f0a1b2c3d'

git cat-file -t <adr-commit-sha>   # prints: commit
```

The ADR records a contract; it does not implement it. Implementation proof is ZYS-9023's fixture suite above
plus its real-session verification.
