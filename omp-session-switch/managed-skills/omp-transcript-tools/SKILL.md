---
name: omp-transcript-tools
description: "Use when reading, analyzing or changing omp native session-transcript tools (get_transcript, get_recent_turns, create_session_handoff_doc, extract_hypotheses, learn_from_transcript) or fetching a session transcript by id like omp:01a1c0b2-…."
---

# omp transcript tools

**Fetch by id:** call `get_transcript` `{sources:["omp:<uuid>"], annotate?:true}`. It writes JSONL under `~/.local/share/capability-replicas/annotated/` (`.transcript.jsonl` plain, `.annotated.jsonl` annotated; header line then one `{"type":"item",turn,role,id,…}` per item). `read`/`grep`/`jq` the returned `path`. Never hand-grep `~/.omp/agent/sessions`. `get_recent_turns` = last few turns inline; `create_session_handoff_doc` = takeover note. The old `get_annotated_transcript` omp tool is removed (the Mastra workflow of that name still exists).

**Layout (native tools, `~/.omp/agent/tools/`, not a git repo):**
- `get_transcript/` owns the shared code: `reader/`, `session_export.ts`, `annotated.ts`, `annotate_sources.ts`, `pricing.ts`, `transcript_jsonl.ts`, `get_transcript.ts`, test helpers.
- `extract_hypotheses`, `learn_from_transcript`, `create_session_handoff_doc`, `get_recent_turns` import these via `../get_transcript/...`. Never re-copy them into a tool dir; fix once in `get_transcript/`.
- Tests: `cd ~/.omp/agent/tools/<tool> && bun test`; after touching shared code run all five tool dirs.
- New or renamed tools load only after an omp restart (`omp_restart`). Not a git repo: back up first (`tar czf`).
- `annotate:true` also writes `.annotated.json`, which `extract_hypotheses`/`learn_from_transcript` consume; keep that contract.
