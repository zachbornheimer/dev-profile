---
name: mcp-ops
description: Use when wiring GitHub, Linear, Sentry, PagerDuty, or AWS into an agent task, or building any MCP-driven pipeline. LOAD before spawning any MCP-connected worker that touches financial or insurance data.
---

# MCP Ops

Give agents real access to org systems without creating a blast-radius catastrophe.
Core principle: **present MCP servers as a code API, not raw tool calls; scope every
agent's access; keep the cache hot.**

## Gotchas — read these first

- **The egress allowlist is a capability grant, not a destination filter.** Allowing
  `api.anthropic.com` means allowing file uploads to any Anthropic account — including
  an attacker's. Every function reachable through an allowed domain is attack surface.
  A MITM proxy inside the agent's environment must validate token provenance per
  request, not just check the destination host.

- **A poisoned README is a prompt injection vector.** GitHub MCP loads a malicious
  `README.md` straight into context even if the connector passed a malware scan.
  Classify every tool return before it enters the model's context window. The
  classifier doesn't need to be the reasoning model — a small, fast model is enough.

- **Never borrow a human OAuth token.** The agent inherits everything that person can
  do. Revoking the person's account is the only way to stop it. Use dedicated service
  accounts with least-privilege grants, scoped per task or channel.

- **Switching models mid-thread rebuilds the cache and costs more.** A 100k-token
  Opus thread that asks Haiku a "cheap" question pays full uncached input on all 100k
  tokens. Fork a fresh worker with a hand-off summary instead.

- **Changing the tool set mid-conversation busts the cache.** Use `defer_loading`
  stubs; never add or remove tools during a live session.

- **Symlink resolution must happen BEFORE path validation** — a symlink inside an
  authorized folder can escape to arbitrary paths if you validate the path first.

- **Credentials must never enter the agent environment.** Host keychain or secrets
  manager only. The agent gets a per-session scoped token, revocable independently
  of the user.

- **GitHub's REST limit (5,000/hr) is shared across every tool and agent — and a
  fleet of agents polling `gh` in loops exhausts it fast.** When `gh run list` / any
  REST call 403s with "rate limit exceeded," don't wait for the hourly reset — switch
  transport: (1) **GraphQL is a SEPARATE bucket** — `gh api graphql` (e.g. a commit's
  `checkSuites`/`statusCheckRollup`) still works when REST is dead; (2) the **GitHub
  MCP** (`mcp__plugin_github_github__*`) uses a distinct app-installation token with its
  own budget. And stop _tight-polling_ `gh` for slow external state (a deploy rollout,
  a CI run): poll the underlying system directly (ECS/AWS for a rollout) or
  `ScheduleWakeup`, and touch `gh` only at completion. `gh api rate_limit --jq
  .resources` shows the per-bucket reset. Same shape for any REST-metered MCP: a
  different transport or token often has separate quota — reach for it before you sleep.

## Workflow for any MCP-connected task

1. **Scope first.** What does THIS agent need to read/write? Assign a service account
   with only that. Read `references/security.md`.
2. **Present tools as code.** Materialize the `./servers/` filetree; let the agent
   import the modules it needs rather than loading all tool definitions upfront.
   Read `references/servers-pattern.md`.
3. **Cache-safe setup.** Lock the system prompt, tool stubs, and model before the
   first turn. Never change any of them mid-session. Read `references/cache-hygiene.md`.
4. **Classify outbound.** Route AWS / GitHub / Linear / Sentry / PagerDuty calls
   through typed tools the harness can gate, log, and trace.
5. **Store every transcript.** Every agent run is the compliance and audit artifact.
   Never suppress or truncate it.

## The three reference files

- `references/servers-pattern.md` — `./servers/<server>/<tool>.ts` filetree; filter
  in the runtime (see 5 rows, not 10,000); PII tokenization at the MCP-client
  boundary; persist reusable code to `./skills/`. Token cut: 150k → 2k (98.7%).

- `references/security.md` — per-agent identity / service accounts; egress allowlist
  as capability grant + MITM proxy fix; classify every tool return; quarantine pattern
  for untrusted content; symlink validation order; read-only AWS profiles for
  investigation; transcript as compliance artifact.

- `references/cache-hygiene.md` — never switch models mid-thread; inject volatile
  info via `<system-reminder>` in the next message; `defer_loading` stubs instead of
  removing tools; cache-safe forking for compaction; monitor cache-hit-rate like
  uptime.
