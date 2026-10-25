---
name: gas-city-self-improve
description: Use when improving a Gas City setup from real transcript evidence; mine repeated work for missing role agents, formulas, skills, or routing rules, then create open beads with acceptance checks for human-approved implementation and verification.
---

# Gas City self-improve

Mine real sessions for recurring work that the city does not model yet. The
output is open Beads work, not an automatic edit.

## Contract

Every candidate must name one category: `role`, `formula`, `skill`, `routing`,
or `guard`. It must include evidence from at least three distinct sessions,
show the closest existing city capability, and state the missing durable
behavior. Reject one-offs, provider-specific quirks, and candidates already
covered by an existing role, formula, or skill.

## Run

Harvest deterministic evidence first:

`uv run ~/.agents/available-skills/gas-city-self-improve/scripts/harvest-gas-city.py --city <city> --days 30 > /tmp/gas-city-self-improve.ndjson`

Then cluster the records, have a skeptic check each cluster against the current
city and `~/.agents/available-skills`, and keep only survivors. The script reads
transcripts and city inventory; it does not mutate either.

## Bead gate

For each surviving candidate, create one open bead. Do not close it during
harvest or clustering. The bead body must include:

- category and proposed name;
- three or more distinct session IDs and dates;
- the repeated user-visible outcome;
- current role/formula/skill gap;
- files or skill path allowed to change;
- explicit acceptance commands;
- a verification observation at the real Gas City or skill boundary;
- `gc.self_improve.status=proposed` and `gc.self_improve.evidence_count`.

Use `gc bd create` or the city's bead helper. Attach the candidate evidence to
the bead, then leave it open for implementation. A proposal is not shipped.

## Verification lifecycle

Route an approved bead through the smallest fitting workflow, usually
`build-basic` for a new role/formula or `review` for a prompt-only change. The
worker must prove the new capability on a fresh Gas City process, not by
reading the file it just wrote. Review must check that the candidate was not a
one-off and that the city catalog exposes the new formula or role.

Close only after the verification evidence is attached and the acceptance
commands pass. If the candidate is rejected, close it with the rejection reason
and `gc.self_improve.status=rejected`; do not silently delete the evidence.

Never auto-install a role, formula, skill, or global rule. Human approval is the
boundary between a proposed self-improvement bead and a live capability.
