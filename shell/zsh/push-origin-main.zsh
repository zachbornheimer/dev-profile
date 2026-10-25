# Force-with-lease HEAD → origin/main from whatever repo $PWD is in.
# SAH org remotes: briefly org-admin `always` bypass on linear-history / CI /
# signed-default nff, then restore empty bypass_actors on EXIT (even on fail).
# Non-SAH remotes: force-with-lease only — no org ruleset touch.
# Requires: on main/master, gh auth as org admin, signed commits.
push-origin-main() {
	emulate -L zsh
	setopt localtraps
	local root branch origin_url remote_sha audit i
	local org=Software-Automation-Holdings-LLC
	local -a ids=(18071128 19927427 15298483)

	root=$(git rev-parse --show-toplevel) || return 1
	branch=$(git -C "$root" rev-parse --abbrev-ref HEAD) || return 1
	if [[ "$branch" != main && "$branch" != master ]]; then
		__ -t failed "push-origin-main: on '$branch', not main/master"
		return 1
	fi
	origin_url=$(git -C "$root" remote get-url origin) || return 1

	if [[ "$origin_url" == *"${org}"* ]]; then
		audit=$(mktemp -d)
		trap '
      for i in 18071128 19927427 15298483; do
        gh api --method PUT orgs/Software-Automation-Holdings-LLC/rulesets/$i --input '"$audit"'/restore-$i.json >/dev/null
      done
    ' EXIT INT TERM
		for i in $ids; do
			gh api "orgs/${org}/rulesets/$i" | python3 -c "
import json, sys
d = json.load(sys.stdin)
keep = ['name', 'target', 'enforcement', 'bypass_actors', 'conditions', 'rules']
base = {k: d[k] for k in keep if k in d}
rid = str(d['id'])
json.dump(base, open('${audit}/restore-' + rid + '.json', 'w'))
u = dict(base)
u['bypass_actors'] = [{'actor_id': 1, 'actor_type': 'OrganizationAdmin', 'bypass_mode': 'always'}]
json.dump(u, open('${audit}/unlock-' + rid + '.json', 'w'))
" || return 1
			gh api --method PUT "orgs/${org}/rulesets/$i" --input "$audit/unlock-$i.json" >/dev/null || return 1
		done
	fi

	if git -C "$root" rev-parse --verify -q origin/main >/dev/null; then
		remote_sha=$(git -C "$root" rev-parse origin/main)
		git -C "$root" push --no-verify --force-with-lease=refs/heads/main:"$remote_sha" origin HEAD:main
	else
		git -C "$root" push --no-verify --force-with-lease origin HEAD:main
	fi
}
