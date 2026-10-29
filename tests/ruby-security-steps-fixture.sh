#!/usr/bin/env bash
# The brakeman and bundle-audit pre-push steps judge the pushed Ruby files of a repo
# whose Ruby lives in subdirectories. hk runs both steps from the repo root and
# hands them the changed files as relative paths, in the shapes the tools refuse:
# brakeman takes one path (the Rails app root) and read the last changed file,
# spec/support/capybara.rb, as the app ("Please supply the path to a Rails
# application"); bundle-audit check takes a project directory and read the
# lockfile as one ("No such file or directory: Gemfile.lock"). A clean push must
# pass with both steps run, and a real finding must still fail the push, whether
# the app sits at the repo root or below it. Real brakeman, bundle-audit and the
# local advisory database; skips when one is missing.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scratch="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${scratch}"' EXIT

for tool in brakeman bundle-audit; do
	command -v "${tool}" >/dev/null 2>&1 || {
		echo "ruby-security-steps fixture skipped: ${tool} not installed"
		exit 0
	}
done
mise exec ruby@4 -- brakeman --version >/dev/null 2>&1 || {
	echo "ruby-security-steps fixture skipped: ruby@4 brakeman not available"
	exit 0
}

fail() {
	echo "FAIL ruby-security-steps: $*" >&2
	[[ ! -f "${scratch}/push.txt" ]] || sed 's/^/  | /' "${scratch}/push.txt" >&2
	exit 1
}

# The profile's hk config, active the way bootstrap links it, run by git's pre-push
# hook with the profile's bin directory on PATH, as home/gitconfig's hook command
# puts it. Only the two steps this fixture judges run. The fixture's gitconfig
# defines no commit hooks, so its commits run none.
mkdir -p "${scratch}/hk-config"
ln -s "${repo}/hk/hk.pkl" "${scratch}/hk-config/config.pkl"
printf '[hook "hk-pre-push"]\n\tevent = pre-push\n\tcommand = PATH="${PATH}:%s/bin" hk run pre-push -S brakeman -S bundle-audit\n' \
	"${repo}" >"${scratch}/gitconfig"
export HK_CONFIG_DIR="${scratch}/hk-config" GIT_CONFIG_GLOBAL="${scratch}/gitconfig" GIT_CONFIG_SYSTEM=/dev/null
export GIT_AUTHOR_NAME=fixture GIT_AUTHOR_EMAIL=fixture@example.invalid
export GIT_COMMITTER_NAME=fixture GIT_COMMITTER_EMAIL=fixture@example.invalid
unset HK HK_FILE

work="${scratch}/work"
git init -q --bare "${scratch}/remote.git"
git init -q -b main "${work}"
git -C "${work}" remote add origin "${scratch}/remote.git"
printf 'fixture\n' >"${work}/README.md"
git -C "${work}" add -A
git -C "${work}" -c commit.gpgsign=false commit -qm "chore: first file"
git -C "${work}" push -q origin HEAD >"${scratch}/push.txt" 2>&1 || fail "the base push must pass"

# lockfile <dir> <gem> <version>: a one-gem Gemfile.lock under <dir>.
lockfile() {
	mkdir -p "${work}/$1"
	printf 'GEM\n  remote: https://rubygems.org/\n  specs:\n    %s (%s)\n\nPLATFORMS\n  ruby\n\nDEPENDENCIES\n  %s\n\nBUNDLED WITH\n   2.5.0\n' \
		"$2" "$3" "$2" >"${work}/$1/Gemfile.lock"
}
# rails_app <dir> <controller body>: the files of a minimal Rails app under <dir>,
# with a spec support file in a subdirectory that is not under app/.
rails_app() {
	mkdir -p "${work}/$1/app/controllers" "${work}/$1/spec/support"
	printf "source 'https://rubygems.org'\ngem 'rake'\n" >"${work}/$1/Gemfile"
	printf 'class ApplicationController < ActionController::Base\n  protect_from_forgery with: :exception\nend\n' \
		>"${work}/$1/app/controllers/application_controller.rb"
	printf '%s\n' "$2" >"${work}/$1/app/controllers/users_controller.rb"
	printf 'RSpec.configure { |config| config.order = :random }\n' >"${work}/$1/spec/support/helper.rb"
}
clean_controller='class UsersController < ApplicationController
  def index
    @users = User.all
  end
end'
sql_injection_controller='class UsersController < ApplicationController
  def index
    @users = User.where("name = '"'"'#{params[:name]}'"'"'")
  end
end'

# push_branch <branch>: commit the working tree on a new branch off main and push it.
push_branch() {
	git -C "${work}" switch -q main
	git -C "${work}" switch -q -c "$1"
	git -C "${work}" add -A
	git -C "${work}" -c commit.gpgsign=false commit -qm "feat: $1"
	(cd "${work}" && git push -q origin "$1") >"${scratch}/push.txt" 2>&1
}
# next_case: a clean tree on main for the next branch.
next_case() {
	git -C "${work}" switch -q main
	git -C "${work}" clean -qfdx
}
expect_step_ran() { grep -q "✔ $1" "${scratch}/push.txt" || fail "$2: the $1 step must have run and passed"; }
expect_step_failed() { grep -q "✗ $1" "${scratch}/push.txt" || fail "$2: the $1 step must be the one that fails"; }

# 1. The app at the repo root, a spec support file among the pushed files: the last
# changed file must not be read as the app path, nor the lockfile as a directory.
rails_app . "${clean_controller}"
lockfile . rake 13.2.1
push_branch root-app || fail "root app: a clean push must pass"
expect_step_ran brakeman "root app"
expect_step_ran bundle-audit "root app"

# 2. The app below the repo root: brakeman needs its own root, and bundle-audit
# its project directory.
next_case
rails_app services/api "${clean_controller}"
lockfile services/api rake 13.2.1
push_branch nested-app || fail "nested app: a clean push must pass"
expect_step_ran brakeman "nested app"
expect_step_ran bundle-audit "nested app"

# 3. Two apps in one push: each is scanned from its own root.
next_case
rails_app services/api "${clean_controller}"
rails_app services/web "${clean_controller}"
lockfile services/api rake 13.2.1
lockfile services/web rake 13.2.1
push_branch two-apps || fail "two apps: a clean push must pass"
expect_step_ran brakeman "two apps"
expect_step_ran bundle-audit "two apps"

# 4. The checks have not been switched off: a finding in a nested app fails the push.
next_case
rails_app services/api "${sql_injection_controller}"
if push_branch nested-sql-injection; then fail "a SQL injection in a pushed controller must fail the push"; fi
expect_step_failed brakeman "nested SQL injection"

# 5. ... and so does an advisory against a nested lockfile.
next_case
lockfile services/api rack 1.6.0
if push_branch nested-vulnerable-lock; then fail "a vulnerable gem in a pushed lockfile must fail the push"; fi
expect_step_failed bundle-audit "nested vulnerable lockfile"

# 6. A pushed Ruby file in no Rails app is not brakeman's to scan: the push passes
# and the file is named as not scanned.
next_case
mkdir -p "${work}/scripts"
printf 'puts "hello"\n' >"${work}/scripts/tool.rb"
push_branch no-rails-app || fail "a Ruby file in no Rails app must not fail the push"
grep -q 'scripts/tool.rb is in no Rails app' "${scratch}/push.txt" || fail "no Rails app: the file must be named as not scanned"

echo "ok ruby-security-steps"
