---
name: new-service
description: Use when user says 'new service', 'scaffold service', 'create new api', or 'bootstrap project' — scaffolds entry point, HTTP server, OpenTelemetry, structured logging, and mise task contract. Supports Go, Node, Python.
user-invokable: true
disable-model-invocation: true
argument-hint: "<service-name> [--lang=go|node|python]"
allowed-tools: Bash Read Write Edit Glob Grep
---

# New Service

Scaffold a new service with observability from the start.

## Step 1: Parse arguments

- Service name from first argument (required — ask if not provided)
- Language from `--lang` flag or prompt user. Default to Go if ambiguous.
- Supported: `go`, `node`, `python`

## Step 2: Read the specs

- Read `~/.claude/rules/observability-standards.md` for the full observability checklist
- Read `~/.claude/rules/devops-standards.md` for the mise task contract, Trunk, Lefthook, and repo structure

## Step 3: Create directory structure

**Go:**

```text
<service-name>/
  cmd/<service-name>/main.go       # entry point, wires deps
  internal/server/server.go        # HTTP server setup
  internal/server/health.go        # /health and /ready handlers
  internal/telemetry/telemetry.go  # OTel SDK init (tracer + meter providers)
  go.mod
  mise.toml                        # standard task contract
  .trunk/trunk.yaml                # lint, format, and secrets checks
  lefthook.yml                     # Git hooks delegate to mise tasks
  .gitignore
  README.md
  docs/adr/001-service-creation.md
```

**Node (TypeScript):**

```text
<service-name>/
  src/index.ts                     # entry point
  src/server.ts                    # HTTP server (Express or Fastify)
  src/health.ts                    # /health and /ready handlers
  src/telemetry.ts                 # OTel SDK init
  package.json
  tsconfig.json
  mise.toml
  .trunk/trunk.yaml
  lefthook.yml
  .gitignore
  README.md
  docs/adr/001-service-creation.md
```

**Python:**

```text
<service-name>/
  src/<service_name>/main.py       # entry point
  src/<service_name>/server.py     # FastAPI with /health and /ready
  src/<service_name>/health.py     # health check handlers
  src/<service_name>/telemetry.py  # OTel SDK init
  pyproject.toml
  mise.toml
  .trunk/trunk.yaml
  lefthook.yml
  .gitignore
  README.md
  docs/adr/001-service-creation.md
```

## Step 4: Implement observability

Per `observability-standards.md`:

**Health endpoints:**

- `/health` → 200 `{"status": "ok"}` — no dependency checks, always fast
- `/ready` → checks database/cache connectivity (stub with TODO and clear contract)

**Structured logging:**

- Go: `slog` with JSON handler, trace ID extraction from context
- Node: `pino` with trace ID serializer
- Python: `structlog` with trace ID processor

**OpenTelemetry:**

- Initialize TracerProvider + MeterProvider with OTLP exporter
- Auto-instrumentation for HTTP server
- Manual span creation helper for business logic
- RED metrics: request.duration histogram, request.count counter, error.count counter
- W3C Trace Context middleware on HTTP server

## Step 5: All system boundaries through facades

Every system call in the scaffolded code goes through an injectable facade:

- `FileSystem` interface (not direct `os.ReadFile`)
- `Clock` interface (not direct `time.Now`)
- `HTTPClient` interface (not direct `http.Get`)

This is non-negotiable per the facade rule.

## Step 6: Initialize git

```bash
cd <service-name>
git init
wt step commit
```

## Step 7: Verify

Run `mise run ci` in the new service directory. All tasks must pass.
Run `mise run build` and start the service. Verify `/health` returns 200.

## ADR-001

Create `docs/adr/001-service-creation.md` documenting:

- Date created
- Language/framework choice and why
- Observability setup (OTel, structured logging)
- Service boundaries and contract (/health, /ready)
