---
name: tailscale-ssh-mini
description: "Enable or re-test Tailscale SSH on Zach's Mac mini. Use when turning on tailscale set --ssh, proving a keyless login, or deciding whether the NAS can use the same path."
---

# Tailscale SSH on the mini

## Facts (verified 2026-11-08)

- Mini is `zacharys-mac-mini.tail158749.ts.net` (`100.115.34.115`). LAN SSH stays `192.168.4.102`, user `zachbornheimer`.
- `RunSSH` is already true. Do not run `tailscale set --ssh` again unless a check shows it off.
- The daemon is `/usr/local/bin/tailscaled` (`system/com.tailscale.tailscaled`). The CLI is `/opt/homebrew/bin/tailscale` (1.98.5). `/usr/local/bin/tailscale` does not exist. `sudo -n` works.
- Tailnet login `zachbornheimer@github` maps to local user `zachbornheimer`.
- A keyless non-interactive login already succeeded and did not stop for a browser check:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=20 \
  -o PreferredAuthentications=none -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/dev/null \
  zachbornheimer@zacharys-mac-mini.tail158749.ts.net 'hostname; whoami'
```

## Enable (only if RunSSH is false)

1. Check from the LAN alias, never from the Tailscale IP. `tailscale set --ssh` hangs any SSH session already open to the Tailscale address.

```bash
ssh -o BatchMode=yes mini '/opt/homebrew/bin/tailscale debug prefs'
ssh -o BatchMode=yes mini 'sudo -n /opt/homebrew/bin/tailscale set --ssh --accept-risk=lose-ssh'
```

2. Prove `RunSSH true`, then the keyless command above. Do not change `Host mini` until that print shows `zachbornheimer` and a hostname.

## Do not

- Point `Host mini` at MagicDNS before the keyless test passes. Keep `192.168.4.102` as the break-glass path.
- Expect Tailscale SSH on the Synology NAS. Tailscale's Synology docs say it does not run there. Join the NAS to the tailnet and keep DSM sshd plus the `ravn` key.
- `mise dot pull` the laptop's tracked history onto the mini. That history is full of MacBook paths, and LaunchDaemons run as that account.
