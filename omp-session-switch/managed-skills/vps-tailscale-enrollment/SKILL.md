---
name: vps-tailscale-enrollment
description: "Use when vps:up waits on status off, or when asked whether the dev-env flake joins the fleet box to Tailscale and applies tags."
---

# Fleet Tailscale enrollment

The flake does not join the Hetzner fleet box. Do not look there for the auth key or the tags.

## Where enrollment lives

- `nix/os.nix` enables `services.tailscale` (`--accept-routes --ssh`) and does not auto-enroll.
- `nix/container.nix` enrolls a container from `/run/secrets/tailscale-auth-key`. That is the persistent runtime key, not the fleet key. If `BackendState` is already `Running`, it runs `tailscale set` and skips `up`.
- `nix/home.nix` only installs the binary.
- The fleet box is cloud-init plus `tools/vps/vps-up.sh`. cloud-init installs Tailscale. `vps_resolve_tskey` reads 1Password item `Tailscale Fleet (AI) Ephemeral API Key`, vault `Zysys`, field `credential`, and `provision_tailnet` sends it on SSH stdin.

## status=off is not a boot wait

The idle reaper's `systemctl poweroff` leaves Hetzner `status=off` with no poweroff action. Reuse does not boot the box. `wait_for_server` must `POST /servers/<id>/actions/poweron` once, then poll. A log of `waiting for boot (status: off)` means that call never happened. The join cannot run until the box is `running`.

## Tags are a property of the minted key

The 1Password item has no tag field. `Self.Tags` null after a successful join means the key was not minted with a tag. Mint a tagged auth key in the Tailscale admin console. The flake cannot stamp tags, and `tailscale up` without `--force-reauth` leaves an already-Running node on its old identity.
