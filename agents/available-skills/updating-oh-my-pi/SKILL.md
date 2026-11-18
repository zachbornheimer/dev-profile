---
name: updating-oh-my-pi
description: Use for personal omp behavior versus source-change routing, installing or rolling back omp through mise, upstream PRs to can1357/oh-my-pi, and proving the installed binary. All fork operations belong to shipping-a-fork-binary-via-mise; omp-fork-conventions owns build, test and remote facts.
user-invokable: true
---

# Oh-my-pi: route the change and prove the installed binary

**`shipping-a-fork-binary-via-mise` is the single operational owner** for adopting forks, creating and landing topics, upstream sync, resolving carry conflicts, dropping absorbed carries, installing and verifying releases. **`omp-fork-conventions` owns omp-specific build recipes, tests and remote expectations.** Do not maintain a parallel assembly or registration procedure here.

## Extension, tool or repository change?

- **Personal presentation or session behavior** (slash commands, hiding transcript blocks, toggles, session hooks) belongs in an auto-discovered extension under `~/.omp/agent/extensions/<name>/index.ts` or `<name>.ts`, without a settings registration. Restart/reload as required and prove the behavior in a fresh session. Do not patch the repository when its extension API can do the job.
- **A tool agents call** belongs to `creating-new-tools`. Keep one implementation and use the current tool adapters; a personal command can call it without duplicating logic in an extension.
- **Incorrect core behavior or a missing extension seam** is a repository change. Use the owner's `fork change` and `fork land` procedure. Keep the topic upstream-PR-ready and do not edit the mirror or generated assembly. A carried-topic push alone needs a `fork.yml` dispatch on `fork`.

## Install the promoted release

Normal install follows the owner's `install oh-my-pi` operation. The mise tool is `github:zachbornheimer/oh-my-pi`, version `latest`, with `version_prefix = "build-"`; preserve all existing keys, including platform restrictions and asset matching. Never replace the release install with a source-checkout binary or a local source symlink.

```bash
bun ~/.omp/agent/tools/fork/cli.ts install oh-my-pi
mise current github:zachbornheimer/oh-my-pi
mise which omp
omp --version
```

The fork build identity must name the promoted release, not merely the upstream package version. A long-lived shell can pin an older mise installation in PATH; compare the resolved executable with `mise where github:zachbornheimer/oh-my-pi` or launch through the current mise environment. An already-running process may still use an older binary: `omp-version-hot-reload` owns that distinction.

## Prove the actual installed behavior

Prove the reported bug or requested feature with the installed binary. Version output establishes identity, not behavior. Use a deterministic smoke that exercises the changed path, with isolated context/session state where relevant; `omp-fork-e2e-test-environment` owns those details. Read the completed test result, not an empty in-progress log. Record the release/run, executable path, identity and observable outcome separately.

For a string intended to be embedded in the executable, inspecting `$(mise which omp)` can establish its presence, but does not replace a runtime test. Test the final committed assembly before claiming the shipped fix works.

## Submit upstream

Upstream is `can1357/oh-my-pi`; fork is `zachbornheimer/oh-my-pi`. Inspect remotes rather than swapping their meanings. Use an independent source topic from the owner's mirror/merge-base procedure, never fork configuration or another topic. Read the checked-out `CONTRIBUTING.md` and PR template; preserve the contributor's explanation and follow repository checks.

The owner supports `fork land ... --upstream-pr`. For an existing pushed topic, the equivalent upstream PR is:

```bash
gh pr create --repo can1357/oh-my-pi --head zachbornheimer:fix/my-change --base main
```

After upstream absorbs the behavior, follow the owner's `drop` procedure rather than retaining duplicate fixes.

## Roll back one machine

Choose a known-good **promoted** release, not a prerelease:

```bash
gh release list --repo zachbornheimer/oh-my-pi
```

In machine-local `~/.config/mise/config.local.toml`, override only this tool's version while preserving its existing options. This file is not synced:

```toml
# ROLLBACK <date>: <reason>; remove after a fixed release is promoted.
[tools]
"github:zachbornheimer/oh-my-pi" = { version = "build-<known-good-tag>", version_prefix = "build-", matching = "omp-", minimum_release_age = "0" }
```

Copy any platform restriction or other keys from the current entry; do not silently discard them. Then install and verify both identity and behavior:

```bash
mise install github:zachbornheimer/oh-my-pi
mise exec -- omp --version
```

When a fixed release is promoted, remove only the rollback override and return to the owner's normal latest-release install. Do not replace or delete unrelated local configuration.
