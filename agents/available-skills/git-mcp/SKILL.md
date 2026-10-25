---
name: git-mcp
description: Use when the main/orchestrator session needs git reads (status, diff, log, show, branch list) via MCP, or when setting up the git MCP server on a new machine. Lifecycle (add, commit, checkout, create_branch) uses `wt` — see worktrunk-index.
---

# git MCP server

Git **reads** go through the `git` MCP server (`mcp-server-git`, from the
official `modelcontextprotocol/servers` project): `git_status`, `git_diff`,
`git_diff_staged`, `git_diff_unstaged`, `git_log`, `git_show`, `git_branch`.

Lifecycle (`git_add`, `git_commit`, `git_checkout`, `git_create_branch`) must
use `wt` per `worktrunk-index`, not git MCP tools. `git_reset` remains unused.

`orchestrator-only.py` (`~/.claude/hooks/orchestrator-only.py`) still denies
destructive `Bash git` (`reset --hard`, `push --force`, `branch -D`, `clean -f`,
pathspec `checkout`/`restore`, `stash drop/clear`) as a backstop. Push still
goes through `Bash git ...`, still gated.

## Setup (per machine)

Registered per-user in `~/.claude.json` under `mcpServers.git` (this is
Claude-Code-specific runtime config, not chezmoi-templated — re-add it by hand
on a new machine, or script it):

```json
"git": {
  "command": "uvx",
  "args": ["mcp-server-git"]
}
```

Requires `uvx` (from `uv`) on PATH — no separate install step, it fetches the
package on first launch. Verify with `uvx mcp-server-git --help`.

After adding the entry, run `/reload-plugins` (or restart the session) to pick
up the new server. Call any `mcp__git__*` tool with `repo_path` set to the
target repo's absolute path.
