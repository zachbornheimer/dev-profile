---
name: find-past-omp-session
description: "Use when the user asks for the resume command or id of an earlier omp session (\"we had a session on X, find it\")."
---

Fast path: eval (py) `await archive.search("word", project="*", limit=6, silent=True)` for several keywords; each hit has `session` (id), `project`, `at`. Resume: `cd <project> && omp --resume <id-prefix>` (fallback `omp -r` in that dir; unverified which flag the build accepts).

Do NOT: rg/fd over ~/.omp/agent/sessions (takes 80-200s, hits timeouts, run_command bans `find`), or memory_search (returns noisy CI-log chunks). Archive search matches only prompts typed in the interactive editor, so use the user's own likely words. Offer 2-3 candidates with project and date.
