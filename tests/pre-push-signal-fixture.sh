#!/usr/bin/env bash
# A gate a supervisor's deadline kills mid-run must say so.
#
# hk cancels the steps that were running when the signal arrived and reports
# whichever command it killed as "command was cancelled", naming a step that
# never reached a verdict. Read on its own that looks like a step finding, and
# an agent chased it through the gate's content for a failure that never
# happened. The wrapper has to name the signal and say the gate judged nothing.
#
# The signal stands in for a supervisor's: a step sends SIGTERM to the hk
# process running it, which is the only signal path that produces hk's
# cancellation report.
#
# Usage: pre-push-signal-fixture.sh [repo-root]
set -euo pipefail
repo="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
scratch="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${scratch}"' EXIT

fail() {
	echo "FAIL pre-push-signal: $*" >&2
	if [[ -e "${scratch}/push.txt" ]]; then sed 's/^/  | /' "${scratch}/push.txt" >&2; fi
	exit 1
}

# One step that signals the hk running it, then outlives it: the gate is still
# in flight when the signal lands.
mkdir -p "${scratch}/hk-config"
cat >"${scratch}/hk-config/config.pkl" <<'PKL'
amends "package://github.com/jdx/hk/releases/download/v2.5.0/hk@2.5.0#/Config.pkl"

hooks {
  ["pre-push"] {
    steps {
      ["signal"] {
        check = "kill -TERM $PPID; sleep 30"
        fix = "kill -TERM $PPID; sleep 30"
      }
    }
  }
}
PKL

# The profile's bin directory on PATH, the way home/gitconfig's hook command has
# it. Seeding the remote runs no hook: this fixture judges one signal, and a
# second gate run would only add noise to its output.
printf '[hook "hk-pre-push"]\n\tevent = pre-push\n\tcommand = test x${DEV_PROFILE_FIXTURE_SKIP_HOOK:-x} = x1 || PATH="%s/bin:${PATH}" dev-profile-pre-push\n' \
	"${repo}" >"${scratch}/gitconfig"
export HK_CONFIG_DIR="${scratch}/hk-config" GIT_CONFIG_GLOBAL="${scratch}/gitconfig" GIT_CONFIG_SYSTEM=/dev/null
export GIT_AUTHOR_NAME=fixture GIT_AUTHOR_EMAIL=fixture@example.invalid
export GIT_COMMITTER_NAME=fixture GIT_COMMITTER_EMAIL=fixture@example.invalid
unset HK HK_FILE

commit() { # <message>
	git -C "${scratch}/work" add -A
	git -C "${scratch}/work" -c commit.gpgsign=false commit -qm "$1"
}

git init -q --bare "${scratch}/remote.git"
git init -q -b main "${scratch}/work"
git -C "${scratch}/work" remote add origin "${scratch}/remote.git"
printf 'hello\n' >"${scratch}/work/a.txt"
commit "feat: first file"
DEV_PROFILE_FIXTURE_SKIP_HOOK=1 git -C "${scratch}/work" push -q origin main ||
	fail "the seeding push must pass"

git -C "${scratch}/work" switch -q -c feature
printf 'second\n' >>"${scratch}/work/a.txt"
commit "feat: another line"

if git -C "${scratch}/work" push origin feature >"${scratch}/push.txt" 2>&1; then
	fail "a gate stopped by a signal must refuse the push"
fi

# hk's own line is the one that reads like a step finding: reproduce it first, so
# the wrapper's diagnosis is a fix for this failure and not for another.
grep -q 'command was cancelled' "${scratch}/push.txt" ||
	fail "hk must report the killed run as 'command was cancelled'"
grep -q 'was stopped by TERM' "${scratch}/push.txt" ||
	fail "the wrapper must name the signal that stopped the gate"
grep -q 'Nothing in the gate failed' "${scratch}/push.txt" ||
	fail "the wrapper must say the gate judged nothing"

echo "ok pre-push-signal"
