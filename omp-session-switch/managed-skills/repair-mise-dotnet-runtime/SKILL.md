---
name: repair-mise-dotnet-runtime
description: "Fix local dotnet test/build failing with \"missing framework Microsoft.NETCore.App 8.0.x\" while CI is green — the mise dotnet SDK pin needs a matching runtime and targeting pack installed into ~/.local/share/mise/dotnet-root."
---

# Repair the mise dotnet-root when the SDK pin outruns the runtime

## When

A repo pins `dotnet = "8.0"` (or similar) in `mise.toml`. `mise x dotnet -- dotnet test` fails locally with "You must install or update .NET … framework 'Microsoft.NETCore.App', version '8.0.x' not found" while CI on the same commit is green. Cause: mise installs each new **SDK** into `~/.local/share/mise/dotnet-root/sdk/` but does not refresh the **runtime** or **targeting pack**; `shared/Microsoft.NETCore.App/` keeps whatever the first install carried. The SDK's muxer demands a runtime with its own minor (SDK 8.0.427 needs runtime 8.0.33).

## Diagnosis

- `mise ls dotnet` — which version the pin resolves to.
- `ls ~/.local/share/mise/dotnet-root/shared/Microsoft.NETCore.App/` — which runtimes exist. Mismatch with the SDK minor = this problem.
- Run once to capture the exact missing version from the error, then run again after each install step; the error moves through three stages (runtime missing → targeting pack `FrameworkList.xml` missing → analyzer assemblies missing). Install all three in one pass.

## Repair (example: SDK 8.0.427 needing 8.0.33, osx-arm64)

```bash
V=8.0.33; ROOT=~/.local/share/mise/dotnet-root

# 1. Runtime — official tarball, osx-arm64
curl -fsSL -o /tmp/dotnet-rt.tar.gz \
  "https://builds.dotnet.microsoft.com/dotnet/Runtime/$V/dotnet-runtime-$V-osx-arm64.tar.gz"
tar -xzf /tmp/dotnet-rt.tar.gz -C "$ROOT"

# 2. Targeting pack — from the nupkg (the runtime tarball 404s for ref packs)
curl -s -o /tmp/ref.nupkg.zip \
  "https://api.nuget.org/v3-flatcontainer/microsoft.netcore.app.ref/$V/microsoft.netcore.app.ref.$V.nupkg"
mkdir -p /tmp/ref && unzip -q -o /tmp/ref.nupkg.zip -d /tmp/ref
P="$ROOT/packs/Microsoft.NETCore.App.Ref/$V"; mkdir -p "$P"
cp -R /tmp/ref/data       "$P/"   # FrameworkList.xml etc.
cp -R /tmp/ref/ref/net8.0 "$P/ref/" 2>/dev/null || mkdir -p "$P/ref" && cp -R /tmp/ref/ref/net8.0 "$P/ref/"
cp -R /tmp/ref/analyzers  "$P/"
```

Substitute `$V` from the error message, and the runtime URL OS/arch for the host. For other major versions the nupkg id is `microsoft.netcore.app.ref` (8.x) / check the error's pack path under `packs/`.

## Verify

`mise x dotnet -- dotnet test <the repo's .sln>` exits 0. If it still fails on metadata files, read the path in the CS0006 error — it names exactly which pack directory is still empty (repeat step 2 for that subtree).

## Notes

- This is machine-local repair, not a repo change; nothing to commit.
- A pre-push contract that fails on `dotnet test` while CI is green on the same commit is this problem, not the branch.
- If a push that timed out left an orphaned `sah-contract-push` → `mise run test` → `rspec` chain alive, kill those pids before re-pushing or the next push fails with `PG::ObjectInUse` on the test database (found via `ps -eo pid,ppid,command | rg rspec`, then `pg_stat_activity` for the DB session).
