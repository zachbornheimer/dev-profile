---
name: cut-release
description: Cut a release for an SAH or personal repo — normal path via CI/changesets, or the billing-bypass path (git tags + GitHub Release with npm-pack tarball assets) when GitHub Actions/Packages are blocked by the org billing limit. Wraps the `bump` Go CLI.
---

# Cut Release

Cut a complete, verifiable release even when GitHub's org billing limit blocks
both Actions (startup_failure) and GitHub Packages publishes (E403 on PUT).
GitHub **Releases** (tags + attached assets) do not count against the Packages
quota — that is the bypass.

## Decide the path

1. **Normal path** — Actions working: merge to main, let the repo's Release
   workflow run (`changeset publish` → npm.pkg.github.com). Verify the new
   version is on the registry before calling it done.
2. **Billing-bypass path** — Actions or Packages returning
   `billing limit` errors: cut the release as tags + a GitHub Release with
   npm-pack tarballs attached, and log a follow-up task to run the registry
   publish when billing is restored. Consumers that vite-alias or vendored-copy
   the package keep working; registry consumers wait for the catch-up publish.

Probe cheaply before assuming: a publish attempt that fails **E401** is an auth
problem (missing `NODE_AUTH_TOKEN`), not billing; only **E403 "Account has
reached its billing limit"** means blocked. `gh auth token` works as
`NODE_AUTH_TOKEN` for npm.pkg.github.com.

## The `bump` tool (preferred)

```text
bump [--patch|--minor|--major] [--dry-run] <org/repo[#pr] | local-path>
```

Source: `~/Developer/Personal/bump` → installed at `~/.local/bin/bump`.

- Resolves a local checkout under `~/Developer/{Software-Automation-Holdings,Personal}/<repo>`
  or shallow-clones via `gh`.
- Refuses dirty trees / non-default branches; `#pr` must reference a MERGED PR
  (it lands in the release notes).
- **Changesets repos** (`.changeset/` exists): versions come from
  `changeset version` — the bump flag is rejected; it runs `changeset tag` and
  packs every non-private workspace package.
- **Plain repos**: bumps the latest `vX.Y.Z` tag per the flag, updates
  package.json if Node, commits, tags.
- Builds, `npm pack`s publishable packages, pushes tags, creates the GitHub
  Release with tarballs attached. Release notes state the registry publish is
  pending and give the exact catch-up command.
- Always run `--dry-run` first and read the plan before the real run.

## Manual procedure (what `bump` automates)

Proven 2026-08-17 cutting isa-ui-kit 1.4.0:

```bash
# From a clean checkout/worktree of main at the version-bumped commit,
# with the CI gate already green there.
npm run build          # or the repo's build; make sure dist/build outputs exist
npx changeset tag      # changesets repos — creates only the missing tags
for p in packages/*; do (cd "$p" && npm pack --pack-destination /tmp/rel-tarballs); done
tar tzf /tmp/rel-tarballs/<pkg>.tgz | head   # sanity: dist present, key exports in bundle
git push -u origin refs/tags/<tag1> refs/tags/<tag2>
gh release create '<primary-tag>' /tmp/rel-tarballs/*.tgz \
  --title '<repo> <version>' \
  --notes '... registry publish PENDING (org Packages billing E403); catch-up: NODE_AUTH_TOKEN="$(gh auth token)" npx changeset publish'
gh release view '<primary-tag>' --json assets -q '.assets[].name'   # verify upload
```

## Definition of done

- Tags exist on origin and the Release shows every expected asset
  (`gh release view --json assets`).
- A tarball was inspected, not assumed: it contains the built artifact and the
  feature that motivated the release.
- A follow-up task exists for the registry catch-up publish, with the exact
  command and commit SHA.
- The catch-up publish is safe later: `changeset publish` decides from the
  registry (not tags), and skips tags that already exist.

## Gotchas

- `changeset publish` failing E401 means the shell lost `NODE_AUTH_TOKEN` — it
  is not the billing block returning.
- Doppler `bpp/bpp` only holds `GITHUB_PACKAGES_READ_TOKEN` (read-only); use
  `gh auth token` for writes.
- `npm pack` does not run the build — build first or ship an empty package.
- Tag names in changesets repos contain `@` and `/`; quote them in shell and
  they URL-encode in release URLs (`%40`, `%2f` — normal, not a bug).
- Never run the release from a dirty tree; an untracked `.npmrc` for auth is
  the one acceptable exception (it must never be committed).
