---
name: zys-linear-ticket-access
description: "How linear-personal (ZYS) and linear-sah (SAH) authenticate on mcp-gateway via 1Password vault Agent Gateway (MCP: Linear Personal and MCP: Linear SAH)."
---

# Linear (`linear-personal` / ZYS & `linear-sah` / SAH) on `mcp-gateway`

Both `linear-personal` (ZYS) and `linear-sah` (SAH) run on `http://mcp-gateway.tail158749.ts.net:4600/mcp` and are configured in the 1Password **`Agent Gateway`** vault via **`MCP: Linear Personal`** and **`MCP: Linear SAH`** (`host=https://mcp.linear.app/mcp`, `credential=lin_api_...`):

- **Update ZYS token:** Edit `MCP: Linear Personal` (or `LINEAR_PERSONAL_TOKEN`) in the **`Agent Gateway`** vault with a Zysys workspace Personal API Key (`lin_api_...`); `mcp-gateway-sync.timer` hot-reloads `agentgateway` within 5 seconds.
- **Update SAH token:** Edit `MCP: Linear SAH` (or `LINEAR_SAH_TOKEN`) in the **`Agent Gateway`** vault with a SAH workspace Personal API Key (`lin_api_...`).
- **Headless 1Password access:** Use Keychain `org.zysys.op-service-account` (`security find-generic-password -a "$USER" -s org.zysys.op-service-account -w`) to read `"Service Account Auth Token: Agent Gateway RW"` from the `Zysys` vault when editing items in `Agent Gateway`.
