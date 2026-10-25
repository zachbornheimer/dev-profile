---
name: land-ticket
description: >-
  Use when the user says /land-ticket, "land ticket", names a Linear identifier
  (ZYS-123, SAH-456), or gives an explanation of tickets to land. Implement and
  land exactly one issue this session. Route ZYS- to personal Linear
  (linear-personal) and SAH- to work Linear (linear-sah). A second unrelated
  identifier is a /new handoff, not more work here.
---

# Land Ticket

Execute **exactly one** named Linear issue this session. `tickets` files;
`triage-lead` closes from census evidence; `land-open-prs` drains PRs. This
skill implements then lands.

## Route

`python3 scripts/inventory-project.py ZYS-806 SAH-1` (argv or stdin) →
`[{id, workspace, mcp}]`. Mapping lives in `scripts/route.py`
(`workspace_for` / `mcp_server_for`). `ZYS` → personal / `linear-personal`.
`SAH` → work / `linear-sah`. Unknown prefix is an error, not a personal default.

Work `SAH-` from this Grok session: if the `linear-sah` MCP is missing, do not
pretend to land — report the blocker. Prefix routing still works in tests.

## Spine

1. Parse identifiers from the user text. If they gave an explanation instead
   of ids, search Linear (correct MCP from any prefix that appears; else
   personal first for ZYS-shaped, work for SAH-shaped).
2. Take **one** issue: the first identifier, or the single match from the
   explanation.
3. `prompt-writer` → `implement` for the code change. Isolation `worktree`
   when the target is a git repo; isolation `none` for `~/.agents`.
4. Land: `save_issue` on the routed MCP with `statusType=completed`, and the
   ticket's own verify evidence in the comment/body. If a PR is required,
   merge proof like `land-open-prs` (explicit merge OID is an ancestor of
   default).
5. Default no-questions. Hold only for destructive/irreversible work or two
   surviving product intents.

## Second ticket → `/new`

If the user (or a later turn) names a **second** identifier that is not the
in-flight one: **do not implement it**. Reply with a pasteable handoff whose
**first line is `/new`**, then a truncated first-message:

```text
/new
/land-ticket ZYS-123 one-line intent
Do not spawn tmux.
```

## Gotchas

- Do not reopen ZYS-756.
- Missing work `linear-sah` MCP ≠ landed. Report the blocker.
- Never silent-default an unknown prefix to personal.
- After editing `~/.agents`, `chezmoi re-add ~/.agents` before `chezmoi apply`. Run `~/.agents/hooks/chezmoi-guard.py --check` first — apply of unre-added live work silently reverts it (ZYS-755).
