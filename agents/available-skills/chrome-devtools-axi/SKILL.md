---
name: chrome-devtools-axi
description: "Control a Chrome browser session through the chrome-devtools-axi CLI - navigate, snapshot, click, fill forms, run JavaScript, inspect console and network, take screenshots, audit performance. Use whenever a task needs a real browser: opening or testing a web page, clicking through a flow, extracting page content, or debugging a website."
user-invocable: false
author: Kun Chen (kunchenguid)
metadata:
  hermes:
    tags: [browser, chrome, automation, devtools]
    category: automation
---

# chrome-devtools-axi

Agent ergonomic interface for controlling Chrome browser sessions. Use this instead of the old chrome-devtools MCP/code interface.

Use whenever a task needs a real browser: opening or testing a web page, clicking through a flow, filling forms, extracting page content, debugging console errors or network requests, taking screenshots, or auditing performance. Skip it when a plain fetch/curl suffices.

## Current guidance lives in the CLI

Get current commands, flags, environment variables, and contextual next-step hints from the installed CLI:

- `chrome-devtools-axi --help`
- `chrome-devtools-axi <command> --help`

The CLI is installed globally at `/opt/homebrew/bin/chrome-devtools-axi`. If it is not on PATH, use that absolute path. Only fall back to `npx -y chrome-devtools-axi` if the global install is unavailable.

## Local operation

Choose a unique `CHROME_DEVTOOLS_AXI_SESSION` per agent task and use the same name for all browser commands in that task. Set `CHROME_DEVTOOLS_AXI_IDLE_TIMEOUT_MS=1800000` when starting the session to clean up abandoned browsers after 30 minutes. Do not export a shared port: named sessions derive their own ports.

For example:

    CHROME_DEVTOOLS_AXI_SESSION=<unique-task-name> CHROME_DEVTOOLS_AXI_IDLE_TIMEOUT_MS=1800000 chrome-devtools-axi open https://example.com

Use a Chrome for Testing binary via `CHROME_DEVTOOLS_AXI_EXECUTABLE_PATH` when available, to avoid macOS routing user links to a headless copy of ordinary Chrome.

Pass element references back exactly as printed. After any state-changing action, verify the resulting state with a fresh snapshot, eval, or screenshot before reporting success. Stop the task's bridge when finished with `CHROME_DEVTOOLS_AXI_SESSION=<unique-task-name> chrome-devtools-axi stop`.

This is a native CLI/skill integration, not an MCP server registration. Existing unrelated Docker MCP gateway integrations are independent and should remain untouched.
