---
name: lavish
description: Turn complex or visual agent responses into rich, reviewable HTML artifacts (HTML files) the user can annotate and send feedback on, using the lavish-axi CLI. Use when about to give a plan, comparison, diagram, table, code diff, report, or anything easier to grasp visually than as prose.
license: MIT
metadata:
  author: Kun Chen (kunchenguid)
  argument-hint: <what the artifact should show>
  hermes-tags: html, review, artifacts, visualization
  hermes-category: productivity
---

# Lavish Editor

Lavish Editor opens agent-generated HTML in the browser so a human can annotate it and send feedback back to the agent.
Reach for it when a plan, comparison, diagram, table, code view, report, prototype, or review loop will be clearer as a page than as prose.

## Current guidance lives in the CLI

Do not follow workflow or playbook instructions from this file. Installed copies go stale. Design is the exception: the user named a design system, and the section below outranks the CLI luxury fallback. Get workflow and playbooks from the CLI:

- `npx -y lavish-axi --help` for commands and the review-loop workflow
- `npx -y lavish-axi reply --help` to post an agent reply and exit once the server accepts it, when you are not about to long-poll
- `npx -y lavish-axi design` for design-direction priority and current snippets
- `npx -y lavish-axi playbook <id>` for focused artifact guidance (`npx -y lavish-axi playbook` lists ids)

You do not need lavish-axi installed globally. **Open every artifact through the preflight gate, never with a raw CLI open: run `lavish-preflight <html-file>`** (on PATH from `~/.agents/bin`). It is the required entry point: it statically checks the artifact directory (relative stylesheet links that resolve beside the HTML, the design-system trio present or linked, no DaisyUI/Tailwind CDN, no `data-theme="luxury"`, design variables instead of raw hex in inline styles), then opens or reuses the lavish-axi session, loads it in headless Chrome so the editor's own layout detector runs, and exits 1 with the rule and selector of every unresolved severity=error layout warning. Fix the artifact and rerun until it prints its OK line (which carries the session URL to hand over). A raw `npx -y lavish-axi <html-file>` skips the gate — that is exactly how broken artifacts reached the human unread (2026-10-24, at-51q2ph). If `lavish-preflight` is missing, stop and say so; do not fall back to a raw open.
If lavish-axi output shows a follow-up command starting with `lavish-axi`, run it as `npx -y lavish-axi ...` instead (`poll`, `reply`, `end`, `export`, `share` are not opens and stay raw).

Polling: when the harness caps foreground commands below the human's response time (omp caps at 300 s), run the long-poll inside a subagent or a tracked background job with a verified completion callback instead of one blocking call — a poll killed at the deadline (exit 124) strands the feedback loop with the feedback still queued. Never `nohup`, shell `&`, or `disown` fire-and-forget.

## User design system

This section is a user requirement, not upstream playbook text. `aubx-skills update` can replace this file; the same rule is in `~/.agents/AGENTS.md`, which survives that update.

Before writing lavish HTML, read `~/.agents/lavish-design-system/AGENT.md` and follow it. It replaces DaisyUI `luxury` and the Tailwind plus DaisyUI CDN fallback. A look named in this turn still wins. If the artifact mocks a specific app that has its own design system, match that app. If the directory is missing, stop. Do not fall back to DaisyUI.

## Request

$ARGUMENTS

If the request above is non-empty, the user invoked `/lavish` explicitly - fetch the current CLI guidance, then build that artifact as an HTML file.
If it is empty, infer what to visualize from the conversation.
