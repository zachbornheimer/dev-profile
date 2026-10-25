# Autoresearch — causal review of {SESSION_LABEL}

```yaml
work_order:
  schema_version: 1
  intent: "Explain one agent session as a causal chain ending in a single structural root cause, returned as the entire reply, with zero writes."
  scope:
    primary_targets:
      - {SOURCE}            # annotated export, e.g. /tmp/output.json or a thread URL
    allowed_writes: ["**"]
  acceptance:
    - id: root-cause-chain
      kind: manual
      run: "Report opens with a one-line structural root cause, cites transcript item ids for material claims, states its provenance, and names a file plus a red test for every surviving fix."
```

READ-ONLY: the allowed_writes glob grants read access only. Do not create, modify, or delete any file, and do not run a shell command. Return the report as your entire reply.

## Deliverable

A causal chain that explains this session, ending in the one structural gap that produced its failures. The review questions at the bottom are prompts for building the chain, not a structure to fill in. A report that answers each question in isolation, without connecting them, has failed even if every answer is accurate.

## Method

1. **Completeness first.** Before stating any end state of the session, verify the export against the raw session log ({RAW_LOG}, if available). Exports truncate: both A/B runs that read only the export were confidently wrong about how the session ended, and the one run that checked the raw log was the only one that got the end state right. State your provenance in the report: which sources you read, and whether the export was complete. Resolution order when sources disagree: the raw log beats the export; raw items beat annotation summaries; measurements beat impressions.
2. **Read raw items, not annotation summaries.** Every material claim cites the item id that shows it. Where a summary and the raw item disagree, the raw item wins. If you hold a claim the raw items later contradict, report the contradiction as a correction — corrections are evidence the evidence bar was met.
3. **Build the chain before writing.** For each significant action ask why it happened, and keep asking until the cause is a mechanism that lives in a file: a rule, a hook, a tool schema or description, a skill trigger. If the answer is "the agent chose to," the chain is not done — find what made that choice the locally rational one.
4. **Find the functional-completion moment.** Locate the first point where the user's actual request was satisfied, then account for everything after it. Work after that moment is the primary object of study; say what generated it.
5. **Clear the census.** {CENSUS_BLOCK — if a pre-run census is provided, paste it here.} A diagnosis that explains only the counted events has not explained the run: name the waste classes the census cannot see — unsolicited execution, deliverable-missing re-asks, verdict reversal, orphaned-process recovery, intent-level user recovery — and account for them before proposing anything. If no census was provided, enumerate these classes yourself from the raw items.
6. **Present in your native contract.** If your machinery has evidence levels, disproof conditions, comparative tables, or falsifiable experiment designs, use them. This template is a floor, not a shape; do not flatten your output into it.

## Report shape

1. Open with the one-line root cause: the structural gap such that fixing it makes the session's individual failures unlikely. If it cannot be said in one line, you have parallel findings, not a chain — keep digging.
2. The chain: item-cited, cause to effect, ending at the structural gap.
3. Corrections: claims you held that the raw items contradicted.
4. Provenance: which sources you read, and whether the export was complete.
5. Fixes: each mapped to the root cause it kills, each naming the file it touches and a red test that fails today. A fix without both is a wish; drop it. Drop anything that would only be a memory.
6. If nothing survives, say so.

## Review questions — prompts, not sections

- What was the actual real-world result of the flow?
- What was accomplished?
- How would a human have approached this?
- Did the user get frustrated — when, why, and what is the earliest divergence before the onset?
- What would the user have expected to see? What did they want the session to be?
- Everything that went wrong, little and big.
- What would the magic version have been?
- What in the harness didn't support the magic — name the file each gap lives in?

## Acceptance

A reader who never saw the session can, from your report alone, state in one sentence why it went wrong and point to the item ids and files that prove it.

---

<!-- Provenance of this template: merged from the A/B prompt experiment in
mastra:thread:13fc33c4-13c7-431b-bdeb-60dbd0f3dd14 (learner × GLM 5.3, 2026-10-23/24).
The light skeleton and the "questions are prompts, not sections" framing come from the
user's prompt (best report: forensics.z — native machinery, detected export truncation).
Method clauses 2-5 come from the heavier prompt (consistent depth in both glm runs).
Clause 1 (completeness/provenance) and the census-class list are the additions the A/B
proved missing: both glm runs were snapshot-blind and wrong about the end state.
Supersedes ~/Downloads/prompt.md (which retained a dangling "the census below is pre-run"
reference after its census block was removed). -->
