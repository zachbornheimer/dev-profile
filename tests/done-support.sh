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
# Real test-local SSH signatures avoid dependence on the private user keyring.
ssh-keygen -q -t ed25519 -N '' -C done-fixture -f "$work/signing-key"
principal=done-fixture@example.com
printf '%s %s\n' "$principal" "$(cat "$work/signing-key.pub")" >"$work/allowed-signers"
# Deploy the complete profile-owned config over the stale live shape that caused
# the regression. Keep this inside a scratch HOME, never the user's installation.
python3 - "$root" "$work" <<'PY'
import json, os, pathlib, subprocess, sys, tomllib
root, work = map(pathlib.Path, sys.argv[1:])
if os.environ.get('DONE_DEPLOY_CONFIG') != '1':
    (work / 'worktrunk.toml').write_text((root / 'config/worktrunk.toml').read_text())
    sys.exit(0)
source = tomllib.loads((root / 'config/mise.toml').read_text())
entry = source['dotfile_groups']['dev-profile']['entries']['~/.config/worktrunk/config.toml/dev-profile']
home = work / 'home'
target = home / '.config/worktrunk/config.toml'
target.parent.mkdir(parents=True)
target.write_text('[aliases]\ndone = "dev-profile-done"\nretire = "dev-profile-done --drop"\n')
config = work / 'mise-config.toml'
config.write_text('[settings]\ndotfiles.root = ' + json.dumps(str(root)) + '\n'
    '[dotfile_groups.dev-profile]\nroot = "."\nexclude = ["**"]\n[dotfile_groups.dev-profile.entries]\n'
    '"~/.config/worktrunk/config.toml/dev-profile" = { source = ' + json.dumps(entry['source']) + ', merge = true }\n')
env = os.environ | {'HOME': str(home), 'XDG_CONFIG_HOME': str(home / '.config'),
    'MISE_GLOBAL_CONFIG_FILE': str(config), 'MISE_CONFIG_FILE': str(config),
    'MISE_STATE_DIR': str(work / 'mise-state'), 'MISE_DATA_DIR': str(work / 'mise-data'),
    'MISE_CACHE_DIR': str(work / 'mise-cache'), 'MISE_TRUSTED_CONFIG_PATHS': str(work),
    'MISE_OFFLINE': 'true', 'MISE_AUTO_INSTALL': 'false'}
subprocess.run(['mise', '-C', str(home), 'dot', 'apply', '--yes'], env=env, check=True)
deployed = tomllib.loads(target.read_text())
expected = tomllib.loads((root / entry['source']).read_text())
assert deployed['aliases'] == expected['aliases'], 'mise deployment changed the public alias set'
(work / 'worktrunk.toml').write_text(target.read_text())
PY
# Sandbox host composition only: every alias stays byte-for-byte equivalent.
# Git hooks/signing remain authoritative; workstation adapters are out of scope.
bun -e '
const fs = require("node:fs");
const path = process.argv[1];
const config = Bun.TOML.parse(fs.readFileSync(path, "utf8"));
for (const key of ["pre-start", "post-start", "post-remove", "post-switch", "pre-merge", "post-commit"]) delete config[key];
config["worktree-path"] = "{{ repo_path }}/../{{ repo }}-{{ branch | sanitize }}";
config.commit.generation.command = "printf '\''chore: save unfinished work'\''";
fs.writeFileSync(path, Bun.TOML.stringify(config));
' "$WORKTRUNK_CONFIG_PATH"
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
PATH="$work/tools:$root/bin:$(dirname "$native_wt"):$PATH"
export PATH
setup_clone() {
	origin="$work/$1.git"
	repo="$work/$1"
	git init -q --bare --initial-branch=main "$origin"
	git clone -q "$origin" "$repo"
	git -C "$repo" config user.name 'Worktrunk fixture'
	git -C "$repo" config user.email "$principal"
	git -C "$repo" config gpg.format ssh
	git -C "$repo" config user.signingkey "$work/signing-key"
	git -C "$repo" config commit.gpgsign true
	git -C "$repo" config gpg.ssh.allowedSignersFile "$work/allowed-signers"
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
