# Evidence Bundle Contract

## ZIP name

```text
<uuid>.zip
```

## Minimum layout

```text
term.out.txt
report.json
run-<uuid>.py
evidence/
```

## Recommended repository-run layout

```text
term.out.txt
report.json
request.json
run-<uuid>.py
evidence/
├── git/
│   ├── before-status.txt
│   ├── before-diff.txt
│   ├── before-names.txt
│   ├── after-status.txt
│   ├── after-diff.txt
│   └── after-names.txt
├── patches/
│   ├── initial.diff
│   └── repair-1.diff
├── verification/
│   ├── focused.txt
│   ├── all-tests.txt
│   ├── vet.txt
│   ├── diff-check.txt
│   └── repo-gate.txt
├── source/
│   └── <targeted source snapshots>
└── model/
    ├── request.txt
    ├── stdout.txt
    └── stderr.txt
```

Only include model/harness files when a model/harness was actually used.

## `report.json`

`report.json` is the authoritative machine-readable run result.

Recommended fields:

```json
{
  "schema_version": 1,
  "uuid": "uuid",
  "ticket": "optional",
  "operation": "proof-only",
  "repo": "/absolute/path",
  "started_at": "ISO-8601",
  "finished_at": "ISO-8601",
  "outcome": "TICKET-PROVED",
  "acceptance_proved": true,
  "deterministic": {
    "focused": 0,
    "all_tests": 0,
    "vet": 0,
    "diff_check": 0
  },
  "changed_files": [],
  "baseline_notes": [],
  "unmet_acceptance": [],
  "error": null
}
```

## Outcome vocabulary

Projects may add ticket-specific names, but these semantic categories are useful:

```text
PROVED
NOT_PROVED
BLOCKED
HUMAN_ACTION_REQUIRED
TRANSPORT_FAILED
RUNNER_FAILED_BEFORE_OPERATION
SOURCE_SNAPSHOT_CAPTURED
CANDIDATE_DETERMINISTIC_GREEN
```

Do not infer `PROVED` merely because the runner process exited `0`.

## `term.out.txt`

Should include timestamped runner/controller-relevant diagnostics sufficient to answer:

- What command ran?
- What did it return?
- Where did it fail?
- Did packaging run?
- What ZIP path was produced?

## Source snapshots

Use source snapshots when semantic correctness depends on untracked/new files that a normal `git diff HEAD` would not fully expose.

This is especially useful when:

- implementation files are untracked;
- the proof reviewer needs to inspect an abstraction boundary;
- a controller/runner race made the Git diff ambiguous.

## Controller fallback ZIP

If the controller packages a fallback artifact because the expected runner ZIP did not appear, it must be unmistakable in the report, for example:

```json
{
  "outcome": "TRANSPORT_FAILED",
  "runner_zip_missing": true
}
```

A fallback ZIP must never masquerade as task evidence.
