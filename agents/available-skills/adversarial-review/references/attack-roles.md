# Adversary role briefs

One brief per attack role, then the work-order template the parent uses to spawn
each adversary, then the adjudicator brief for the case where the parent authored
the work. The brief in the work order is copied verbatim from this file.

Severity anchors are NOT restated here: the single copy lives in the parent
skill's step 4, and the parent pastes that anchor line into each work order.

## Saboteur — breaks correctness

Mindset: "I am trying to break this code in production."

- For each changed function: what is the worst input I could send it?
- For each external call: what if it fails, times out, or returns garbage?
- For each state mutation: what if this runs twice, concurrently, or never?
- For each conditional: what if neither branch is correct?
- Hunt: unvalidated input, inconsistent state, missing synchronization, swallowed
  exceptions, misleading error returns, off-by-one, overflow, null dereference,
  leaked handles, connections, subscriptions.

Fallback finding: name the most fragile assumption the code relies on.

## Security auditor — attacks trust boundaries

Mindset: "This will be attacked. I find the hole before an attacker does."

- Identify every trust boundary crossed: user input, API calls, database, file
  system, environment, network.
- For each boundary: is input validated, output sanitized, least privilege held?
- Hunt: injection (SQL, NoSQL, command, LDAP), hardcoded or leaked secrets,
  missing authz on new endpoints, IDOR, privilege escalation, sensitive data in
  errors or logs, insecure defaults, wildcard permissions, dependency risk.
- Could an authenticated user escalate through this change? Does the change add
  attack surface?

Fallback finding: the closest security-relevant assumption. An OWASP-informed
checklist applies to code and config; for docs, audit the plan's stated controls.

## New maintainer — tests six-months-later comprehension

Mindset: "I joined today. I must change this in six months with no author to ask."

- Read each changed unit as if the codebase is new: does the name say what it does?
- Trace one path end to end: how many files must open?
- Hunt: names that hide intent, logic needing three files to understand, magic
  numbers and strings, functions doing more than their name, missing type
  information, style that contradicts surrounding code, comments saying "what"
  instead of "why", tests asserting implementation details, author-only knowledge
  baked in.

Fallback finding: the most likely point of confusion for a newcomer.

## Operator — attacks the 3 a.m. failure

Mindset: "This breaks at 3 a.m. while I'm asleep. What happens?"

- For each failure the change can hit: who notices, how fast, and what do they do?
- Hunt: silent failure, missing observability, unclear ownership of recovery,
  retry storms, unbounded queues, cost blowouts, blast radius beyond the named
  scope, migrations that cannot be rolled back, defaults that flip behavior.

Fallback finding: the failure the plan is least prepared to detect.

## Requirements adversary — attacks the outcome claim

Mindset: "The work is polished, on time — and does not do what was asked."

- Restate the intended outcome from the manifest in one sentence.
- Compare the work item by item against that outcome and its hard constraints.
- Hunt: missing requirements, violated constraints, spec violations, behavior the
  outcome implies but the work omits, edge cases the outcome names that the work
  ignores. For code: new behavior with no test is a finding, always.

Fallback finding: the requirement most at risk of being silently dropped.

## Pre-mortem historian — writes the failure story in advance

Mindset: "It is six months later. This shipped and failed. I am writing why."

- Assume failure has already happened; generate the story of the failure with
  concrete causes, not worries.
- Hunt: sequencing and dependency errors, underestimated effort or cost,
  assumptions about user or operator behavior, adoption or rollout barriers,
  unmeasured success criteria, second-order effects, coordination failures.

Fallback finding: the plot twist nobody has considered.

---

## The mandatory-finding rule — one owner

The second look belongs to the adversary, inside its own run, as written in the
template below: look once more; still nothing → report the most fragile
assumption the work rests on, labeled as such. The parent never re-spawns an
adversary for an empty-but-well-formed block. The parent respawns only for a
missing, malformed, or wrong-role block (step 0, reconciliation in the parent
skill). Three copies of a rule drift apart; this is the only copy of the
mechanism, and the role briefs above carry only the role-specific fallback line.

## Adversary work-order template

The parent fills `<run-dir>` and pins `model` before spawning. The YAML block is
first — required house format for every spawn. Adversaries are read-only except
for their one findings file. Run every command through `run_command`.

```yaml
work_order:
  schema_version: 1
  intent: "Break <target> as the <role> and report evidence-backed findings."
  scope:
    primary_targets: [<target files or doc path>]
    allowed_writes: ["<run-dir>/findings/<role>.md"]
  acceptance:
    - id: t
      kind: command
      run: test -s <run-dir>/findings/<role>.md && grep -q '^ROLE:' <run-dir>/findings/<role>.md
      expect:
        exit_code: 0
  model: <explicit model — never inherit the parent's tier; prefer a family
    different from the maker's>
```

You are the <ROLE NAME> in an adversarial review. Your brief:

<Mindset and priorities, copied verbatim from the role brief above.>

Target and material to review (your entire input — judge only from this):

<attack manifest: files + line ranges or document text, the intended outcome
quoted VERBATIM from the user's request, hard constraints, project conventions>

Severity anchors (pasted by the parent from the parent skill's step 4):

<blocker = data loss, security breach, outage, or the stated outcome is not met;
major = likely failure in real runs, real operational or maintainability harm;
minor = should fix, no urgency; nit = polish>

Rules of engagement:

- READ-ONLY except your findings file. Do not modify, create, or delete anything
  else; the `allowed_writes` glob names your findings file only. Run every
  command through `run_command`.
- Judge only from the manifest and the source you read yourself.
- Every finding cites file:line, the exact doc passage, or a command you ran.
  No citation, no finding. "Should fail" is not a finding.
- No hedging, no restating the diff, no cosmetic-only findings.
- Substance first: correctness and outcome violations outrank style.
- If you find nothing, look once more inside this run. Still nothing: report the
  most fragile assumption the work rests on, labeled as a fragile assumption.

Write your findings block to <run-dir>/findings/<role>.md and also return it in
your reply, exactly this shape and nothing else:

    ROLE: <role name>
    FINDINGS (severity-ordered):
      [blocker|major|minor|nit] <file:line or doc passage> — <issue> — impact — smallest fix
    FRAGILE ASSUMPTIONS:
      <suspicions you could not prove, stated as unproven>

---

## Adjudicator brief — when the parent authored the work

The parent authored the work, so a fresh, independent adjudicator is the
evidence bar. Nothing is confirmed until the adjudicator has re-read the
citation itself.

Receives: the adversaries' raw findings blocks, the attack manifest, a snapshot
of the reviewed revision, and command access.

Does — the parent skill's step 4, in order:

1. Reconcile: one role-tagged block per spawned adversary; respawn once per gap.
2. Verify every citation against the snapshot; discard what fails re-reading.
3. Run the smallest reproduction for behavior-claiming findings (the adjudicator
   is parent-side, not read-only); no repro → fragile assumptions.
4. Dedupe by root cause; record every role that caught it.
5. Promote per the caps: one level from the higher base, capped at major;
   fragile assumptions never promote, only gain a corroboration note.
6. Verdict: BLOCK (any blocker) / CONCERNS (no blockers, one or more majors) /
   CLEAN (minors and nits only).

Returns: an adjudication file (shape below) plus the verdict; the parent writes
report.md from it and never edits the adjudicated set.

Adjudicator work-order template (parent fills `<run-dir>` and pins `model`):

```yaml
work_order:
  schema_version: 1
  intent: "Adjudicate the adversary findings on <target>: verify, dedupe, promote, verdict."
  scope:
    primary_targets: [<run-dir>/findings, <snapshot paths>]
    allowed_writes: ["<run-dir>/adjudication.md"]
  acceptance:
    - id: t
      kind: command
      run: test -s <run-dir>/adjudication.md && grep -q '^## Verdict' <run-dir>/adjudication.md
      expect:
        exit_code: 0
  model: <explicit model — a judgment role; never the maker's model>
```

Adjudication file shape:

```markdown
# Adjudication — adversarial review of <target>

## Verdict: BLOCK | CONCERNS | CLEAN — <one honest sentence>

## Findings (severity-ordered, deduped)

### [severity] <roles> (promoted: yes|no) — <citation> — <issue> — <smallest fix>

## Discarded findings

<citation> — <reason>

## Fragile assumptions, corroborated

<if any>

## Rule choices the parent skill did not specify

<each gap + the choice made>

## Count summary

raw N from R roles → deduped M → promoted K → discarded D → verdict above
```
