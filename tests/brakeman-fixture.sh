#!/usr/bin/env bash
# dev-profile-brakeman blocks a push only on the warnings it introduces. Some warnings
# belong to the whole app (a Rails past end of life is reported from Gemfile.lock
# whichever files are scanned), so a gate that failed on every warning would reject
# every push to such an app. The base's own warnings are printed as pre-existing and
# never hidden; a warning the base lacks fails the push. Real brakeman through mise
# ruby@4; skips when it is unavailable. Usage: brakeman-fixture.sh
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mise exec ruby@4 -- brakeman --version >/dev/null 2>&1 || {
	echo "brakeman fixture skipped: ruby@4 brakeman not available"
	exit 0
}

work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT
fail() {
	echo "FAIL brakeman fixture: $*" >&2
	[[ ! -f "${work}/out.txt" ]] || sed 's/^/  | /' "${work}/out.txt" >&2
	exit 1
}

export GIT_CONFIG_GLOBAL="${work}/gitconfig" GIT_CONFIG_NOSYSTEM=1
git config --file "${GIT_CONFIG_GLOBAL}" user.name fixture
git config --file "${GIT_CONFIG_GLOBAL}" user.email fixture@example.invalid
git config --file "${GIT_CONFIG_GLOBAL}" commit.gpgsign false
export PATH="${repo}/bin:${PATH}"

clean_controller='class UsersController < ApplicationController
  def index
    @users = User.all
  end
end'
sql_injection='    @found = User.where("name = '"'"'#{params[:name]}'"'"'")'

# app <dir>: a minimal Rails app under <dir> on Rails 7.0.8, which brakeman reports as
# an end-of-life dependency: a High warning on Gemfile.lock, not on any app file.
app() {
	mkdir -p "$1/app/controllers" "$1/config"
	printf "source 'https://rubygems.org'\ngem 'rails', '7.0.8'\n" >"$1/Gemfile"
	printf 'GEM\n  remote: https://rubygems.org/\n  specs:\n    rails (7.0.8)\n\nPLATFORMS\n  ruby\n\nDEPENDENCIES\n  rails (= 7.0.8)\n\nBUNDLED WITH\n   2.5.0\n' >"$1/Gemfile.lock"
	printf 'class ApplicationController < ActionController::Base\n  protect_from_forgery with: :exception\nend\n' >"$1/app/controllers/application_controller.rb"
	printf '%s\n' "${clean_controller}" >"$1/app/controllers/users_controller.rb"
}
# controller <dir> <extra line>: users_controller with <extra line> in #index.
controller() {
	printf 'class UsersController < ApplicationController\n  def index\n    @users = User.all\n%s\n  end\nend\n' "$2" >"$1/app/controllers/users_controller.rb"
}

# repo_with_base <name> <command…>: a repo whose origin/main is the commit holding what
# <command…> builds in it, switched to a feature branch for the change under test.
repo_with_base() {
	local name="$1"
	shift
	rm -rf "${work:?}/${name}"
	git init -q -b main "${work}/${name}"
	(cd "${work}/${name}" && "$@" && git add -A && git commit -qm "base" && git update-ref refs/remotes/origin/main HEAD && git switch -qc feature)
}
# run <repo> <file>…: the wrapper, from the repo root, output captured in out.txt.
run() {
	local dir="$1"
	shift
	(cd "${work}/${dir}" && dev-profile-brakeman "$@") >"${work}/out.txt" 2>&1
}
expect_out() { grep -qF -- "$1" "${work}/out.txt" || fail "$2: output must contain: $1"; }
expect_no_out() { ! grep -qF -- "$1" "${work}/out.txt" || fail "$2: output must not contain: $1"; }
commit() {
	(cd "${work}/$1" && git add -A && git commit -qm "$2")
}

# 1. A clean change in an app whose base already carries the repo-wide High warning
# passes, and the warning is printed as pre-existing, not hidden.
repo_with_base a app .
controller "${work}/a" ""
commit a "touch users"
run a app/controllers/users_controller.rb || fail "pre-existing High on Gemfile.lock must not fail the push"
expect_out "pre-existing warnings" "pre-existing"
expect_out "Unmaintained Dependency" "pre-existing"
expect_out "Gemfile.lock" "pre-existing"
expect_out "0 introduced" "pre-existing"
expect_no_out "warnings introduced by this push" "pre-existing"

# 2. A High warning the push introduces still fails it, and the pre-existing warning
# stays visible beside it.
controller "${work}/a" "${sql_injection}"
commit a "add sql injection"
if run a app/controllers/users_controller.rb; then fail "an introduced SQL injection must fail the push"; fi
expect_out "warnings introduced by this push" "introduced"
expect_out "SQL Injection" "introduced"
expect_out "pre-existing warnings" "introduced"

# 3. A warning the base already had does not fail the push when an edit only moves it:
# lines added above the vulnerable line change its number, not its fingerprint.
sqli_app() {
	app .
	controller . "${sql_injection}"
}
repo_with_base b sqli_app
(cd "${work}/b" && printf 'class UsersController < ApplicationController\n  # one\n  # two\n  def index\n    @users = User.all\n%s\n  end\nend\n' "${sql_injection}" >app/controllers/users_controller.rb)
commit b "shift the vulnerable line"
run b app/controllers/users_controller.rb || fail "a pre-existing SQL injection that only moved must not fail the push"
expect_out "SQL Injection" "moved"
expect_no_out "warnings introduced by this push" "moved"

# 4. An app below the repo root is judged against its own copy at the base.
repo_with_base c app services/api
controller "${work}/c/services/api" ""
commit c "touch users"
run c services/api/app/controllers/users_controller.rb || fail "nested app: pre-existing High must not fail the push"
expect_out "pre-existing warnings" "nested"

# 5. An app the base lacks has nothing pre-existing: every warning is introduced.
readme_only() { printf 'fixture\n' >README.md; }
repo_with_base d readme_only
app "${work}/d"
commit d "add the app"
if run d app/controllers/users_controller.rb; then fail "a new app's warnings are all introduced and must fail the push"; fi
expect_out "warnings introduced by this push" "new app"

# 6. With no upstream default branch nothing can be called pre-existing: the full verdict stands.
repo_with_base e app .
git -C "${work}/e" update-ref -d refs/remotes/origin/main
if run e app/controllers/users_controller.rb; then fail "without a base every warning is introduced and must fail the push"; fi
expect_out "no upstream default branch" "no base"

echo "brakeman fixture ok"
