#!/usr/bin/env bash
# A merged live config (worktrunk) moves off the render link onto a regular file
# the profile edits in place: detach-merged copies it out, backup-live keeps its
# first backup as the rollback point, and rollback never deletes the keys you added.
# Usage: live-files-fixture.sh
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

fail() {
	echo "FAIL live-files fixture: $*" >&2
	exit 1
}

export HOME="${work}/home"
export DEV_PROFILE_OUT="${work}/out"
export DEV_PROFILE_BACKUPS="${work}/backups"
mkdir -p "${HOME}/.config/worktrunk" "${HOME}/.config/hk" "${DEV_PROFILE_OUT}" "${work}/bin"

# The tasks read their target lists from profile.pkl; answer as the profile would.
cat >"${work}/bin/pkl" <<'PKL'
#!/usr/bin/env bash
case "$3" in
'mergedTargets.keys.join("\n")') echo "~/.config/worktrunk/config.toml" ;;
*) printf '%s\n' "~/.config/hk/config.pkl" "~/.config/worktrunk/config.toml" ;;
esac
PKL
chmod +x "${work}/bin/pkl"
export PATH="${work}/bin:${PATH}"
task() { (cd "${here}" && bash "mise-tasks/$1" >/dev/null); }

wt_live="${HOME}/.config/worktrunk/config.toml"
printf '[aliases]\nmine = "echo original"\n' >"${wt_live}"
task backup-live
first="$(find "${DEV_PROFILE_BACKUPS}" -mindepth 1 -maxdepth 1)"
[[ -f "${first}${wt_live}" ]] || fail "the original worktrunk config must be backed up"

# The profile as it was: both targets link into the render.
printf 'profile = true\n' >"${DEV_PROFILE_OUT}/worktrunk.toml"
printf 'amends "x"\n' >"${DEV_PROFILE_OUT}/hk-config.pkl"
ln -sf "${DEV_PROFILE_OUT}/worktrunk.toml" "${wt_live}"
ln -sf "${DEV_PROFILE_OUT}/hk-config.pkl" "${HOME}/.config/hk/config.pkl"

task detach-merged
[[ ! -L "${wt_live}" && -f "${wt_live}" ]] || fail "detach-merged must leave a regular file"
grep -qx 'profile = true' "${wt_live}" || fail "detach-merged must keep the render's contents"
[[ -L "${HOME}/.config/hk/config.pkl" ]] || fail "detach-merged must leave linked targets alone"
printf 'mine = "added by hand"\n' >>"${wt_live}"
task detach-merged
grep -qx 'mine = "added by hand"' "${wt_live}" || fail "a second detach-merged must not touch a regular file"

sleep 1 # backups are named by the second
task backup-live
[[ "$(find "${DEV_PROFILE_BACKUPS}" -mindepth 1 -maxdepth 1 | wc -l)" -eq 1 ]] ||
	fail "an already-backed-up merged target must not make a new rollback point"

task rollback
grep -qx 'mine = "echo original"' "${wt_live}" || fail "rollback must restore the original worktrunk config"
[[ ! -e "${HOME}/.config/hk/config.pkl" ]] || fail "rollback must remove a link with no original"

# A newer backup that never held the merged target must not delete it.
printf 'mine = "added later"\n' >"${wt_live}"
sleep 1
mkdir -p "${DEV_PROFILE_BACKUPS}/29990101T000000Z"
cat >"${DEV_PROFILE_BACKUPS}/29990101T000000Z/targets" <<'TARGETS'
~/.config/worktrunk/config.toml
TARGETS
task rollback
grep -qx 'mine = "added later"' "${wt_live}" || fail "rollback must keep a regular file its backup never held"

echo "live-files fixture ok"
