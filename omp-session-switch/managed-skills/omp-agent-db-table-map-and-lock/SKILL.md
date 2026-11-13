---
name: omp-agent-db-table-map-and-lock
description: "What each ~/.omp/agent/agent.db table holds, why credentials/cache must not move to the Neon SESSIONS_DB_URL, how VPS and E2B arms get omp state, auth-broker risks, provider OAuth ToS limits and the credential-brokering research verdict, and the schema-init write-lock bug"
---

# agent.db table map, the startup lock, and why it isn't a Neon candidate

Measured 2026-11-09 on the local fork (`~/Developer/Personal/oh-my-pi`). `agent.db` is 11 MB.

## What lives where

Neon (`SESSIONS_DB_URL` in `~/.omp/.env`) holds **only** session transcripts (`omp_session_files`), `memory_chunks`, and `atask`. `agent.db` was never migrated, so everything else is local SQLite:

| Table(s) | Rows (2026-11-09) | Nature |
|---|---|---|
| `auth_credentials` | 8 | live OAuth tokens / API keys (openai-codex, anthropic x2, github-copilot, xai-oauth x2, typesafe api_key, google-antigravity) |
| `auth_credential_refresh_leases`, `auth_credential_blocks`, `auth_change_revision`, `auth_schema_version` | 0 | cross-process refresh mutual exclusion + invalidation counter |
| `cache` | 24,062 | model response cache; most of the 11 MB |
| `usage_history`, `model_usage`, `model_perf`, `client_usage`, `command_usage`, `hint_usage`, `clients` | ~5,300 | usage telemetry |
| `threads` | 87 | session index; `rollout_path` is machine-local |
| `stage1_outputs`, `jobs`, `settings`, `meta`, `notice_claims` | ~35 | local scratch |

## Why credentials must not move to Neon (as a plain table behind SESSIONS_DB_URL)

- E2B and VPS already hold `SESSIONS_DB_URL`; credentials behind the same URL are readable by untrusted ticket text running in a sandbox. Any Neon credential store needs its own role/schema and app-level encryption with the key held outside Neon.
- `auth_credential_refresh_leases` is refresh mutual exclusion; remote latency worsens contention.
- Credential reads are on every request and every 401 retry; local page cache is sub-millisecond.
- `pollExternalChanges()` is a per-process network poll (43 processes observed holding `agent.db`); pins Neon compute.
- `AuthCredentialStore` (`packages/ai/src/auth/store.ts:233`) has only SQLite and Remote (broker) implementations; no Postgres one exists.

Only defensible Neon candidates: `*_usage` / `model_perf` telemetry. Never `cache` or `threads`. A Neon-primary + broker-materialized design is viable only with a write-through layer, encryption before Neon, a lease so one broker refreshes, and writing the rotated refresh token to Neon before use.

## How the other compute arms get omp state (2026-11-10, dev-env)

- **VPS** (`tools/vps/vps-up.sh:918-948`): one-time snapshot only when the box lacks `~/.omp/agent/agent.db`. `sqlite3 .backup` of `agent.db` + `models.db`, plus `config.yml`, `models.yml`, `~/.config/omp/*`, `extensions agents overlays`. Includes all credential rows; never syncs back, so Mac and VPS refresh the same tokens independently.
- **E2B / Relay** (`tools/container/e2b-session-container.sh`, `relay-machine.sh`, `cloudflare/relay-edge`): never copies `agent.db`. Gets `OPENROUTER_API_KEY`, `GH_TOKEN`, `SESSIONS_DB_URL` by env; `relay_omp_models` overwrites `config.yml` to an OpenRouter model. Transcripts resume via Neon path `%/.omp/agent/sessions/conv-<label>/%.jsonl`. Sandboxes run untrusted ticket text (`brief.mjs`). Sandbox tailnet join already exists (`e2b.py`, `TS_AUTHKEY`; container script unsets it at line 572).

## Auth-broker (already implemented in the fork)

`omp auth-broker serve` + `RemoteAuthCredentialStore`, selected by `OMP_AUTH_BROKER_URL` / `auth.broker.url` / `~/.omp/auth-broker.token`; `omp auth-broker migrate --from-local` uploads. State 2026-11-09: token file present, no broker URL configured, clients still local SQLite. Server (`packages/ai/src/auth-broker/server.ts`): flat bearer allow-list (`bearerTokens`, empty = no auth), plain HTTP (Tailscale is the transport security), background refresher every 60s for tokens expiring within 5 min, SSE snapshot stream, AES-GCM client snapshot cache, upload endpoint. No per-token scopes. [INFERENCE, unverified] snapshots carry real credentials to clients, so a client of the broker holds real tokens.

Hosting on Hetzner `mcp-gateway` (`tools/vps/mcp-gateway-up.sh`; tailnet-only; agentgateway v1.7.0): one token reads all; plain HTTP; Hetzner root reads plaintext SQLite; `--recreate` saves only tailscaled.state, `config.yaml.tpl`, `plesk-stdio.py` to `mini`, so broker data is lost without a Neon primary or backup; the `iptables` drops (4600, 15000, 15020, 15021) are runtime-only and a reboot clears them (fix before adding a port); broker must be the only refresher.

## Research verdict (2026-11-10, web)

- **Common solution = CB4A Model A (proxy/egress injection)**: agent never holds the credential; gateway injects it just in time (IETF draft-hartman-credential-broker-4-agents-00, Mar 2026; Posta/agentgateway posts Jul-Aug 2026). Model B (short-lived token to agent) leaves a secret in agent memory; Model C (hand over long-lived, revoke later) is weakest. Broker/vault is the critical target; keep the KEK outside the DB host (KMS/OpenBAO); KEK beside data is catastrophic.
- **E2B Secrets** (docs.e2b.dev/secrets): egress proxy injects stored secrets into outbound HTTPS per host; write-only; rotate without restart; any process in the sandbox hitting that host gets it used; failed lookup forwards the request without the header (401, not leak). E2B **workload identity** issues per-sandbox JWT-SVID (`spiffe://id.e2b.dev/<project>/<sandbox>/<exec>`), federable to Anthropic WIF (API orgs only, not subscriptions).
- **Rotation races**: single-flight refresh behind a per-session lock; check for a newer token before exchanging. Codex CI guide (learn.chatgpt.com/docs/auth/ci-cd-auth): one `auth.json` per runner/serialized stream, never share across concurrent jobs or machines; API keys recommended for automation. OpenAI says a Codex refresh token tolerates reuse for ~1 hour (openai/codex#10332, Feb 2026), but "already used" errors still occur.
- **ToS**: Anthropic (code.claude.com/docs/en/legal-and-compliance) bans subscription OAuth tokens in any other product incl. Agent SDK, and bans developers collecting/storing/intermediating Claude.ai credentials; plan limits assume ordinary individual usage. Google (antigravity.google/terms item 6) bans third-party tools with Antigravity OAuth, penalty suspension of Antigravity and Gemini CLI accounts. OpenAI permits third-party harnesses with Codex subscriptions (Register, Feb 2026, via an OpenAI staff statement; not primary). Copilot and xai-oauth policies not found.
- Ready-made proxies: Infisical Agent Vault (MITM proxy, dummy-key substitution; OSS repo says new setups should use Infisical platform); agentgateway OSS has `backendAuth.oauthTokenExchange`, but the token vault is Solo Enterprise; whether OSS can inject refreshed provider OAuth tokens is unconfirmed.
- **Decision applied (not user-confirmed)**: automated arms (E2B, VPS) use API key or workload identity for Anthropic and Google; subscription OAuth only for interactive Mac use. E2B and VPS share one path: broker refreshes, egress injection; broker pushes refreshed access tokens into E2B secrets. Untested: whether omp runs against a dummy credential through a proxy (OAuth providers like Codex may parse the token client-side). Test with Codex first.

## The real startup failure: write lock during schema init

`SqliteAuthCredentialStore.#initializeSchema` (`packages/ai/src/auth/sqlite-credential-store.ts:636-845`) runs ~25 `CREATE ... IF NOT EXISTS` / `INSERT OR IGNORE` statements on **every** launch even when `auth_schema_version` is current (8). Each booting `omp` takes a write lock; under contention startup dies with `SQLITE_BUSY` in `#createAuthChangeTrackingObjects` during `discoverAuthStorage`.

Diagnosis: `sqlite3 agent.db "PRAGMA busy_timeout=5000; BEGIN IMMEDIATE; ROLLBACK;"` is <10 ms when idle, so a failure is a transient boot storm; `lsof agent.db` counts contending PIDs. Fix: skip the DDL body when `schema_version` / `auth_schema_version` match.

## Reading it without blocking

`sqlite3 -readonly ~/.omp/agent/agent.db ...` is safe while omp runs. `read` renders it: `agent.db:auth_credentials`, `agent.db:usage_history?limit=20`.
