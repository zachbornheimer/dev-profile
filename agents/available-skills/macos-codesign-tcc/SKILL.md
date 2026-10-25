---
name: macos-codesign-tcc
description: Use when building or installing a locally-built macOS binary that runs as a daemon/LaunchAgent or touches TCC-protected folders (Desktop/Documents/Downloads/iCloud); when macOS permission prompts keep recurring with no durable "always allow"; on any "sign this binary" ask; or when setting up a new Go CLI/daemon repo's build task on this Mac.
---

# macOS code signing for durable TCC grants

## Why this exists

TCC (Transparency, Consent, and Control — the Desktop/Documents/Downloads/full-disk
prompts) remembers grants **by code signature**, not by path or bundle ID alone. An
unsigned or ad-hoc-signed binary gets a fresh identity on every rebuild, so the grant
never sticks — the user re-approves forever. A stable `--identifier` plus a real
Developer ID signature makes one grant persist across rebuilds.

## The recipe (proven in obsidian-backup, canonical source of truth)

Run this **after** `go build` — never after any post-build mutation (stripping,
patching the binary) since that invalidates the signature. `ldflags` at build time are
fine; edits to the compiled binary after signing are not.

```sh
DAEMON_IDENTIFIER=com.yourorg.yourproduct.daemon   # stable, per-product — never derived from version/sha/commit

if [ -n "${CODESIGN_IDENTITY:-}" ]; then
  IDENTITY="${CODESIGN_IDENTITY}"
else
  IDENTITY=$(security find-identity -v -p codesigning 2>/dev/null \
    | grep 'Developer ID Application' | head -1 | awk -F'"' '{print $2}')
fi

if [ -n "${IDENTITY}" ]; then
  codesign --sign "${IDENTITY}" \
    --identifier "${DAEMON_IDENTIFIER}" \
    --entitlements entitlements.plist \
    --options runtime \
    --timestamp \
    bin/yourbinary
else
  echo "No Developer ID identity found — shipping unsigned build."
fi
```

- **Best-effort, never blocking:** no identity found → build still succeeds
  unsigned, with a one-line note. Don't fail the build task over signing.
- Zach's Developer ID on this Mac: `Developer ID Application: Zachary Bornheimer
  (WD52VHTN44)` — present in the login keychain, works non-interactively via
  `security find-identity -v -p codesigning`.

## Entitlements (verbatim, proven-working for a Go binary under hardened runtime)

```xml
<key>com.apple.security.cs.allow-unsigned-executable-memory</key>
<true />
<key>com.apple.security.cs.allow-jit</key>
<true />
<key>com.apple.security.cs.disable-library-validation</key>
<true />
```

- `allow-unsigned-executable-memory` — the Go runtime JITs/writes executable pages
  (goroutine stacks, plugin loading); hardened runtime blocks this by default.
- `allow-jit` — same class of protection, required for Go's runtime-generated code.
- `disable-library-validation` — lets the binary dlopen non-Apple-signed shared
  libraries (cgo dependencies) without hardened runtime rejecting them.

## Verify

```sh
codesign -dv bin/yourbinary
```

Check the `Identifier=` and `Authority=Developer ID Application: ...` lines. After
re-signing an already-installed/running binary, macOS may prompt **once more** for
the affected TCC permission — after that click-through, the grant sticks across
future rebuilds (same identifier + same signing identity).

## Gotchas

- **LaunchAgent-run binaries attribute TCC prompts to the binary itself**, not to
  Terminal or the parent process — don't debug the wrong process's permissions.
- Signing must happen **after** the final binary is on disk. Any post-sign edit
  (strip, patch, re-link) invalidates the signature and TCC forgets the grant again.
- Never derive `--identifier` from version, git SHA, or build date — it must be
  constant across every rebuild or the grant resets each release.

## Provenance

- Canonical recipe: `~/Zysys/Software/obsidian-backup/mise.toml` (`[tasks.build]`)
  and `~/Zysys/Software/obsidian-backup/entitlements.plist`.
- Adopted in agentmux with identifier `com.zysys.agentmux`.
