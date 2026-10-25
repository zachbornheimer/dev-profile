---
name: isjac-daily-support-triage
description: >-
  Use when triaging ISJAC member/webmaster email into Zysys Linear and fixing
  site bugs — tech/product only (not ops reply drafting). Also for “any ISJAC
  support issues?” or establishing bot support loops.
---

# ISJAC daily support triage

Reusable loop for ISJAC support → Linear → **fix product/tech bugs**.

## Scope (Zach / Chief of Staff)

**In scope:** site bugs and tech — login/auth, membership/payment product failures, broken forms/cart/account, embeds, deploy-related breakage, security/plugin/infra that blocks the site.

**Invariant:** All members are WP users — that is how WP works. Paid membership must create or link the WP user. "Member with no WP user" is not a normal ops state. Claim flow is recovery for a broken invariant, not the steady-state model.
**Out of scope:** drafting or sending ops/member replies that are pure relationship/process (Summit hosting asks, “contact Chuck for charts,” stale event Q&A, board/collab intros). File a ticket only if there is a **product** angle; otherwise skip or one-line staff flag — do not spend cycles on reply drafts unless Zach asks.
**Ops money** (refunds, manual Woo cancel): ticket AC for human/staff unless Zach prioritized that ops path.

## Sources (discover live)

- **Email:** ISJAC Gmail (`*@isjac.org` / webmaster). Prefer thread view; `newer_than:14d` or unread + support keywords.
- **Tickets:** Linear workspace with project **ISJAC** / team **Zysys**. Run `tickets` skill pre-flight; never hardcode labels — `list_issue_labels`.
- **Code:** GitHub `ZAB-AI-LLC/isjac-site` canonical for bots. Read repo `AGENTS.md` before edits.

## Steps

1. **Scan inbox** — login, membership, cancel, payment, error, broken, unable, cart, account, form fail. Skip Google security, newsletters, Search Console, Clarity, pure collab proposals, and pure ops/process asks with no site bug.
2. **Classify** — **product/tech bug** (fix) vs ops-only / needs-human-reply (skip drafts; optional one-line flag) vs noise.

   TypeSafe gate (optional, fail-open):

   1. Write `{subject, from, body}` to `state.json`.
   2. `python3 ~/.agents/skills/typesafe-ai/scripts/typesafe.py classify-isjac --json < state.json`
   3. If `source` is `typesafe`, use `kind` (`product_bug` / `ops_skip` / `noise`) and `in_scope`.
   4. If `source` is `fallback` or `kind` is `unknown`, continue with this classify step as written.

3. **Dedup Linear** — project ISJAC by reporter, email, symptom. Link related (e.g. cancel UX → ZYS-363 class).
4. **File tickets** — product/tech only. `tickets` template + Gmail URL + live labels.
5. **Fix** — prioritize auth lockouts, payment/cart, account/form breakage. Prefer agentmux `run --goal-file` / local worktrees when Cloud Agents unavailable.
6. **Report** — ADHD digest of **tech** ticket ids + status. No pile of “draft reply to X” next actions.

## Non-goals

- No member email as the user without explicit send approval
- No ops reply drafting as part of the daily/weekly loop
- No Linear closes without machine evidence (`triage-lead`)
- No tickets for marketing/spam/security-alert noise

## Daily cadence

Weekday morning: run this loop. Zero actionable **tech** threads → stay quiet. New tech tickets/PRs → ping with ids and links.
