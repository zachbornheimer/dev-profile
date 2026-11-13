---
name: colima-missing-port-forward
description: "Diagnose and repair a Docker service reachable inside the Colima VM but refusing connections from macOS — the \"port 80 forwards, port 443 does not\" signature after a colima restart, where Lima's ssh master only holds forwards registered at start and macOS blocks unprivileged binds below 1024."
---

# Colima: a published port that never reaches macOS

## Signature

A container publishes a port and listens inside the VM, but the host refuses connections:

- `docker ps` shows `0.0.0.0:443->443/tcp`
- host probe `nc -z 127.0.0.1 443` → closed, while `nc -z 127.0.0.1 80` → open
- in-VM probe → open:

```sh
docker run --rm --net=host busybox:stable sh -c 'nc -z 127.0.0.1 443 && echo VM_OPEN'
docker exec <container> sh -c 'ss -ltn || netstat -ltn'
```

Restarting the container (`docker restart caddy`) does **not** fix it. A full `colima restart`
may not either.

## Why

Colima on macOS forwards guest ports through a Lima-managed `ssh` process. That process holds
forwards decided when it started; ports published later are not always added. Confirmed on
2026-11-07: `ssh` held `*:80`, `*:8443`, `*:9443` but no `*:443`, while caddy listened on `:::443`
inside the VM.

A plain `ssh -L 443:...` cannot repair it because **macOS refuses unprivileged binds below 1024**:

```
bind [::1]:443: Permission denied
```

The Lima-managed ssh can bind 80 because it is a privileged/special process.

## Confirm the split before changing anything

```sh
# host: who, if anyone, holds 443
sudo lsof -nP -iTCP:443 -sTCP:LISTEN     # eg tailscale on its own 100.x/tailnet IPs only
sudo netstat -an -p tcp | grep LISTEN | grep '\.443 '
# guest: is the app actually listening
docker exec <container> sh -c 'ss -ltn | grep 443'
```

Note the difference between a wildcard bind and a specific-IP bind: Tailscale listening on
`100.x.x.x:443` and `[fd7a:...]:443` does **not** block a wildcard listener, and it **does** win
over one for its own address. That matters for any Tailscale-served hostname.

## Repair (transient but correct)

Linux host M, guest reachable through colima's ssh config (`~/.colima/_lima/colima/ssh.config`,
host alias `lima-colima`):

```sh
sudo ssh -f -N -g \
  -o ControlMaster=no -o ControlPath=none -o ExitOnForwardFailure=yes \
  -F /Users/<user>/.colima/_lima/colima/ssh.config \
  -L 0.0.0.0:443:127.0.0.1:443 lima-colima

sudo netstat -an -p tcp | grep LISTEN | grep '443 '   # expect *.443
```

- `sudo` is required (privileged port). `-g` is required for LAN access; without it the bind is
  loopback-only and only the host itself can connect.
- `ControlMaster=no -o ControlPath=none` avoids asking the existing mux master, which reports
  `bind [0.0.0.0]:443: Address already in use` for a port that `netstat` shows nobody holds — a
  misleading error produced by the master, not a real conflict.
- Verify from a *different* machine, not the host: host-local checks can pass while the LAN path
  is still broken.

## This is not durable

The forward dies on reboot or `colima restart`. Treat it as a stopgap: report it as such and decide
the permanent shape (fix Lima's forward registration, move ingress above 1024, or add an explicit
supervised forward). Do not present it as a converged state.

## Related trap

A service declared but disabled (e.g. `deployed:false` for a memory budget) can still make a
converge CLI fail on its probe, which then blocks unrelated repairs. Read the whole output to see
whether the failing item is live before chasing it.
