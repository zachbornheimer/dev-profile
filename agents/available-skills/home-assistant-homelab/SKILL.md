---
name: home-assistant-homelab
description: USE when working on Home Assistant automations, integrations, or device config for this house. Read docs/automations.md and docs/home-assistant-agent-contract.md first; keep changes config-driven, safety-first, and verified against live state.
---

# Home Assistant Homelab

This skill is a pointer to the repo contract, not a duplicate of it.

- Read [docs/home-assistant-agent-contract.md](/Users/zbornheimer/homelab/docs/home-assistant-agent-contract.md) first.
- Use [docs/automations.md](/Users/zbornheimer/homelab/docs/automations.md) for the canonical automation registry.
- Prefer the smallest config-driven change that preserves safety and capture
  integrity.
- Verify live state when the request touches existing automations, devices, or
  integrations.

Gotchas:

- Do not weaken fire-safety or lossless-capture behavior without an explicit
  replacement path.
- Do not guess entity IDs or device behavior when the repo or live state can be
  checked.
- Do not treat UI-only tweaks as the canonical configuration when repo-managed
  config exists.
