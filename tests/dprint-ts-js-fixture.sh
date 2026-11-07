#!/usr/bin/env bash
# dprint owns TypeScript and JavaScript: the profile config formats every JS/TS extension,
# and hk carries no second JS formatter step (oxlint is a linter and stays).
# Usage: dprint-ts-js-fixture.sh
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

fail() {
	echo "FAIL dprint-ts-js fixture: $*" >&2
	exit 1
}

grep -Fq '"npm:@dprint/typescript@' "${root}/config/dprint.jsonc" || fail "config/dprint.jsonc must carry @dprint/typescript"

messy_ts=$'const   a = {x:1,\n y:2}\nexport function f( a:number ,b:number ){return a+b}\n'
messy_js=$'var x   = 1;;\nmodule.exports = {a:x}\n'
messy_tsx=$'export const C = () => <div   className="x">{ 1+1 }</div>\n'
printf '%s' "${messy_ts}" >"${work}/a.ts"
printf '%s' "${messy_ts}" >"${work}/b.mts"
printf '%s' "${messy_ts}" >"${work}/b.cts"
printf '%s' "${messy_tsx}" >"${work}/c.tsx"
printf '%s' "${messy_tsx}" >"${work}/c.jsx"
printf '%s' "${messy_js}" >"${work}/d.js"
printf '%s' "${messy_js}" >"${work}/d.mjs"
printf '%s' "${messy_js}" >"${work}/d.cjs"

files=(a.ts b.mts b.cts c.tsx c.jsx d.js d.mjs d.cjs)
(cd "${work}" && dprint check --config "${root}/config/dprint.jsonc" "${files[@]}") >/dev/null 2>&1 &&
	fail "dprint check must report the messy JS/TS files as unformatted"
(cd "${work}" && dprint fmt --config "${root}/config/dprint.jsonc" "${files[@]}") >"${work}/out.txt" 2>&1 ||
	{
		sed 's/^/  | /' "${work}/out.txt" >&2
		fail "dprint fmt failed"
	}
(cd "${work}" && dprint check --config "${root}/config/dprint.jsonc" "${files[@]}") >/dev/null 2>&1 ||
	fail "files must be formatted after dprint fmt"
grep -Fxq 'const a = { x: 1, y: 2 };' "${work}/a.ts" || fail "a.ts was not formatted by dprint"
grep -Fxq 'module.exports = { a: x };' "${work}/d.js" || fail "d.js was not formatted by dprint"

# No other JS formatter step in hk: a second formatter on the same files would fight dprint.
if grep -Ev '^[[:space:]]*//' "${root}/hk/hk.pkl" | grep -Eiq 'oxfmt|biome|prettier|Builtins\.(prettier|biome|oxfmt)'; then
	fail "hk/hk.pkl must not carry an oxfmt, biome or prettier step"
fi

echo "dprint-ts-js fixture ok"
