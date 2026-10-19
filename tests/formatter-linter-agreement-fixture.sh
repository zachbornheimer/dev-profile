#!/usr/bin/env bash
# The formatter and the linters never disagree: messy markdown and YAML, once
# formatted by the generated dprint config, pass the generated markdownlint and
# yamllint configs with no finding. A content problem (a fence without a
# language, a duplicate key) must still fail, so the layout rules are off
# without the content rules going with them.
# Usage: formatter-linter-agreement-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: formatter-linter-agreement-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

fail() {
	echo "FAIL formatter-linter-agreement fixture: $*" >&2
	[[ ! -f "${work}/output.txt" ]] || sed 's/^/  | /' "${work}/output.txt" >&2
	exit 1
}

# Layout mess only: every finding after dprint is a formatter/linter disagreement.
cat >"${work}/messy.md" <<'EOF'
Title
=====

Sub
---

* item one
   * nested three spaces
        * nested deep
* item two
+ plus list one
+ plus list two

1) first
2) second
   - mixed child

|a|b|c|
|-|:-:|--:|
|short|a much longer cell here|`x`|
|  spaced  | \| escaped | z |

| Name | Value |
|---|---|
| a | 1 |

Some *emphasis* and __strong__ text with trailing spaces
and a hard break.

```yaml
a:   {x: 1}
```

> quote
continued lazily

-----

***



Final paragraph
EOF

cat >"${work}/messy.yaml" <<'EOF'
a: {x: 1, y: 2}
b: [1,2,3]
c: {   }
d: [ ]
g:
- one
-   three
h:
    nested:
          deep: true
    list:
        - a
        - b:   1
          c:   2
i: {a: [1, 2], b: {c: d}}
j: [ {a: 1}, {b: 2} ]
k :   value   # comment
t: [a,
  b,
  c]
u: {a: 1,
  b: 2}



end: 'single'
EOF

# Controls: real content problems that must still fail after formatting.
cat >"${work}/control.md" <<'EOF'
# Control

```
no language
```
EOF
printf 'a: 1\na: 2\n' >"${work}/control.yaml"

format() {
	local file
	for file in "$@"; do cp "${file}" "${file}.orig"; done
	dprint fmt --config "${out}/dprint.jsonc" "$@" >"${work}/output.txt" 2>&1 || fail "dprint could not format the samples"
	for file in "$@"; do
		if cmp -s "${file}" "${file}.orig"; then fail "dprint left ${file##*/} unchanged, so the sample proves nothing"; fi
	done
}
format "${work}/messy.md" "${work}/messy.yaml"
dprint fmt --config "${out}/dprint.jsonc" "${work}/control.md" "${work}/control.yaml" >"${work}/output.txt" 2>&1 || fail "dprint could not format the controls"

lint_markdown() { markdownlint --config "${out}/markdownlintrc.json" "$@" >"${work}/output.txt" 2>&1; }
lint_yaml() { yamllint --strict --config-file "${out}/yamllint.yaml" --format parsable "$@" >"${work}/output.txt" 2>&1; }

disagreements=0
lint_markdown "${work}/messy.md" || {
	echo "markdownlint rejects dprint-formatted markdown:" >&2
	sed 's/^/  | /' "${work}/output.txt" >&2
	disagreements=1
}
lint_yaml "${work}/messy.yaml" || {
	echo "yamllint rejects dprint-formatted YAML:" >&2
	sed 's/^/  | /' "${work}/output.txt" >&2
	disagreements=1
}
rm -f "${work}/output.txt"
[[ "${disagreements}" -eq 0 ]] || fail "the formatter and a linter disagree"

if lint_markdown "${work}/control.md"; then fail "markdownlint must still flag a fence without a language"; fi
grep -Fq "MD040" "${work}/output.txt" || fail "the markdown control must fail on MD040"
if lint_yaml "${work}/control.yaml"; then fail "yamllint must still flag a duplicate key"; fi
grep -Fq "key-duplicates" "${work}/output.txt" || fail "the YAML control must fail on key-duplicates"

echo "formatter-linter-agreement fixture ok"
