# Wails v3 built-in MCP tools

Source: https://v3.wails.io/guides/mcp-service/

Requires the app compiled with the `mcp` build tag (`WAILS_MCP=1 wails3 dev` or
`go run -tags mcp .`). Default URL: `http://127.0.0.1:9099/mcp`.

## Tools

| Tool                | Purpose                                                                    |
| ------------------- | -------------------------------------------------------------------------- |
| `app_info`          | Application information: platform, architecture, all windows, MCP endpoint |
| `windows_list`      | List all windows with geometry and state                                   |
| `window_control`    | Focus, resize, move, fullscreen, devtools, reload, set URL, … (22 actions) |
| `js_eval`           | Evaluate JavaScript in a window (async body; `return` for a value)         |
| `dom_html`          | Get HTML of the page or a specific element                                 |
| `dom_query`         | Find elements by CSS selector — tag, text, bounds, visibility              |
| `screenshot_dom`    | Structural snapshot of the visible page (DOM-based, no pixels)             |
| `mouse_move`        | Animate the cursor to a point or CSS selector                              |
| `mouse_click`       | Click with animated cursor (left/right/middle, double-click, modifiers)    |
| `mouse_drag`        | Drag with animated cursor (supports HTML5 drag-and-drop)                   |
| `mouse_scroll`      | Scroll at a point or element                                               |
| `keyboard_type`     | Type text character by character with realistic events                     |
| `keyboard_press`    | Press a single key (Enter, Tab, Escape, ArrowDown, …) + optional modifiers |
| `call_bound_method` | Call a bound Go service method, e.g. `main.GreetService.Greet`             |
| `emit_event`        | Emit a Wails application event                                             |
| `wait_for_event`    | Wait for a Wails application event and return its data                     |

## Targeting

- Optional `window` arg = `WebviewWindowOptions.Name`. Omit → focused window, else first.
- Mouse/keyboard: `selector: "#submit-btn"` **or** `x`/`y` (CSS px, viewport).
- Drag: `from_selector` / `to_selector` (or coordinate pairs).

## Config env (process)

| Variable                | Default     | Description                     |
| ----------------------- | ----------- | ------------------------------- |
| `WAILS_MCP`             | unset       | CLI adds `mcp` tag when set     |
| `WAILS_MCP_HOST`        | `127.0.0.1` | Bind interface                  |
| `WAILS_MCP_PORT`        | `9099`      | Port (`0` = free port from log) |
| `WAILS_MCP_TIMEOUT`     | `30000`     | JS eval timeout (ms)            |
| `WAILS_MCP_HIDE_CURSOR` | unset       | Disable animated cursor overlay |

## Client notes

- Transport: **streamable HTTP** (not stdio).
- Do not leave a global MCP client entry for this URL; the server dies with the app.
- Production builds: no `mcp` tag → no server code, no port, no attack surface.
