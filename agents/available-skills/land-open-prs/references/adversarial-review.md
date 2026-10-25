# Adversarial review (lander)

Fresh-context `reviewer`. It did not write the diff. It does not merge. Direct
findings only.

Read, in order: PR body, issue comments, review threads (open and resolved), bot
comments by login, then the full diff.

## Four questions (all required)

1. **Claim** — What does the PR say it is for? Quote the body, not the title.
2. **Problem** — What is the real problem in the product/repo? If the body and
   the codebase disagree, the codebase wins.
3. **Fit** — Does this diff solve that problem? Missing, partial, or a different
   change than claimed: say so.
4. **Harm** — New vulnerability, weaker test, swallowed error, extra
   maintenance, leaked vendor in the workflow, or a junior trap?

No survey. No "looks good if tests pass." Each finding is one concrete change.

## Output shape

```text
CLAIM: <one sentence from the body>
PROBLEM: <one sentence from the code/product>
FIT: does | partial | does-not — <why>
FINDINGS:
- [must] <file:line> <what to change>
- [must] ...
HARM: none | <vuln / weaker-test / maintenance>
VERDICT: act | hold
```

`hold` only for an item in the parent skill's Human gate. Otherwise `act`.

## Acting on it

Findings are a to-do list for the implement worker. Empty `FINDINGS` is allowed
only when FIT is `does` and HARM is `none`.

A bot or human thread may be rebutted only with evidence recorded on the PR: a
reproduction that disproves the finding, a targeted test that exercises it, or
an authoritative contract that settles it. Evidence can close a false finding;
authority or confidence cannot. If the evidence does not remove the ambiguity,
rewrite the code or prose until a junior cannot hit the same trap, then resolve
the thread.

Do not:

- close a thread with an unrecorded or authority-only rebuttal
- defer a finding to a follow-up ticket unless the user named that hold
- treat a resolved-but-unfixed thread as done — re-open the issue in the
  FINDINGS list
