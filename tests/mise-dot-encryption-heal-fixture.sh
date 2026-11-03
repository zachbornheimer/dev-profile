#!/usr/bin/env bash
# The heal must write down the encryption a bare `mise dot track` entry drops,
# and must leave every deliberate choice alone.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
heal="$root/bin/dev-profile-mise-dot-encryption-heal"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

mkdir -p "$work/.config/mise" "$work/bin"
export HOME="$work"
# The heal calls python3. Keep the caller's PATH — mise shims above all, which fail when the
# tool is not in this scratch HOME's config — out of it: the fixture's own mise stub and the
# system tools are all it needs.
export PATH="$work/bin:/usr/bin:/bin"
calls="$work/mise-calls"
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$*" >>"%s"\n' "$calls" >"$work/bin/mise"
chmod +x "$work/bin/mise"

cfg="$work/.config/mise/config.toml"
fail() {
	echo "FAIL: $*" >&2
	exit 1
}
write_cfg() {
	cat >"$cfg" <<'EOF'
[history]
exclude = ["age.txt"]

[dotfiles]
"~/.config/enc" = { mode = "track", encrypt = true, exclude = ["*.bak*"] }
"~/.config/enc/dropped.sh" = { mode = "track" }
"~/.config/enc/chosen.sh" = { mode = "track", encrypt = false }
"~/.config/enc/nested/deep/deeper.sh" = { mode = "track" }
"~/.config/enc/already.sh" = { mode = "track", encrypt = true }
"~/.config/plain/other.sh" = { mode = "track" }
"~/.worktrunk" = { source = "~/somewhere" }
EOF
}

# A dry run names the bare children, writes nothing, and runs no save.
write_cfg
bash "$heal" --dry-run >"$work/plan" 2>"$work/plan.err"
grep -qx 'would heal ~/.config/enc/dropped.sh' "$work/plan" || fail "dry run missed the bare child"
grep -qx 'would heal ~/.config/enc/nested/deep/deeper.sh' "$work/plan" || fail "dry run missed the nested child"
grep -qx 'would heal ~/.config/plain/other.sh' "$work/plan" || fail "dry run missed the bare entry in no encrypted directory"
[ "$(wc -l <"$work/plan" | tr -d ' ')" = 3 ] || fail "dry run named the wrong set: $(tr '\n' ' ' <"$work/plan")"
grep -q '"~/.config/enc/dropped.sh" = { mode = "track" }$' "$cfg" || fail "dry run wrote the config"
[ ! -e "$calls" ] || fail "dry run ran mise"

# A real run writes the declarations, saves once, and touches nothing else.
write_cfg
bash "$heal" >"$work/log" 2>&1
grep -q '"~/.config/enc/dropped.sh" = { mode = "track", encrypt = true }' "$cfg" || fail "bare child not healed"
grep -q '"~/.config/enc/nested/deep/deeper.sh" = { mode = "track", encrypt = true }' "$cfg" || fail "nested child not healed"
grep -q '"~/.config/enc/chosen.sh" = { mode = "track", encrypt = false }' "$cfg" || fail "a deliberate encrypt = false was overwritten"
grep -q '"~/.config/plain/other.sh" = { mode = "track", encrypt = true }' "$cfg" || fail "a bare entry in no encrypted directory was left bare"
grep -q '"~/.config/enc/already.sh" = { mode = "track", encrypt = true }' "$cfg" || fail "an already-correct entry was rewritten"
grep -q '"~/.worktrunk" = { source = "~/somewhere" }' "$cfg" || fail "a source entry was touched"
grep -qx '\[history\]' "$cfg" || fail "an unrelated section was dropped"
grep -qx 'dot save' "$calls" || fail "the change was never saved"

# Idempotent: a second run heals nothing, stays silent, and saves nothing.
before="$(wc -l <"$calls" | tr -d ' ')"
bash "$heal" >"$work/log2" 2>&1
[ ! -s "$work/log2" ] || fail "second run was not silent: $(cat "$work/log2")"
[ "$(wc -l <"$calls" | tr -d ' ')" = "$before" ] || fail "second run saved again"

echo 'mise dot encryption heal: ok'
