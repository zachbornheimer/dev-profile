---
name: parallel-edits-same-file-race
description: "Use before issuing several edit/edit_replace calls against the same file in one turn: parallel calls race and silently drop all but one edit."
---

# Parallel edits to one file lose edits

Observed twice (2026-11-09, ~/.config/nvim `core/sort.lua`, `LAYOUT.md`): three `edit_replace` calls on the same file sent in one parallel batch all reported "replaced 1 occurrence", but only one survived on disk. The others were overwritten (read-modify-write race). Line count and `grep` of the new text revealed it. A fourth call in the same batch using `edit` was refused as a stale tag, which is the visible form of the same race.

Rules:
- Several changes to ONE file go in ONE `edit` call (multiple `PUT` sections against the same `[path#TAG]`; ops are addressed to the snapshot, so list bottom-up or rely on the tool applying bottom-up), or in sequential calls that each re-read the fresh tag.
- Parallel calls are fine across DIFFERENT files.
- After any batch that touched a file more than once, `grep` for one distinctive new string per intended edit before moving on. A success message is not proof.

Short-term bridge: this is a tool defect (no per-file lock), not a skill-shaped fact. When tooling work is next picked up, hand the failing batch to the code improver so edit tools serialize or refuse concurrent writes to one path; then retire this skill.
