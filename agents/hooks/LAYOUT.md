typesafe-skill-pick.py: UserPromptSubmit routing; observe context, invoke TypeSafe, emit decision
lib/skill_conversation.py: bounded parallel routing-context observation with per-session fallback
suggested-timeout-for.py: time one hook with hyperfine; observe run logs; decide p95 timeout; print JSON list
lib/suggested_timeout.py: run-log types, percentiles, p95-to-timeout decision
session-recall.sh: SessionStart; observe the cwd's repository, one read-only psql query over memory_chunks, decide a digest within a character budget, print nothing on any failure
