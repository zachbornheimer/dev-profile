---
name: relay-edge-ops
description: "Diagnose, retry, deploy and smoke-test the Relay Linear agent (Cloudflare Worker + Workflow + E2B sandbox) in dev-env/cloudflare/relay-edge"
---

Relay runs entirely on Cloudflare + E2B (no VPS, tunnel or laptop). Code: `~/Developer/Personal/dev-env/cloudflare/relay-edge` (worker.mjs intake/dedupe/DO, run.mjs RelayRun Workflow, transcript.mjs, brief.mjs; container script `tools/container/e2b-session-container.sh`). Linear webhook URL is `https://relay.zachandaj.com/linear/webhook` (Worker route on the proxied zone).

## Deploy
`cd cloudflare/relay-edge && bun install --silent && ./deploy.sh` (needs `wrangler login` live; deploy.sh sets all secrets from 1Password and `gh auth token`). Run `wrangler` directly only for inspection (`bunx wrangler workflows instances list relay-run --json`); direct `wrangler deploy` misses the gitignored `dev-profile-done.txt` and fails.

## Read a ticket's session (no Linear UI)
Token: POST https://api.linear.app/oauth/token with grant_type=client_credentials, scope `read,write,app:assignable,app:mentionable`, client id/secret from `op://Zysys/Linear Relay Agent/{Client ID,Client Secret}`. (Stored access/refresh tokens are dead; do not use them.) Then GraphQL `issue(id:"ZYS-N"){agentSessions{nodes{id status activities(first:250){nodes{createdAt content{__typename ... on AgentActivityThoughtContent{body} ... on AgentActivityErrorContent{body} ... on AgentActivityResponseContent{body} ... on AgentActivityActionContent{action parameter}}}}}}}`. Guard jq with `(.content.body//"")`. `agentSessions(first:N)` at root is unreliable; go through the issue.

## Retry a failed session
POST a signed `prompted` webhook to relay.zachandaj.com/linear/webhook: body `{"type":"AgentSessionEvent","action":"prompted","agentSession":{"id":SID},"agentActivity":{"id":"x-<ts>","content":{"type":"prompt","body":"Retry this ticket."}}}`; header `Linear-Signature` = hex HMAC-SHA256 of the raw body with `op://Zysys/Linear Relay Agent/Signing Secret`, and a unique `Linear-Delivery` (duplicates are deduped). Add `"signal":"stop"` in agentActivity to test Stop. A follow-up while a turn runs queues as the next turn.

## Admin (Bearer RELAY_EDGE_TOKEN from ~/.config/relay/env)
GET /admin/status; POST /admin/release?session=SID (free a stuck slot); POST /admin/limits?timeoutMinutes=1-55|default (shorten turn limit to test continuation; reset to `default` afterwards).

## Known behaviors
- Sandbox template `dev-env-e2b-capacity` (4 GB); default E2B base OOM-kills omp. E2B sandbox lifetime is capped at 1 hour; turns cap at 40 min then auto-continue in a fresh sandbox resuming the Neon-stored omp conversation, but unpushed files are lost (prompt says push after every commit). Budget (run.mjs, 2026-11-11): a ticket keeps getting turns while it makes progress (new branch commit, merged PR, or todo `done`; gate.mjs `progressOf`), Hold after 3 turns in a row without progress, ceiling 10 turns.
- Hold is a high bar: the first `OUTCOME: hold` is sent back with a challenge; a second is accepted only with a `NEEDS ZACH: <input>` line (gate.mjs `exitGate`). Archived repository -> Canceled, not Hold.
- omp's own --max-time exit prints "Deadline exceeded" with exit 1: treated as out-of-time via `hitTimeLimit` (transcript.test.mjs).
- Prep failure `gh could not authenticate...` aborts with exit 125; transient failures are not retried automatically (retry by webhook above).
- Smoke tests: create a Linear ticket with delegate "Relay" (linear-personal/save_issue, team Zysys, project AI Tooling) targeting a safe repo task; close test PRs unmerged, delete `relay/zys-*` branches, cancel tickets.
- Commit scope for dev-env hook: `feat(relay-edge): ...`, subject <= 60 chars.
