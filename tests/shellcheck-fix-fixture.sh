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

# A source file is never shell. A template literal reads as an unquoted command
# substitution to shellcheck, so a fixer handed one rewrites valid TypeScript
# into invalid TypeScript. The fixer refuses the call and touches nothing, even
# a shell file named beside it.
cat >template.ts <<'TS'
const PIN = `${homedir()}/.omp/agent/overlays/pin-model.yml`;
TS
cat >node-script <<'NODE'
#!/usr/bin/env node
const PIN = `${homedir()}/.omp/agent/overlays/pin-model.yml`;
NODE
printf 'cmd $x\n' >bare-name
cp template.ts template.before
cp node-script node-script.before
cp bare-name bare-name.before
cat >fixable.sh <<'FIXABLE'
#!/usr/bin/env bash
chmod +x $1
FIXABLE
cp fixable.sh fixable.before

for refused in template.ts node-script bare-name "fixable.sh template.ts"; do
	# shellcheck disable=SC2086 # the loop value is a word list on purpose
	if "${fixer}" ${refused} 2>refusal.txt; then
		fail "must refuse a non-shell file: ${refused}"
	fi
	grep -q 'not a shell file' refusal.txt || fail "the refusal must say why: ${refused}"
done
cmp -s template.ts template.before || fail "a TypeScript file must stay byte-identical"
cmp -s node-script node-script.before || fail "a node script must stay byte-identical"
cmp -s bare-name bare-name.before || fail "a file with no shell marker must stay byte-identical"
cmp -s fixable.sh fixable.before || fail "a shell file named beside a refused file must stay untouched"

# hk must not select a source file for the fixer in the first place: the plan is
# what the commit hook will run.
plan_repo="${work}/plan"
mkdir "${plan_repo}"
cd "${plan_repo}"
git init -q
cp "${out}/hk/hk.pkl" hk.pkl
cp "${work}/template.ts" template.ts
cp "${work}/node-script" node-script
cp "${work}/fixable.before" fixable.sh
cp "${work}/sample.sh" sample.sh
git add -A
plan="$(hk run pre-commit --staged --plan 2>&1)" || fail "hk plan failed: ${plan}"
grep -Eq '✓ shellcheck-fix +\(2 files matched\)' <<<"${plan}" ||
	fail "shellcheck-fix must match the two shell files only: $(grep 'shellcheck-fix' <<<"${plan}")"
cmp -s template.ts "${work}/template.before" || fail "planning must not rewrite a staged file"
cd "${work}"
echo "shellcheck-fix fixture ok"
