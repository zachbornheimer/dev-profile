#!/usr/bin/env bash
# dprint formats Swift by piping the file to dev-profile-swift-format.
# Apple swift-format 6 reads stdin from `-`, not `--stdin`. A parent
# `.swift-format` is not found from the file's directory, so the wrapper
# must pass it. Usage: swift-format-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: swift-format-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT
fmt="${out}/bin/dev-profile-swift-format"

fail() {
	echo "FAIL swift-format fixture: $*" >&2
	exit 1
}

# A swift-format that dies the way 604 does when given --stdin, and records argv.
cat >"${work}/swift-format" <<'EOF'
#!/bin/sh
printf '%s\n' "$@" >"${STUB_ARGS:?}"
for arg in "$@"; do
	if [ "$arg" = "--stdin" ]; then
		echo "Error: Unknown option '--stdin'" >&2
		exit 64
	fi
done
cat
EOF
chmod +x "${work}/swift-format"

# nicklockwood's swiftformat, recording argv and copying stdin.
cat >"${work}/swiftformat" <<'EOF'
#!/bin/sh
printf '%s\n' "$@" >"${STUB_ARGS:?}"
cat
EOF
chmod +x "${work}/swiftformat"

export STUB_ARGS="${work}/args"

# No path: dprint's current command. Must not pass --stdin.
printf 'struct  Foo{let x:Int}\n' | PATH="${work}:${PATH}" "${fmt}" >"${work}/out" 2>"${work}/err" ||
	fail "no-arg stdin failed: $(cat "${work}/err")"
grep -q 'Unknown option' "${work}/err" && fail "no-arg stdin passed --stdin"
cmp -s <(printf 'struct  Foo{let x:Int}\n') "${work}/out" || fail "no-arg stdin did not copy the file"
grep -qx -- '-' "${work}/args" || fail "no-arg stdin must pass - to swift-format"

# --stdin-path: dprint names the file so a parent .swift-format is used.
mkdir -p "${work}/repo/sub"
printf '%s\n' '{"version":1,"lineLength":20}' >"${work}/repo/.swift-format"
printf 'struct  Foo{let x:Int}\n' >"${work}/repo/sub/Foo.swift"
printf 'struct  Foo{let x:Int}\n' |
	PATH="${work}:${PATH}" "${fmt}" --stdin-path "${work}/repo/sub/Foo.swift" >"${work}/out" 2>"${work}/err" ||
	fail "stdin-path failed: $(cat "${work}/err")"
grep -qx -- '--configuration' "${work}/args" || fail "stdin-path must pass --configuration"
grep -qx -- "${work}/repo/.swift-format" "${work}/args" || fail "stdin-path must name the parent config"
grep -qx -- 'Foo.swift' "${work}/args" || fail "stdin-path must pass --assume-filename"
grep -qx -- '--stdin' "${work}/args" && fail "stdin-path must not pass --stdin"

# The other installed formatter, when Apple's is absent.
mkdir -p "${work}/nick"
cp "${work}/swiftformat" "${work}/nick/swiftformat"
printf 'struct  Foo{let x:Int}\n' |
	PATH="${work}/nick:/bin:/usr/bin" STUB_ARGS="${work}/args" "${fmt}" --stdin-path "${work}/repo/sub/Foo.swift" \
		>"${work}/out" 2>"${work}/err" ||
	fail "swiftformat stdin-path failed: $(cat "${work}/err")"
grep -qx -- 'stdin' "${work}/args" || fail "swiftformat stdin mode must be given stdin"
grep -qx -- '--stdin-path' "${work}/args" || fail "swiftformat must receive --stdin-path"

# Real Apple swift-format, when this machine has it: parent config is applied.
if [[ -x /opt/homebrew/bin/swift-format ]]; then
	printf 'struct  Foo{let x:Int}\n' |
		PATH="/opt/homebrew/bin:${PATH}" "${fmt}" --stdin-path "${work}/repo/sub/Foo.swift" \
			>"${work}/real.out" 2>"${work}/err" ||
		fail "real swift-format stdin-path failed: $(cat "${work}/err")"
	grep -q 'let x: Int' "${work}/real.out" || fail "real swift-format did not format stdin"
	# lineLength 20 wraps the property off the struct line.
	grep -q 'struct Foo {$' "${work}/real.out" || fail "real swift-format ignored the parent .swift-format"
fi

echo "swift-format fixture ok"
