---
name: omp-auth-gateway-broker-gotchas
description: "Centralized authentication and gw/provider/model routing with omp-auth-broker (:8765), omp-auth-gateway (:4000), Vercel Token Pass (/v1/credits), and quota-pacing extension"
---

# omp auth-broker + auth-gateway (dev-env mcp-gateway box)

## Architecture & Purpose (verified 2026-11-13)
- **Why this exists:** Centralize authentication and model routing off the Mac via `omp-auth-broker` (`:8765`) and `omp-auth-gateway` (`:4000`) on `mcp-gateway.tail158749.ts.net` so switching computers, crashing the Mac, or running on VPS/E2B works seamlessly from one shared credential store and one OAuth token refresher.
- **Never run `omp` locally without `auth.broker.url`:** Anthropic OAuth refresh tokens are single-use; if a local session refreshes against `~/.omp/agent/agent.db` without `auth.broker.url`, it rotates the refresh token and causes the central broker to fail with `400 invalid_grant` (`disabled_cause` on `auth_credentials`). Recover by running `omp auth-broker migrate --from-local --include-oauth`.
- **Broker (`omp-auth-broker.service` on `mcp-gateway.tail158749.ts.net:8765`):**
  - Holds all 10 credentials across 8 providers in `/var/lib/omp-auth/broker/.omp/agent/agent.db`: `anthropic` (×2 OAuth), `google-antigravity` (OAuth), `openai-codex` (OAuth), `xai-oauth` (×2 OAuth), `github-copilot` (OAuth), `vercel-ai-gateway` (API key), `openrouter` (API key), and `typesafe` (API key).
  - Exposes `GET /v1/snapshot` and `GET /v1/usage` (authenticated with `~/.omp/auth-broker.token`).
- **Gateway (`omp-auth-gateway.service` on `mcp-gateway.tail158749.ts.net:4000`):**
  - Forward proxy backed by the broker (`models.yml` provider `gw`).
  - `/etc/omp-auth-gateway/clients.json` grants each client (`mac`, `vps`, `e2b`) access to `["openrouter/*", "anthropic/*", "google-antigravity/*", "openai-codex/*", "xai-oauth/*", "typesafe/*", "vercel-ai-gateway/*"]` (plus `"github-copilot/*"` on `mac`).
  - In `~/.omp/agent/config.yml`, always use `gw/<provider>/<model>` (e.g., `gw/anthropic/claude-sonnet-5-5:auto`, `gw/openai-codex/gpt-6.1-sol:auto`, `gw/xai-oauth/grok-4.7:auto`), NEVER `gw/openrouter/<vendor>/<model>` for models covered by subscriptions.
- **Vercel Token Pass & Quota Pacing (`~/.omp/agent/extensions/quota-pacing`):**
  - Only route Token Pass models (`vercel-ai-gateway/deepseek/deepseek-v4.1-flash`, `vercel-ai-gateway/zai/glm-5.3`, `vercel-ai-gateway/moonshotai/kimi-k3`) through `vercel-ai-gateway`; non-covered models immediately bill general Vercel cash credits (`balance`).
  - Query live Token Pass balance via `GET https://ai-gateway.vercel.sh/v1/credits` (`token_pass.remaining` out of `$80`, `token_pass.resets_at`).
  - Because `gw/*` routes OAuth refreshes on `mcp-gateway` rather than local SQLite and `health.model("gw")` returns `unknown`, `~/.omp/agent/extensions/quota-pacing` fetches `http://mcp-gateway.tail158749.ts.net:8765/v1/usage` + Vercel `/v1/credits`, enforces the 10% reserve boundary (`90%` max burn) and linear daily pacing toward reset day, and exposes `/quota`.
