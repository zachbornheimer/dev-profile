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
