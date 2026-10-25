# Embed this skill

One path everywhere. Do not copy the decision tables into prompts.

```text
~/.agents/available-skills/atask/SKILL.md
```

Workers load that file. Optional extra: `references/when.md` and
`references/file.md` when the material is a long review.

## Prompt / work order (file only)

After the `work_order` fence, or in a required_inputs list:

```text
Load ~/.agents/available-skills/atask/SKILL.md.
Analyze: <paths or pasted findings>.
Inspect atask list in <cwd or --project>.
File missing objectives. Reuse duplicates. Do not claim or implement.
```

## Handoff / worker contract

```text
Tracker: atask. Skill: ~/.agents/available-skills/atask/SKILL.md
You may add/update tasks for outcomes you discover.
You may not claim, verify complete, or edit product files unless this
handoff also names a claim ID and implementation authorization.
```

## Other skills and docs

Point, don’t fork:

```markdown
Filing agent work: load `atask` (`~/.agents/available-skills/atask/SKILL.md`).
Product tickets: `tickets`. Gas City city-internal: `gc bd`.
```

## Orchestrator

This skill on an **orchestrator** means: persist the plan as atask ids before
spawning implementers. Each implementer gets **one** claimable id. Do not
spawn until ids exist and the user authorized implementation.

## What “analyze and file” covers

Reviews, ChatGPT atoms, audit notes, failing tests, leftover TODOs in a
named file, and “we should also…” asides in a thread — if they are real
outcomes with a proof. It does not mean mining the whole monorepo unasked.
