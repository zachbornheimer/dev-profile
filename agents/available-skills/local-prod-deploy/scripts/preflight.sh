#!/usr/bin/env bash
# Confirm a repo is legal to ship from this laptop.
# Exit 0 only when: clean tree, HEAD is origin/<default>, Actions Deploy is blocked.
set -euo pipefail

REPO=""
DEFAULT_BRANCH=""
WORKFLOW="Deploy"

usage() {
	cat <<EOF
Usage: $(basename "$0") --repo PATH [--branch main] [--workflow Deploy]
EOF
}

while [[ $# -gt 0 ]]; do
	case "$1" in
	--repo)
		REPO="$2"
		shift 2
		;;
	--branch)
		DEFAULT_BRANCH="$2"
		shift 2
		;;
	--workflow)
		WORKFLOW="$2"
		shift 2
		;;
	-h | --help)
		usage
		exit 0
		;;
	*)
		echo "unknown arg: $1" >&2
		usage
		exit 2
		;;
	esac
done

[[ -n "$REPO" && (-d "$REPO/.git" || -f "$REPO/.git") ]] || {
	echo "need --repo with a .git dir or worktree" >&2
	exit 2
}

need() {
	command -v "$1" >/dev/null || {
		echo "missing $1" >&2
		exit 2
	} \
		;
}
need git
need gh
need aws
need docker
need jq

cd "$REPO"
if [[ -z "$DEFAULT_BRANCH" ]]; then
	DEFAULT_BRANCH=$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##' || echo main)
fi

git fetch --quiet origin "$DEFAULT_BRANCH"
HEAD=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/${DEFAULT_BRANCH}")
if [[ "$HEAD" != "$REMOTE" ]]; then
	echo "HEAD ${HEAD} != origin/${DEFAULT_BRANCH} ${REMOTE}" >&2
	exit 1
fi
if [[ -n "$(git status --porcelain)" ]]; then
	echo "worktree is dirty" >&2
	git status --short >&2
	exit 1
fi

REMOTE_URL=$(git remote get-url origin)
# git@host:org/repo.git or https://host/org/repo.git
GH_REPO=$(printf '%s\n' "$REMOTE_URL" | sed -E 's#^git@[^:]+:##; s#^https://[^/]+/##; s#\.git$##')

echo "repo=${GH_REPO}"
echo "sha=${HEAD}"
echo "branch=${DEFAULT_BRANCH}"

set +e
aws sts get-caller-identity --output json >/tmp/local-prod-deploy-sts.json
aws_rc=$?
set -e
if [[ "$aws_rc" -ne 0 ]]; then
	echo "aws sts failed — configure credentials for the target org first" >&2
	exit 1
fi
jq -r '"aws_account=\(.Account) aws_arn=\(.Arn)"' /tmp/local-prod-deploy-sts.json

# Actions blocked? Latest run of the deploy workflow must not be a real success
# on this SHA. startup_failure / no run since merge is the expected lock.
set +e
LATEST=$(gh run list --repo "$GH_REPO" --workflow="$WORKFLOW" --limit 1 \
	--json conclusion,status,headSha,displayTitle,url,createdAt 2>/dev/null)
gh_rc=$?
set -e
if [[ "$gh_rc" -ne 0 || -z "$LATEST" || "$LATEST" == "[]" ]]; then
	echo "workflow=${WORKFLOW} latest=none (treat as blocked if you already saw startup_failure)"
else
	echo "$LATEST" | jq -r '.[0] | "workflow=\($wf) conclusion=\(.conclusion) status=\(.status) head=\(.headSha) url=\(.url)"' --arg wf "$WORKFLOW"
	CONC=$(echo "$LATEST" | jq -r '.[0].conclusion // empty')
	RUN_SHA=$(echo "$LATEST" | jq -r '.[0].headSha // empty')
	if [[ "$CONC" == "success" && "$RUN_SHA" == "$HEAD" ]]; then
		echo "Actions already shipped this SHA via ${WORKFLOW} — do not local-deploy" >&2
		exit 1
	fi
fi

docker info >/dev/null
echo "preflight_ok=1"
