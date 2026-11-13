---
name: macos-tailscale-cli-ssh
description: Switch this Mac from the sandboxed Tailscale GUI to Homebrew tailscaled so tailscale set --ssh can run.
---

# macOS Tailscale CLI SSH

The Tailscale GUI (Standalone and App Store) cannot be a Tailscale SSH server. `tailscale set --ssh` returns: "The Tailscale SSH server does not run in sandboxed Tailscale GUI builds." Only the open-source `tailscaled` variant can.

## Install and start

```sh
brew install --formula tailscale
# admin password required; brew services installs LaunchDaemon sh.brew.tailscale
sudo brew services start tailscale
```

Daemon socket: `/var/run/tailscaled.socket`. Binary: `/opt/homebrew/opt/tailscale/bin/tailscaled`.

Then, as root once:

```sh
/opt/homebrew/opt/tailscale/bin/tailscale --socket=/var/run/tailscaled.socket set --operator="$USER"
```

## CLI must not talk to the GUI

On macOS the `tailscale` CLI discovers the GUI local API via `/Library/Tailscale/ipnport` and ignores `/var/run/tailscaled.socket`. A version warning (`client version != tailscaled server version`) means you are still on the GUI backend. `~/.local/bin/tailscale` is a wrapper that forces `--socket=/var/run/tailscaled.socket` unless the caller already passed `--socket`.

Quit `/Applications/Tailscale.app` and `scutil --nc stop "Tailscale"` before `tailscale up`. Opening the menu bar app reclaims the tunnel and SSH stops. The network extension cannot be uninstalled while SIP is on.

## Enable SSH

```sh
tailscale up --ssh --operator="$USER"
tailscale set --ssh
```

`RunSSH` true in `tailscale debug prefs` and TCP 22 open on the node's 100.x address means the server is up. Login is still governed by the tailnet SSH policy; a local `ssh` that fails on keys does not mean the server is down.

Do not run the GUI and `tailscaled` at once. Two nodes appear (often `hostname` and `hostname-1`) until the GUI is down.
