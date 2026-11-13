---
name: zysys-server-access
description: "Reaching and managing Zach's two Zysys servers (srv1.web.zysyshosting.com / zysys-srv1 and db1.data.zysyshosting.com / zysys-db1). SSH is Tailscale-only (sshd on 127.0.0.1, no keys, no passwords); EIP break-glass is AWS SSM. Also covers the zysys/ansible-infra and zysys/zysys-hosting-terraform repos."
---

## Servers (AWS `zab` profile, account `443021256344`, `us-east-1`)

| Role | Public DNS / EIP | Private IP | Instance ID / Type | OS / Arch | Tailscale |
| --- | --- | --- | --- | --- | --- |
| Web + Plesk (`srv1`) | `srv1.web.zysyshosting.com` (`54.198.191.19`) | `10.0.0.174` | `i-06e7c0292483e95d6` (`m6a.large`) | AlmaLinux 9.8 `x86_64` | `zysys-srv1.tail158749.ts.net` (`100.92.190.20`), `tag:server` |
| Database (`db1`) | `db1.data.zysyshosting.com` (`34.199.92.113`) | `10.0.0.36` | `i-073f501d9a5ed0453` (`t4g.medium`) | AlmaLinux 9.8 `aarch64` | `zysys-db1.tail158749.ts.net` (`100.99.134.41`), `tag:server` |

Both have passwordless `sudo` for `ec2-user`.

## SSH access (Tailscale only)

- **How:** `ssh srv1` / `ssh db1` (aliases in `~/.ssh/config`, Tailscale SSH, `PreferredAuthentications none`, no keys).
- **Hardened state:** sshd listens on `127.0.0.1` only (drop-in `/etc/ssh/sshd_config.d/00-zysys-tailscale-only.conf`): no password, no pubkey, no root login. `authorized_keys` were purged. Public port 22 refuses connections. Tailscale SSH does not need sshd on the network.
- **Human re-auth:** the tailnet ACL has a `check` rule for human members, so a laptop login needs a browser approval (cached ~12h per src/dst). The check URL dies about 2 minutes after the `ssh` command starts, so click it right after starting `ssh`. Server-to-server (`tag:server` to `tag:server`) and `tag:ci` are `accept` rules with no prompt.
- **Server to server:** `ssh -o PreferredAuthentications=none -o StrictHostKeyChecking=accept-new ec2-user@zysys-db1.tail158749.ts.net` works from srv1 (and the reverse).
- **Break-glass (replaces the EIP + `zysys-hosting-key` path):** AWS SSM Session Manager. Both instances are SSM Online (db1 got instance profile `zysys-srv1-ssm-profile`, association `iip-assoc-0d92d25942ddb8d84`). `aws --profile zab --region us-east-1 ssm start-session --target <instance-id>`; non-interactive: `ssm send-command` with `AWS-RunShellScript`.
- **Undo the lockdown (over SSM, on the host):** `rm -f /etc/ssh/sshd_config.d/00-zysys-tailscale-only.conf && systemctl restart sshd` (prior config saved at `/var/lib/zysys-ssh-rollback/sshd_config.prior`).
- **Public EIP SSH is gone:** `ssh zysys-srv1-eip` / `zysys-db1-eip` and `-i ~/.ssh/1p/zysys-hosting-key.pub` no longer work.

## WP Engine (ISJAC)

`ssh isjac` goes `ProxyJump zysys-srv1` to `isjac@isjac.ssh.wpengine.net`. The jump host only relays TCP, so WP Engine authenticates the laptop's `~/.ssh/1p/id-rsa.pub` (1Password agent). No key on srv1 is involved. The `ec2-user` ed25519 key on srv1 is NOT registered at WP Engine and is unused by this path.

## Configuration management

- **Ansible:** `zysys/ansible-infra` at `~/Developer/Zysys/ansible-infra` (not `dev-env` or `homelab`). Inventory `inventory/hosts.yml`, playbook `playbooks/site.yml`, roles `ssh`, `tailscale`, `fail2ban`, `hosts`.
- **Tailscale-only SSH change:** PR `zysys/ansible-infra#44` (branch `feat/tailscale-only-ssh`): lockdown with a 300 s timed rollback, tailnet inventory, `deploy.yml` joining the tailnet as `tag:ci`. Lockdown is already LIVE on both hosts (applied from the branch, verified 2026-11-13); the PR stays draft until the CI OAuth secrets (`TS_OAUTH_CLIENT_ID`, `TS_OAUTH_SECRET`, Tailscale OAuth client with `auth_keys` write for `tag:ci`) exist. `ANSIBLE_VAULT_PASSWORD` is only a GitHub secret (not in 1Password), so local full `site.yml` runs need `.vault_pass` from the operator; `--tags ssh,tailscale` needs no vault. `SSH_PRIVATE_KEY` can be deleted after merge. `ssh srv1 'ssh isjac'` fails (srv1's ec2-user key is not registered at WP Engine); the laptop `ssh isjac` ProxyJump path works.
- **Terraform:** `zysys/zysys-hosting-terraform` at `~/Developer/Zysys/zysys-hosting-terraform`; PR `zysys/zysys-hosting-terraform#2` (`0bdc519`) is merged and live `:22` ingress rules (`sgr-099a03606b56b7c38` on `sg-02761bac2b11499cd` and `sgr-099409432828bc044` on `sg-0af4900df1b2800b0`) are revoked in AWS (`allowed_plesk_ips` controls `:8443` only; `iam_instance_profile = zysys-srv1-ssm-profile` is codified on both EC2 instances).
- **ansible-infra hooks:** `hk` requires a conventional commit subject of at most 60 characters; `dprint fmt` before `HK_JOBS=1 git commit` avoids parallel markdown contention; pre-push runs actionlint, zizmor (pinned actions, `permissions:`, `persist-credentials: false`) and yamllint --strict.
- **Tooling gotchas:** use `/opt/homebrew/bin/gh` (the `~/.local/bin/gh` wrapper hangs); the `op` CLI needs the desktop-app integration on and `OP_SERVICE_ACCOUNT_TOKEN` unset.
