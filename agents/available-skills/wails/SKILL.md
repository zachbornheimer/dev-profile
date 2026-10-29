---
name: wails
description: >
  Build, run, debug, and agent-verify Wails v3 desktop apps (Go + web frontend).
  Use when working on a Wails app, operator console, desktop UI, webview window,
  bound Go methods, or when you need to drive a running Wails UI via its built-in
  MCP server. Also: /wails, WAILS_MCP, wails3 dev/build, MCP LLM control.
---

# Wails v3

Wails v3 is Go + a web frontend in a native webview. The agent works the **Go
side**, the **frontend**, and — when verifying live UI — the **built-in MCP
server** that can drive a running app. Do not permanently register that MCP in
`~/.grok/config.toml`; connect only while an MCP-enabled binary is running.

Official MCP guide: <https://v3.wails.io/guides/mcp-service/>

## When this skill applies

- Scaffolding, building, or packaging a Wails v3 app
- Binding Go services to the frontend / calling bound methods from the UI
- Live UI verification (click, type, DOM snapshot) via the Wails MCP tools
- Debugging multi-window layout, events, or frontend↔Go wiring

## Non-negotiables

1. **MCP is opt-in and ephemeral.** Server code is only compiled with the `mcp`
   build tag. Production/default builds must **not** ship it.
2. **Do not add a permanent `[mcp_servers.wails]` entry** to Grok/Claude/Cursor
   config. The endpoint only exists while _this_ app is running with MCP.
3. **Prove UI claims on a fresh process** started after the build you care about.
   Unit tests do not prove webview behavior.
4. **Facade boundaries still apply** on the Go side — no raw `os`/`http`/`time`
   in domain packages; inject.

## Dev loop

### Run with MCP (agent can drive the UI)

```bash
# Prefer the Wails CLI so the mcp tag is applied automatically
WAILS_MCP=1 wails3 dev

# Or direct Go
go run -tags mcp .
```

On success the app logs something like:

```text
INFO MCP server started. Connect MCP clients using the streamable HTTP transport.
     url=http://127.0.0.1:9099/mcp
```

Default endpoint: `http://127.0.0.1:9099/mcp` (loopback only).

### Run / build without MCP (normal)

```bash
wails3 dev
wails3 build
# never set WAILS_MCP=1 for production artifacts
```

### Env (app process only)

| Variable                | Default     | Notes                                      |
| ----------------------- | ----------- | ------------------------------------------ |
| `WAILS_MCP`             | unset       | `1`/`true`/`on`/`yes` → CLI adds `mcp` tag |
| `WAILS_MCP_HOST`        | `127.0.0.1` | Keep loopback unless a trusted LAN test    |
| `WAILS_MCP_PORT`        | `9099`      | `0` = random free port (read from log)     |
| `WAILS_MCP_TIMEOUT`     | `30000`     | JS eval timeout (ms)                       |
| `WAILS_MCP_HIDE_CURSOR` | unset       | `1` hides the animated agent cursor        |

## Connecting an agent to a running app

Only after the app is up with the `mcp` tag and the log shows the URL:

```bash
# One-shot / session-local check — do NOT leave this in permanent user config
# Grok (this session or temporary project scope if you must):
#   Prefer: tell the agent the URL and use search_tool/use_tool after the
#   server is reachable; or project-scoped .grok/config.toml that is gitignored.
#
# Claude Code (session example from upstream docs):
claude mcp add --transport http my-wails-app http://127.0.0.1:9099/mcp
```

If Grok needs the tools mid-session and the server is not already connected:

1. Confirm something is listening: `curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:9099/mcp` (any non-connection-refused response means the port is open).
2. Use project-scoped config **only if the project wants it**, and keep it out of committed user-global config:

   ```bash
   # from the app repo — project scope, not user scope
   grok mcp add --scope project --transport http wails http://127.0.0.1:9099/mcp
   ```

3. Refresh MCP list (`/mcps` → `r`) or start a new session.
4. When done verifying, remove project entry if you added one:
   `grok mcp remove --scope project wails`

**Never** `grok mcp add` (user scope) for Wails. The permanent config was deliberately
rejected: Wails MCP is per-running-app, not a always-on service.

## MCP tools (verify-oriented)

Full detail: `references/mcp-tools.md`. Use these to prove UI end-state:

| Tool                                        | Use for                                         |
| ------------------------------------------- | ----------------------------------------------- |
| `app_info`                                  | Confirm app up, platform, windows, MCP endpoint |
| `windows_list` / `window_control`           | Multi-window geometry, focus, reload, devtools  |
| `screenshot_dom` / `dom_query` / `dom_html` | Structural state (not pixels)                   |
| `mouse_*` / `keyboard_*`                    | Drive UI with animated cursor + real events     |
| `js_eval`                                   | Read derived state / run small probes           |
| `call_bound_method`                         | Exercise Go bindings without clicking           |
| `emit_event` / `wait_for_event`             | App-event coordination                          |

Typical verify prompts (once tools are connected):

```text
Take a DOM snapshot of the main window.
Click the "Submit" button, then verify a success toast appears.
Call the bound method main.GreetService.Greet with argument ["World"].
```

Multi-window: pass `window` = `WebviewWindowOptions.Name`. Default is focused
window (else first). Selectors are CSS; mouse tools also accept `x`/`y`.

## Implementation defaults

### App shape

- `application.New` + `Window.NewWithOptions` — MCP needs **no** extra imports or
  registration; it starts inside `App.Run()` when the `mcp` tag is present.
- Name windows you care about (`Name: "main"`, `"editor"`, …) so MCP can target them.
- Bound Go services: keep them thin facades; domain logic stays testable without the webview.

### Frontend

- Prefer stable selectors agents can hit (`data-testid` / ids for primary actions).
- Controlled inputs: use MCP `keyboard_type` (per-character events), not paste hacks.
- Always-show-state UX still applies (waiting / working / done).

### Security

- MCP = full control of the app (DOM, JS, clicks, Go methods). Loopback only by default.
- DNS-rebinding protections reject non-local browser origins.
- Do not set `WAILS_MCP_HOST=0.0.0.0` outside a trusted isolated network.
- Strip MCP from release builds (default `wails3 build` already does).

## Done bar for Wails UI work

Before claiming a UI change works:

1. Build/run a **fresh** binary with the change.
2. If the claim is interactive, run with `WAILS_MCP=1` (or `-tags mcp`) and drive
   the real UI (MCP tools or eyes-on). Unit tests alone are not enough.
3. State evidence: process start time / binary identity, actions taken, DOM or
   event outcome observed. "Should work" is not done.

## Reference playground

Upstream example (all tools):
<https://github.com/wailsapp/wails/tree/v3-alpha/v3/examples/mcp>

```bash
cd v3/examples/mcp
go run -tags mcp .
# then connect a client to http://127.0.0.1:9099/mcp
```
