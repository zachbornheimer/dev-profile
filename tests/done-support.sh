#!/usr/bin/env bash
# Shared real-Git sandbox. Identity, signing and Git hooks remain authoritative.
set -euo pipefail
root="$(cd "${1:-$(dirname "${BASH_SOURCE[0]}")/..}" && pwd -P)"
work="$(cd "$(mktemp -d)" && pwd -P)"
cleanup_fixture() {
	local status=$?
	if ((status)); then
		echo "Fixture retained for diagnosis: $work" >&2
		for log in "$work"/*.out; do [[ ! -f "$log" ]] || {
			echo "=== $log ===" >&2
			tail -80 "$log" >&2
		}; done
	else
		rm -rf "$work"
	fi
}
trap cleanup_fixture EXIT
fail() {
	echo "FAIL done fixture: $*" >&2
	exit 1
}
export WORKTRUNK_CONFIG_PATH="$work/worktrunk.toml"
export WORKTRUNK_SYSTEM_CONFIG_PATH="$work/no-system.toml"
export WORKTRUNK_PROJECT_CONFIG_PATH="$work/no-project.toml"
export TRASH_DIR="$work/trash" FORGE_LOG="$work/forge.log"
mkdir -p "$work/tools" "$TRASH_DIR"
# Use only the lifecycle aliases; unrelated workstation hooks aren't this fixture's surface.
python3 - "$root/config/worktrunk.toml" "$WORKTRUNK_CONFIG_PATH" <<'PY'
import sys, tomllib, json
c = tomllib.load(open(sys.argv[1], 'rb'))
with open(sys.argv[2], 'w') as f:
    f.write('worktree-path = "{{ repo_path }}/../{{ repo }}-{{ branch | sanitize }}"\n')
    f.write('[commit.generation]\ncommand = "printf \'chore: save unfinished work\'"\n')
    f.write('[aliases]\n')
    for key, value in c['aliases'].items():
        if key in ('done', 'retire', 'drop') and isinstance(value, str):
            f.write(f'{json.dumps(key)} = {json.dumps(value)}\n')
    for key, value in c['aliases'].items():
        if not key.startswith('done-'):
            continue
        blocks = value if isinstance(value, list) else [value]
        for block in blocks:
            f.write((f'[[aliases.{key}]]' if isinstance(value, list) else f'[aliases.{key}]') + '\n')
            for name, cmd in block.items():
                f.write(f'{json.dumps(name)} = {json.dumps(cmd)}\n')
PY
cat >"$work/tools/gh" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$FORGE_LOG"
if [[ "$1 $2" == 'pr list' && "$*" != *--jq* ]]; then echo '[]'; fi
STUB
cat >"$work/tools/trash" <<'STUB'
#!/usr/bin/env bash
mv "$1" "$TRASH_DIR/"
STUB
chmod +x "$work/tools/gh" "$work/tools/trash"
native_wt=$(mise which wt)
export PATH="$work/tools:$root/bin:$(dirname "$native_wt"):$PATH"
setup_clone() {
	origin="$work/$1.git"
	repo="$work/$1"
	git init -q --bare --initial-branch=main "$origin"
	git clone -q "$origin" "$repo"
	git -C "$repo" config dev-profile.sync-clone "$1"
	printf 'base\n' >"$repo/base.txt"
	git -C "$repo" add base.txt
	git -C "$repo" commit -q -m 'test: seed lifecycle fixture'
	git -C "$origin" fetch -q "$repo" main:main
	git -C "$repo" fetch -q origin
	git -C "$repo" remote set-head origin --auto >/dev/null
}
commit_file() {
	printf '%s\n' "$3" >"$1/$2"
	git -C "$1" add "$2"
	git -C "$1" commit -q -m "test: save $2"
}
run_done() {
	(cd "$repo" && wt -y "$@")
}
