#!/usr/bin/env bash
# Replays failed oh-my-pi CI runs through probe-build.sh; each must fail with CI's own error text.
# PROBE=path overrides the probe. Needs network (gh, github.com).
set -uo pipefail
P=${PROBE:-$(dirname "$0")/../agents/available-skills/updating-oh-my-pi/scripts/probe-build.sh}
full() { gh api repos/zachbornheimer/oh-my-pi/commits/$1 --jq .sha; }
fail=0
expect() { # run-id expected-text args...
	id=$1 want=$2
	shift 2
	out="$(bash "$P" "$@" 2>&1)"
	rc=$?
	if [ "$rc" = 1 ] && printf '%s' "$out" | grep -qF -- "$want"; then echo "PASS $id"; else
		echo "FAIL $id rc=$rc want: $want"
		printf '%s\n' "$out" | tail -5 | sed 's/^/   /'
		fail=1
	fi
}
expect 43084879761 "conflicts with upstream" --base 261551aa0b7a7f0eb1abc9fd504a9555d264c4dd --pin assembled="$(full 5f59f9bd89)" --no-build
expect 43104365571 "assembled is a merge-only integration base; move non-merge commits" --base 9c9d096718f33976b47ee5662db32464db43a1d4 --pin assembled="$(full a3ec036f2d)" --no-build
expect 43104993748 'Private name "#blockingPrompts" must be declared in an enclosing class' --tree 5b5eb3aaffcc996c4b1517d44bbd7ad22c1c02ba
expect 43156578989 "feat/archive-memory-backend conflicts with upstream" --base a19ec7b58ac083f8a4ea6313048935998bb26465 --pin assembled="$(full a3ec036f2d)" --pin feat/archive-memory-backend="$(full 1fc316d362)" --no-build
expect 43297866221 "files outside the allowed paths" --pr-head 39d5831662a4cb10df60f2b1e1b4fd65f284f372 --pr-base 0408040f687da22b1caca6c26222d693b90847ae --no-build
expect 43301353655 'No matching export in "packages/coding-agent/src/session/session-listing.ts" for import "clearSessionListingCache"' --tree 687dba29b7a582069d7a906b82f3fd06e490de0f
expect 43305316594 "conflicts with upstream" --base 5040ef7dceab7ed5ec2d30edf35b0d0d529b8077 --pin assembled="$(full c1f4294f25)" --no-build
exit $fail
