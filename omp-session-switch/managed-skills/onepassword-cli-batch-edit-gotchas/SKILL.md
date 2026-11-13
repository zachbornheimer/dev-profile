---
name: onepassword-cli-batch-edit-gotchas
description: "Avoid stdin consumption, TSV column shifting, 409 vault content_version conflicts, and SSH_KEY CLI errors when batch-editing or tagging 1Password items with op item edit on macOS."
---

# 1Password CLI (`op`) Batch Item Editing & Tagging on macOS

Use this reference when batch-updating or tagging items in 1Password with `op item edit`.

## Four Critical `op item edit` Gotchas

1. **Non-TTY `stdin` is parsed as a JSON item template:**
   - Whenever `op item edit` runs with non-TTY `stdin` (for example inside `while read ...; do op item edit ...; done < <(...)`), `op` reads from `stdin` expecting a JSON item template.
   - This both fails the edit and swallows bytes from the loop's input stream, shifting columns on subsequent rows.
   - **Rule:** Always pass `stdin=subprocess.DEVNULL` (or `</dev/null` in shell) to every `op item edit` invocation, and parse `op item list --format=json` in Python rather than splitting TSV in bash `read` (which collapses empty tab-delimited columns).

2. **Parallel `op item edit` calls fail with `409 Conflict` and Desktop App socket timeouts:**
   - The 1Password Desktop App's local IPC socket and per-vault `content_version` serialize writes per vault.
   - Running concurrent `op item edit` workers triggers `(409) Conflict: Internal server conflict` and `connecting to desktop app timed out`.
   - **Rule:** Run `op item edit` **sequentially (`1` at a time)** with a short retry/backoff on `409` or `timed out`.

3. **`SSH_KEY` items cannot be edited via CLI:**
   - `op item edit` rejects `SSH_KEY` items with: `SSH Key item editing in the CLI is not yet supported.`
   - **Rule:** Filter out `category == "SSH_KEY"` before calling `op item edit` and report `SSH_KEY` items separately for GUI updates.

4. **Reaching all vaults (including `Personal`) on macOS:**
   - The shell's `OP_SERVICE_ACCOUNT_TOKEN` is read-only and only sees shared/service vaults.
   - To reach all vaults (including `Personal`) with write access via Touch ID delegation:
     ```bash
     unset OP_SERVICE_ACCOUNT_TOKEN
     unset OP_BIOMETRIC_UNLOCK_ENABLED
     OP_BIN="/opt/homebrew/bin/op" # bypass ~/.local/share/mise/shims/op overhead
     ```
