---
name: forking-projects
description: Use before forking a project or repairing a fork: decide plugin versus upstream PR versus fork, keep the upstream mirror pristine, separate independent topics from fork configuration, and defer operational commands to shipping-a-fork-binary-via-mise.
---

# Forking projects: keep the delta small

A fork costs something whenever upstream moves. This skill explains the design. **`shipping-a-fork-binary-via-mise` is the single operational how-to**, including the ordered steps and the four enforcement layers. Do not restate those steps here. Oh-my-pi follows that same process; `omp-fork-conventions` contains only its build/test/remote specifics. Machines install a fork binary only with `mise install` or `mise up`.

## 1. Avoid a fork when possible

Try these in order:

1. **Config or plugin point.** Tools, hooks, skills and settings discoverable from a user directory belong in your own repo, not on source carry branches.
2. **Upstream PR.** Generally useful behavior belongs upstream; a fork bridges the wait for acceptance.
3. **Fork.** Carry only behavior upstream has not taken or will not take.

Before moving a branch into a plugin directory, inspect its complete diff: a branch that also changes source is not merely a plugin. Generated tools must not create a branch registration for every tool.

## 2. Use one branch layout

| Branch                               | Role                                                                     |
| ------------------------------------ | ------------------------------------------------------------------------ |
| Upstream-named `main` or `master`    | Exact, fast-forward-only upstream mirror; no fork commits                |
| Default `fork`                       | Only `.github/workflows/fork.yml`, `.fork/branches`, `.fork/rr-cache`    |
| `feat/<slug>` or `fix/<slug>` topics | Independent, upstream-PR-ready source customizations cut from the mirror |
| CI-owned `assembled`                 | Disposable merge result, never a source branch or place for direct edits |

The pristine mirror and absence of blocking protection preserve GitHub's **Sync fork** button. Keep the workflow on default `fork`, where GitHub can discover scheduled/manual triggers; do not put workflow configuration on the mirror to avoid a second branch.

Use the fork tool to create topics and register them. It chooses the mirror base and an owned worktree. When diagnosing an existing topic, the relevant upstream base is `git merge-base upstream/main origin/main` (substitute the actual upstream branch); fork configuration and other topics must not leak into upstream PRs. Never edit a main checkout or force-push a shared branch.

## 3. Sort and isolate customizations

| Kind               | Home                                                                      |
| ------------------ | ------------------------------------------------------------------------- |
| Outside the source | Your own plugin, tool, skill, hook or config directory                    |
| Upstream-bound     | One independent topic with one concern and tests                          |
| Personal           | A cohesive source topic, still independent and free of fork configuration |

Every carry needs an explainable purpose. Keep topics independent rather than merging one topic into another to hide assembly conflicts. If there is a real dependency, make its ordering explicit and submit the base upstream first. Names describe the change, not a session identifier.

The only carry list is `.fork/branches`: one branch per line in merge order. See [the format](references/branch-manifest.md). Do not add a second manifest, resolver convention or hidden registration source.

## 4. Sync and resolve through the shared pipeline

The pinned shared workflow v2.0.0 fast-forwards the mirror, merges ordered topics, checks assembled source, builds a prerelease, installs it with mise and runs smoke, then promotes. A merge without textual conflicts is not proof of compatible APIs or runtime behavior.

The daily 03:30 launchd job `dev.mise.fork-daily-sync` fast-forwards every non-archived fork mirror and dispatches managed builds. Exit 1 means a mirror could not fast-forward: inspect the per-repo log rather than assuming no fork updated. Manual sync and build are distinct operations. A push to an already-carried topic does not itself trigger a build; dispatch `fork.yml` on `fork` through the owner procedure.

Resolve actual assembly conflicts once through the tool's `resolve start` / `resolve record` operations. They publish Git rerere data in `.fork/rr-cache`, replayed by CI. Do not merge topics into each other, invent exact-stage patch metadata, or weaken checks to clear a build. Semantic failures require changing the responsible source topic.

Remove a carry once upstream supplies its behavior, including equivalent squash/reworked fixes. The owner procedure includes ancestry/patch-equivalence commands and `drop`. Mise's `fix/install-os-excluded-tool` was dropped after upstream shipped the same fix.

## 5. Verify what actually shipped

Use the owner skill's exact commands. Measure these separately:

- Mirror ancestry and whether any fork-only commits block fast-forward or Sync fork.
- The actual run, assembled commit, selected topic SHAs and promoted release.
- Completed check results, not an empty in-progress log.
- Installed binary build identity and meaningful customization smoke through mise.

A fresh committed replay is stronger evidence than working-tree tests. Before adopting an existing fork, prove all carries against upstream's **latest** tip: adoption does not freeze the old base. Keep foreign upstream workflows disabled; GitHub-managed `dynamic/` workflows cannot be disabled and are skipped. Remove only protections/rulesets confirmed to block the mirror, preserving unrelated protections.

Install fork releases through mise's GitHub backend at `latest` with `version_prefix = "build-"`, preserving existing keys such as `os`. No local symlink substitutes for a promoted, installed release. Do not treat a successful merge or version string as a complete shipping proof.
