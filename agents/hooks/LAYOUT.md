typesafe-skill-pick.py: UserPromptSubmit routing; observe context, invoke TypeSafe, emit decision
lib/skill_conversation.py: bounded parallel routing-context observation with per-session fallback
suggested-timeout-for.py: time one hook with hyperfine; observe run logs; decide p95 timeout; print JSON list
lib/suggested_timeout.py: run-log types, percentiles, p95-to-timeout decision
worktree-provision.py: WorktreeCreate; observe event, decide dest/repo, execute via wt
lib/worktree_provision_worktrunk.py: wt switch create-or-reuse at an exact dest
lib/worktree_provision_git.py: git facts, Claude-precreate adopt, stray cleanup
lib/worktree_provision_tools.py: chezmoi source lookup and dependency provision
worktree-cleanup.py: WorktreeRemove via wt remove, git fallback
lib/worktree_cleanup_worktrunk.py: wt remove adapter
scope-guard.py: PreToolUse + Stop; deny an off-task call / block a turn that ended off-task, with the correction as the reason
lib/scope_decide.py: the one scope policy — user task from the transcript, prefilter, Jev OffTopic judgment, correction cap, judgment log
session-recall.sh: SessionStart; observe the cwd's repository, one read-only psql query over memory_chunks, decide a digest within a character budget, print nothing on any failure
