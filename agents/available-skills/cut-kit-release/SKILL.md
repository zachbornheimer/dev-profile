---
name: cut-kit-release
description: Cut and consume an isa-ui-kit release — land work on main, version with changesets, publish to GitHub Packages (or the billing-bypass path), then bump the consumer. Use whenever kit changes must reach eapp-system/bpp for real, or when a kit fix "works locally" but not in prod. Covers the local-alias trap that makes local dev silently disagree with deployed builds.
---

# Cut an isa-ui-kit Release

The kit is consumed two completely different ways, and confusing them is the
single biggest source of "it worked locally" in this program. Read
§The two lineages before anything else.

Repo: `~/Developer/Software-Automation-Holdings/isa-ui-kit`
Packages: `packages/{core,react,vue,tokens}` — npm workspaces + changesets.
(npm is this repo's native tooling; the global pnpm-not-npm rule doesn't
apply here. Never regenerate the lockfile with a different manager.)

## The two lineages (read first)

1. **Local dev** — `eapp-system/vite.config.js` aliases the kit to a _sibling
   source checkout_ whenever one exists. Candidate order: `$ISA_UI_KIT`, then
   `../../.worktrees/isa-ui-kit-code-editor`, `../isa-ui-kit`,
   `../../isa-ui-kit`. First directory with `packages/vue/src/index.ts` wins.
   `ISA_UI_LOCAL=0` forces the published package instead.
2. **Deployed/prod** — installs the version pinned in `eapp-system/package.json`
   from `npm.pkg.github.com`. No alias, no source.

Consequences that bite:

- A kit fix is visible locally the moment it's on disk, and invisible in prod
  until it is **published AND the consumer's pin is bumped**.
- Whichever checkout the alias picks is what you are actually testing. It may
  be a stale branch. Print it: the build logs `[vite] isa-ui-kit: local source → <path>`.
  Check that line before trusting any local kit verification.
- To test a _specific_ kit state, pin it: `ISA_UI_KIT=<path> EAPP_FORCE_BUILD=1 …`.
- Any "proven live" claim must say which lineage it was proven on. See
  [[eapp-dual-css-lineage-gap]] for the same class in CSS.

## Land the work on main first

Release from `main`, never from a feature branch: `release/<slug>` is the
feature rebased onto current main, not a fork of main.

- A long-lived kit branch is usually **behind** main; `git diff main` from it
  mixes real changes with reversions of main's newer work and is unreadable.
  Judge scope by `git diff $(git merge-base main <branch>) <branch>` instead.
- Land in a dedicated worktree so an in-flight harness pointed at main isn't
  disturbed mid-run:
  1. `git fetch origin main`
  2. `wt switch --create release/<slug> --base <feature> --no-cd --format=json --yes`
  3. Use the JSON `path`.
  4. `wt -C <path> step rebase origin/main`
     Symlink `node_modules` from the main clone rather than reinstalling.
- `DateInput` (react + vue) is the recurring conflict site — both sides tend to
  touch it. Resolve during that rebase by keeping main's newer behavior AND the
  branch's styling/caption changes; run that component's tests specifically.
- Uncommitted working-tree residue on a kit branch is often **superseded** by
  work already on main. Never blind-commit it. Diff the residue against main
  file by file; back it up (`git diff HEAD > <scratchpad>/kit-uncommitted.patch`)
  before discarding anything.

## Version + build

```bash
npx changeset            # describe the change; pick bumps per package
npx changeset version    # writes versions + CHANGELOGs (do NOT hand-edit versions)
npm run build            # every publishable package must emit dist/ BEFORE packing
npm test                 # plus scripts/check-barrel-parity.mjs if touched exports
```

`npm pack` does **not** run the build. Packing without building ships an empty
package — inspect the tarball, never assume:
`tar tzf <pkg>.tgz | head` must show `dist/`, and grep the bundle for the
feature that motivated the release.

## Publish

Normal path: `NODE_AUTH_TOKEN="$(gh auth token)" npx changeset publish`.

Discriminate failures — they are not the same problem:

- **E401** — the shell lost `NODE_AUTH_TOKEN`. Not billing. Doppler `bpp/bpp`
  holds only `GITHUB_PACKAGES_READ_TOKEN` (read-only); use `gh auth token` for
  writes.
- **E403 "Account has reached its billing limit"** — org billing block. It
  disables Actions _and_ Packages together, so a free probe is
  `gh run list --limit 5` in the kit repo: `startup_failure` on every recent run
  means a publish will E403 too. Probe before planning a release around it.

**Billing-bypass path** (when E403): tags + a GitHub Release with `npm pack`
tarballs attached — Releases don't count against the Packages quota. Use the
`bump` CLI (`bump [--patch|--minor|--major] [--dry-run] <org/repo[#pr]>`), or
the manual sequence in the `cut-release` skill. Always `--dry-run` first.

Critical limitation, and the reason this is a stopgap: **a GitHub Release does
not make the package installable.** `npm install` still resolves from the
registry, so a consumer's `package.json` pin cannot reach a bypass-only
release. Deploys keep getting the last _published_ version. If prod must have
the change while billing is blocked, that is a distribution decision to put to
the owner (restore billing / alternate registry / vendor the built kit) — do
not quietly leave prod on an old version and call the release done.

## Consume it (the step that's easy to forget)

A release nobody depends on changes nothing.

1. Bump the pins in `eapp-system/package.json` for every kit package that moved
   (`isa-ui-vue`, `isa-ui-react`, `isa-ui-tokens`, `isa-ui-core`) — they version
   independently and drift apart.
2. Install with the repo's own manager; commit the lockfile change.
3. Verify against the **served artifact**, not local dev — local dev may still
   be aliasing source and would pass either way. Build with `ISA_UI_LOCAL=0` to
   force the published package, or check the deployed build.
4. Consumers import kit CSS directly ([[project_kit_css_direct_import]]) — a
   styles-only change still requires the version bump to reach anyone.

## Definition of done

- Work is on `main`; tags exist on origin for each bumped package.
- The registry shows the new version (`npm view <pkg> versions --registry=https://npm.pkg.github.com`)
  — or, on the bypass path, the Release lists every expected asset AND a
  follow-up task records the exact catch-up publish command.
- A tarball was opened and shown to contain the built feature.
- The consumer's pin is bumped and the change is observed on the served
  artifact, stating which lineage proved it.

## Gotchas

- Tag names contain `@` and `/`; quote them, and expect `%40`/`%2f` in URLs.
- Never release from a dirty tree. An untracked auth `.npmrc` is the one
  acceptable exception and must never be committed.
- Kit packages version independently — don't assume one number covers all four.
- `.trunk/` noise shows as untracked in kit worktrees; it is not your change.
- Don't run more than one full trunk gate concurrently ([[code-standards]] Trunk rules).
