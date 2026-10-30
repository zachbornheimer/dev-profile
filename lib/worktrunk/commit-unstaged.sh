# shellcheck shell=sh
git stash push -u || exit 1
cmd='git stash pop && wt step commit && wt merge'
if git show-ref --verify --quiet refs/heads/chore/uncommited; then
	wt switch chore/uncommited --no-cd -x sh -- -c "$cmd"
else
	wt switch --create chore/uncommited --no-cd -x sh -- -c "$cmd"
fi
status=$?
if [ "$status" -eq 0 ]; then
	wt switch ^
else
	wt switch chore/uncommited
	exit "$status"
fi
