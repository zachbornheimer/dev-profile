---
name: reuse-documented-features
description: "Before hand-rolling a script, config, automation or workflow, or proposing a new tool, search the indexed documentation of the user's stack (mise, Nix, others) with docs_search and adopt a documented feature that already does the job."
---

# Reuse a documented feature before building

The user's stack (mise first) has features that replace custom scripts: tasks, file watching, hooks, dotfiles, bootstrap, macOS defaults, launchd agents, package installs. Agents miss them because the docs are large and unread. `docs_search` searches them by meaning.

## When
About to write a shell script, config management, scheduler, installer, watcher or wrapper; about to use a different tool (Nix, Make, a cron job, a hand-written launch agent) for a job; or the user asks "is there a way to...".

## Do
1. Describe the **need** in plain words and call `docs_search` with no `project` filter. Do not name the tool you were about to use. If working inside one project, optionally `exclude_project` it.
2. If a hit covers the core of the job, adopt it: cite the page URL, show the smallest config that does it, and say what it replaces. Do not write custom code for a job a documented feature handles. If it covers only part, use it for that part and say what remains.
3. Read the **Index state** lines. `stale` means the project has moved since indexing: run the printed `refresh` command (local checkouts need the `git pull` it names) before concluding anything.
4. **No hit is not proof.** The index lags; a feature may be newer. Check the project's changelog or `web_search`, then decide. Say which you did.
5. If the project is not indexed at all, index it with `docs_index` (public docs: `scope: "global"`), then search. Docs reachable only as HTML are indexed from their git source, not scraped.

## Do not
- Use it for this repo's own code (`grep`/`find`), session history (`memory_search`) or live web facts (`web_search`).
- Report "mise can't do this" from one empty search.

## Tools
`docs_search` (read) and `docs_index` (write), in `~/.omp/agent/tools/docs_search` and `docs_index`; design in `docs_search/DESIGN.md`; objective at-4h9sbf. Tool files load at session start, so a new session or a restart is needed after they change.
