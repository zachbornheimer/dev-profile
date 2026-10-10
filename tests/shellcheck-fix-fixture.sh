#!/usr/bin/env bash
# The commit-time shell fixer quotes what is safe to quote and leaves the rest
# alone: heredoc bodies, and expansions that may split on purpose.
# Usage: shellcheck-fix-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: shellcheck-fix-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT
fixer="${out}/bin/dev-profile-shellcheck-fix"

fail() {
	echo "FAIL shellcheck-fix fixture: $*" >&2
	exit 1
}

cd "${work}"
git init -q

# A heredoc whose body holds its own marker, a lone unquoted variable, and two
# expansions whose splitting is the point.
cat >sample.sh <<'SAMPLE'
#!/usr/bin/env bash
f=$1
cat >"$f" <<'STUB'
echo "x STUB y"
STUB
chmod +x $f
for _ in $(seq 3); do :; done
v="$(${CMD:-mise latest} x)"
echo "$v"
SAMPLE
cat >expected.txt <<'EXPECTED'
#!/usr/bin/env bash
f=$1
cat >"$f" <<'STUB'
echo "x STUB y"
STUB
chmod +x "$f"
for _ in $(seq 3); do :; done
v="$(${CMD:-mise latest} x)"
echo "$v"
EXPECTED

"${fixer}" sample.sh || fail "the fixer must succeed"
diff -u expected.txt sample.sh || fail "only the lone variable may change"
bash -n sample.sh || fail "the fixed script must still parse"

cp sample.sh once.sh
"${fixer}" sample.sh || fail "a second run must succeed"
cmp -s once.sh sample.sh || fail "a second run must change nothing"
"${fixer}" || fail "no files must be a no-op"
echo "shellcheck-fix fixture ok"
