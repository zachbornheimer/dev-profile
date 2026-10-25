# Protocol Specification

## 1. Roles

### Planner / reviewer

Usually a cloud reasoning surface. It owns:

- interpreting the human's task;
- deciding what local work should happen next;
- generating one bounded runner;
- reviewing deterministic evidence;
- deciding whether the task is proved, needs repair, or is terminal.

It does **not** own local filesystem truth.

### Controller

A local UI/transport automation. It owns:

- finding the newest runner file offered by the planner;
- saving it locally;
- preventing duplicate UUID execution;
- executing the runner synchronously;
- attaching the resulting ZIP to the same conversation;
- retrying bounded UI transport failures.

It does **not** decide whether repository work is correct.

### Runner

A single-use local program. It owns:

- the concrete bounded operation for one UUID;
- local commands/effects;
- evidence collection;
- packaging.

It does **not** choose the next task after review.

### Human

The human retains authority over:

- goals;
- credentials/secrets;
- destructive operations;
- commit/push/merge policy;
- stopping or changing the loop.

---

## 2. Correlation identity

Each run has one UUID v4:

```text
<uuid>
```

Derived names:

```text
runner file       run-<uuid>.py
evidence zip      <uuid>.zip
run directory     implementation-defined, keyed by <uuid>
```

A UUID is immutable and single-use.

---

## 3. State machine

```text
PLANNER_READY
    |
    | emits run-<uuid>.py
    v
RUNNER_AVAILABLE
    |
    | controller semantically finds Download file
    v
SAVED
    |
    | controller checks UUID has not run before
    v
EXECUTING
    |
    | synchronous runner process
    v
EVIDENCE_READY
    |
    | ~/Downloads/<uuid>.zip exists
    v
RETURNING_EVIDENCE
    |
    | controller focuses chat, attaches ZIP, sends
    v
REVIEW_COOLDOWN
    |
    | pause ~60 s
    v
WAITING_FOR_NEXT_RUNNER
    |
    | bounded scan ~15 s cadence
    +-------------------------------> RUNNER_AVAILABLE

Terminal outcomes:
- PROVED
- BLOCKED
- HUMAN_ACTION_REQUIRED
- ABORTED
```

A transport/controller failure is not a product-task terminal outcome.

---

## 4. Controller invariants

The known-good controller behavior is:

1. Use semantic reverse focus traversal (`Shift-Tab`) instead of full Accessibility-tree crawling.
2. Reset focus with a harmless keystroke/delete sequence before traversal.
3. Find the button whose accessible title/description is `Download file`.
4. Once found, stop traversal completely and activate it once.
5. Wait for the native Save panel using the focused `AXTextField`.
6. Save to `~/Downloads`.
7. Never re-execute an already-seen UUID.
8. Execute the runner synchronously; do not crawl for another runner while execution is active.
9. After execution, attach the ZIP, press Enter, and use at most the controller's bounded send retry.
10. After returning evidence, pause 60 seconds before scanning.
11. Thereafter scan at about 15-second intervals.
12. Maintain a global bounded deadman (historically 10 minutes for UI waiting; runner subprocesses have their own deadlines).
13. Do not screenshot-hot-loop merely because ChatGPT is temporarily not frontmost.

Avoid full recursive Accessibility-tree traversal; it can hang.

---

## 5. Runner invariants

### 5.1 Synchronous

The controller process invocation blocks until the runner returns.

### 5.2 Bounded

Every potentially blocking operation has a deadline:

- subprocess;
- model/harness call;
- polling loop;
- lock acquisition;
- UI wait (controller-side).

### 5.3 Evidence-first failure

Internal failure is data:

```json
{
  "outcome": "TICKET-NOT-PROVED",
  "error": "..."
}
```

The runner still packages evidence and exits `0`.

### 5.4 Safe Git defaults

Without explicit authorization:

```text
NO commit
NO push
NO merge
NO reset
NO clean
```

Uncommitted user/project work must be preserved.

### 5.5 Deterministic before semantic

Verification order:

```text
focused deterministic checks
full deterministic checks
format/vet/lint/build
repo-specific gate / baseline attribution
semantic review only where needed
```

### 5.6 Baseline attribution

A repository may already be red. A runner must avoid treating unrelated baseline failures as attributable regressions.

When possible, compare:

```text
current finding
vs
HEAD / isolated baseline finding
vs
files actually touched by this run
```

---

## 6. Evidence return contract

The primary artifact is:

```text
~/Downloads/<uuid>.zip
```

The controller must treat an existing ZIP with that name as the runner's output only when it came from the current execution.

If the controller creates a fallback ZIP because the runner ZIP is missing, `report.json` must make that transport failure explicit. A fallback ZIP is not evidence that the runner's requested operation happened.

---

## 7. Duplicate/race semantics

Two local executions of the same UUID are invalid.

Possible consequences include:

- both runners writing the same evidence directory;
- one report overwriting another;
- false "baseline changed" observations;
- duplicate model/harness calls;
- one run packaging another's state.

Controller deduplication is mandatory.

If duplicate starts are still possible, expensive coding-harness authoring should additionally use a kernel-released interprocess lock.

---

## 8. Security / privacy

Evidence collection should be scoped.

Do not blindly include:

- `.env`;
- SSH keys;
- cloud credentials;
- token files;
- browser profiles;
- arbitrary home-directory files.

Prefer explicit file lists, Git diffs, command outputs, and source snapshots known to be relevant.

---

## 9. Versioning

Protocol documents and JSON Schemas use a `schema_version`.

Backward-compatible additions should not change existing field meanings. Breaking changes should increment the major schema version and be documented in `CHANGELOG.md` if/when one is introduced.
