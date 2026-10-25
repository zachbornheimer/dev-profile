# MCP Security — Scope, Contain, Classify, Audit

Sources:

- Anthropic, "How we contain Claude across products" (2026-05-25)
- Anthropic, "Zero Trust for AI agents" (2026-05-27)
- Anthropic, "Agent identity: a new access model" (2026-06-24)
- Devin operating-contract-playbook.md (read-only AWS profiles)

## Per-agent identity — never borrow a human OAuth token

Every agent gets **its own service account** in each system it touches. Acting under
a person's account means the agent inherits everything that person can do; revoking
the person's account is the only way to stop it.

| System    | Pattern                                                           |
| --------- | ----------------------------------------------------------------- |
| GitHub    | GitHub App installation token, scoped to specific repos           |
| Linear    | API key tied to a `claude-agent` workspace member                 |
| Sentry    | Auth token with `project:read` only                               |
| PagerDuty | Read-only API key scoped to specific services                     |
| AWS       | `sah-readonly` / `nq-readonly` IAM role (see below); never mutate |

Admins define a baseline profile (what Claude can do in this channel / task) and
override per compartment. **The scoping question is:** "What can this agent do in
this compartment?" — not "What can this user do?"

Revoking the agent identity ends its access everywhere that identity was used — far
easier to manage than auditing individual agent actions across dozens of user
accounts.

## The egress allowlist is a capability grant — not a destination filter

**The wrong mental model:** "allowed domains are safe destinations."
**The right mental model:** "every function reachable through an allowed domain is
now attack surface."

Real incident: allowing `api.anthropic.com` gave an attacker a path to upload
files to their own Anthropic account. The agent read a malicious file from the
workspace, followed its instructions, and called the Files API using the attacker's
embedded key. The egress proxy saw `api.anthropic.com` and passed it through. The
sandbox worked correctly; the data still left.

**The fix:** a MITM proxy **inside the agent's environment** that:

1. Intercepts every outbound request to allowed domains.
2. Validates that the auth token is the agent's own provisioned session token.
3. Rejects requests carrying any foreign credential.
4. Blocks server-side fetch headers that enable SSRF.

The proxy lives inside the sandbox, not on your servers, because only the sandbox
knows token provenance. From your API's perspective, a sandboxed agent request is
indistinguishable from any other client.

## Classify every tool return before it enters context

A trusted connector does not mean trusted data. GitHub MCP can load a poisoned
`README.md` straight into the model's context despite passing a malware scan.

Run a classifier — a small, fast model; it does not need to be the reasoning
model — on every tool return before passing it to the agent. Inspect for:

- Prompt injection attempts (instructions masquerading as file content or issue text)
- Unexpected command patterns in ostensibly inert data
- Exfiltration triggers (instructions to encode data and POST it elsewhere)

Route tool calls through a proxy that feeds returns to the classifier first. Once a
poisoned return has steered the agent into exfiltrating data, the log shows a
successful authorized API call — there is no after-the-fact signal to find.

## Quarantine pattern for untrusted content readers

When an agent must read untrusted content — PRs from external contributors, Sentry
issues with user-supplied stack traces, PagerDuty alerts carrying external data —
split the work:

1. **Reader agent** — read-only access to the source; NO write credentials; NO
   privileged access. Returns a **structured summary** (typed JSON, not raw text)
   to the orchestrator.
2. **Actor agent** — receives the structured output; holds the write credentials.
   Never sees the raw untrusted content.

The chain breaks injection: the reader summarizes, the actor acts on the summary.

**Multi-agent trust caveat:** sub-agent output is NOT implicitly safer than raw tool
results. If the orchestrator treats sub-agent output as higher trust ("it came from
us"), you have introduced a new injection vector. The reader may have been steered
by the content it read. Classify structured output from sub-agents too before the
actor acts on it.

## Symlink resolution order

Always resolve symlinks **before** path validation, never after:

```python
# Wrong: validate path, then resolve — symlink escapes the check
if path.startswith("/workspace"):
    real = os.path.realpath(path)  # /workspace/link → ~/.aws/credentials

# Correct: resolve first, then validate
real = os.path.realpath(path)
if not real.startswith("/workspace"):
    raise PermissionError(f"path escape attempt: {real}")
```

A symlink at `/workspace/creds` pointing to `~/.aws/credentials` passes the naive
check and hands the agent full credential access.

## Credentials never enter the agent environment

- Credentials live in the host keychain or a secrets manager; never in the agent's
  env, its filesystem, or any mounted directory the agent can read.
- The agent gets a **per-session scoped token**, minted at startup, revocable
  independently of the user's credentials.
- When a secret must flow through a workflow (read from a store, passed to a
  downstream call), the MCP-client tokenization layer handles it — the model sees
  a token like `[SECRET_1]`, not the real value.

## Read-only AWS profiles for investigation (from Devin playbook)

For production investigation, always use the read-only IAM roles. Never mutate AWS
during an investigation — mutating a live system on a hypothesis you haven't proven
is a blast-radius multiplier.

```bash
# SAH production — tail errors
aws logs tail /ecs/zyins-production \
  --since 5m --follow \
  --profile sah-readonly --region us-west-2 \
  --filter-pattern "?ERROR ?FATAL ?error ?fatal"

# NQ app — tail errors
aws logs tail /ecs/nq-app \
  --since 5m --follow \
  --profile nq-readonly --region us-west-2

# Health check
curl https://zyins-production.example.com/health   # 200 = healthy, 503 = degraded
```

Profile to account mapping:

| Profile      | Account ID   |
| ------------ | ------------ |
| sah-readonly | 514598028285 |
| nq-readonly  | 257336559192 |

Log groups: SAH: `/ecs/zyins-production`, `/aws/lambda/sah-prod-pagerduty-relay`,
`/ecs/freefexquoter`; NQ: `/ecs/nq-app`, `/ecs/nq-app-worker`.

## Every transcript is the compliance artifact

The agent transcript — the full turn-by-turn record of tool calls and returns — is
the audit log. It proves what the agent did, when, and with whose credentials.

- Store every transcript; never suppress or truncate.
- Because the agent acts under its own service accounts, actions also land in each
  connected system's own logs (GitHub audit log, Linear activity, AWS CloudTrail,
  Sentry audit trail). The transcript correlates them.
- On financial/insurance data: the transcript is the SOC 2 / HIPAA evidence. Treat
  it with the same retention policy as a human audit log.
- For PagerDuty incidents: attach the relevant transcript excerpt to the incident
  timeline. The agent's investigation steps are evidence, not ephemera.

## Trust bootstrapping gotcha

Project-local config (`.claude/settings.json`, hooks, `CLAUDE.md`) can execute
**before** a user trust prompt is shown. Treat project-open, config-load, and
localhost listeners as untrusted input from the internet — parse and execute them
only after an explicit trust decision is made, not because they arrived before the
trust boundary.
