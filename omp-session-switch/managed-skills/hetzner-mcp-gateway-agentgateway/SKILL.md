---
name: hetzner-mcp-gateway-agentgateway
description: "Use when inspecting, configuring, rotating secrets for, or adding MCP servers to the centralized Hetzner agentgateway MCP server at mcp-gateway.tail158749.ts.net:4600/mcp via 1Password vault Agent Gateway (MCP: Display Name items)."
---

# Hetzner `mcp-gateway` (`agentgateway`) Operations

## Overview
- **Endpoint:** `http://mcp-gateway.tail158749.ts.net:4600/mcp` (LAN alias: `http://mcp.ai.lan.zachandaj.com:4600/mcp`)
- **Host:** `zbornheimer@mcp-gateway.tail158749.ts.net` (`SSH_OPTS`: `-i ~/.ssh/claude_macmini -o IdentitiesOnly=yes -o IdentityAgent=none`)
- **Provisioner:** `~/Developer/Personal/dev-env/tools/vps/mcp-gateway-up.sh` (`--status`, `--ensure`, `--recreate`, `--auth`, `--mint-client`)

## Zero-File 1Password Configuration (`Agent Gateway` vault)
`/usr/local/bin/mcp-gateway-sync` (driven every 5s by `mcp-gateway-sync.timer`) synthesizes `/run/mcp-gateway-config/config.yaml` directly from 1Password vault **`Agent Gateway`**, validates with `agentgateway --validate-only`, and restarts the `agentgateway` container only when the vault digest changes. `/etc/mcp-gateway/config.yaml.tpl` and `mini-lan:~/.local/state/dev-env/mcp-gateway/config.yaml.tpl` are retired.

Each MCP target is an item in vault **`Agent Gateway`** titled **`MCP: <Display Name>`** (for example: `MCP: Linear Personal`, `MCP: Linear SAH`, `MCP: Firecrawl`, `MCP: Freshdesk NinjaQuoter`, `MCP: Opik MCP`, `MCP: PagerDuty SAH`, `MCP: Plesk`, `MCP: Zendesk SAH`). The display name after `MCP:` is automatically slugified to the lowercase hyphenated target name (`MCP: Linear Personal` → `linear-personal`, `MCP: Linear SAH` → `linear-sah`).

### 1. Remote HTTP MCP (`MCP: <Display Name>` with `host`)
- `host`: upstream MCP URL (e.g. `https://mcp.linear.app/mcp`, `https://mcp.firecrawl.dev/v2/mcp`)
- `credential` *(optional)*: sets `policies.backendAuth.key.value`
- `headers.<Header-Name>` *(optional, section `headers` or prefix `header.`)*: sets `policies.requestHeaderModifier.set`
- `enabled` *(optional)*: `false` to disable without deleting

```bash
op item create --category="API Credential" --title="MCP: My Service" --vault="Agent Gateway" \
  "host[text]=https://mcp.example.com/mcp" \
  "credential[password]=<SECRET>"
```

### 2. Stdio MCP (`MCP: <Display Name>` with `cmd`)
- `cmd`: executable path inside the `mcp-gateway:local` container (e.g. `/root/.local/bin/opik-mcp`, `/usr/local/bin/zd-mcp-server`)
- `args` *(optional)*: JSON array (e.g. `["/usr/local/bin/plesk-stdio.py"]`) or space-separated args
- `env.<VAR>` *(optional, section `env` or `UPPER_SNAKE_CASE` fields)*: merged into `stdio.env` with `clear_env: true`

```bash
op item create --category="API Credential" --title="MCP: My Stdio" --vault="Agent Gateway" \
  "cmd[text]=/usr/local/bin/my-mcp" \
  "env.MY_API_KEY[password]=<SECRET>"
```
