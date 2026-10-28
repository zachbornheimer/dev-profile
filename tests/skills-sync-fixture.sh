#!/usr/bin/env bash
# Upstream skills are installed from the record, not committed. This fixture
# proves the three behaviors that depend on: `aubx-skills sync` installs exactly
# the recorded github skills that are missing, the ignore list is derived from
# the record (a local skill stays tracked), and the pull hook starts that sync
# only in the checkout that backs AGENTS_HOME. The installer is a stub, so the
# fixture is offline and deterministic.
# Usage: skills-sync-fixture.sh [aubx-skills] [hook]
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
wrapper="${1:-${root}/agents/bin/aubx-skills}"
hook="${2:-${root}/agents/hooks/skills-sync-on-pull}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

fail() {
	echo "FAIL skills sync fixture: $*" >&2
	exit 1
}

command -v jq >/dev/null 2>&1 || fail "jq is required"

# Stub installer: `aubx skills add <source> --skill <names...> [flags]` run
# under the wrapper's throwaway HOME. Writes each named skill and its record
# entry where the real installer would, and logs every call.
mkdir -p "${work}/stub"
cat >"${work}/stub/aubx" <<STUB
#!/usr/bin/env bash
set -eu
echo "\$*" >>"${work}/calls.log"
shift 2
src="\$1"; shift
names=()
if [ "\${1:-}" = "--skill" ]; then
	shift
	while [ "\$#" -gt 0 ] && [ "\${1#-}" = "\$1" ]; do names+=("\$1"); shift; done
fi
mkdir -p "\$HOME/.agents/skills"
lock="\$HOME/.agents/.skill-lock.json"
[ -f "\$lock" ] || echo '{"version":3,"skills":{}}' >"\$lock"
for n in "\${names[@]}"; do
	mkdir -p "\$HOME/.agents/skills/\$n"
	printf -- '---\nname: %s\n---\n' "\$n" >"\$HOME/.agents/skills/\$n/SKILL.md"
	jq --arg n "\$n" --arg s "\$src" '.skills[\$n] = {source: \$s, sourceType: "github"}' "\$lock" >"\$lock.t"
	mv "\$lock.t" "\$lock"
done
STUB
chmod +x "${work}/stub/aubx"

# The checkout backing AGENTS_HOME: a git repo whose agents/ is the roster.
repo="${work}/repo"
skills="${repo}/agents/available-skills"
mkdir -p "${skills}/alpha" "${skills}/local-one" "${repo}/agents/bin"
printf -- '---\nname: alpha\n---\n' >"${skills}/alpha/SKILL.md"
printf -- '---\nname: local-one\n---\n' >"${skills}/local-one/SKILL.md"
cp "${wrapper}" "${repo}/agents/bin/aubx-skills"
cat >"${skills}/.skill-lock.json" <<'JSON'
{"version":3,"skills":{
  "alpha":{"source":"owner/one","sourceType":"github"},
  "beta":{"source":"owner/two","sourceType":"github"},
  "local-one":{"source":"/tmp/somewhere","sourceType":"local"}
}}
JSON
git init -q "${repo}"

# A copy of the primary aubx guard sits ahead of the installer on PATH, as
# ~/.local/bin/aubx does when a fresh clone runs with AGENTS_HOME pointing at
# it. The wrapper must skip it; resolving it re-enters the confiner.
mkdir -p "${work}/guard"
printf '#!/usr/bin/env bash\n# aubx — scope guard in front of aube'"'"'s `aubx`.\necho "guard re-entered" >&2\nexit 127\n' >"${work}/guard/aubx"
chmod +x "${work}/guard/aubx"
export HOME="${work}/home" AGENTS_HOME="${repo}/agents"
export PATH="${work}/guard:${work}/stub:${PATH}"
mkdir -p "${HOME}"
sync() { "${repo}/agents/bin/aubx-skills" sync >"${work}/out.txt" 2>&1; }

# 1. Only the missing recorded github skill is installed, from its own source.
sync || {
	cat "${work}/out.txt" >&2
	fail "sync exited nonzero"
}
[ -f "${skills}/beta/SKILL.md" ] || fail "sync did not install the missing skill"
[ "$(wc -l <"${work}/calls.log" | tr -d ' ')" = "1" ] || fail "sync must run the installer once, for the missing skill only"
grep -q '^skills add owner/two --skill beta ' "${work}/calls.log" || fail "sync must install beta from owner/two: $(cat "${work}/calls.log")"

# 2. The ignore list names every recorded github skill and no local one.
grep -qx '/alpha/' "${skills}/.gitignore" || fail "a recorded github skill must be ignored"
grep -qx '/beta/' "${skills}/.gitignore" || fail "a newly installed github skill must be ignored"
if grep -q 'local-one' "${skills}/.gitignore"; then fail "a local skill must stay tracked"; fi

# 3. Nothing missing: no installer call.
: >"${work}/calls.log"
sync || fail "a no-op sync must exit 0"
[ ! -s "${work}/calls.log" ] || fail "a complete roster must not call the installer"

# 4. The pull hook in the backing checkout restores a removed skill.
rm -rf "${skills}/beta"
(cd "${repo}" && "${hook}") 2>/dev/null
for _ in $(seq 1 100); do
	[ -f "${skills}/beta/SKILL.md" ] && break
	sleep 0.2
done
[ -f "${skills}/beta/SKILL.md" ] || fail "the pull hook did not restore a removed skill"

# 5. The hook in any other repository does nothing.
rm -rf "${skills}/beta"
: >"${work}/calls.log"
git init -q "${work}/other"
(cd "${work}/other" && "${hook}") 2>/dev/null
sleep 1
[ ! -s "${work}/calls.log" ] || fail "the hook must not sync from an unrelated repository"
[ ! -e "${skills}/beta" ] || fail "the hook must not touch the roster from an unrelated repository"

echo "skills sync fixture ok"
