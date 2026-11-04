#!/usr/bin/env bash
# dev-profile-php-fmt hands phpcbf a temp copy of stdin and must give dprint the
# fixed bytes back on stdout. A standard's <arg name="basepath"> moves the file
# phpcbf writes whenever that file sits outside the basepath:
# Common::stripBasepath drops the path's leading separator and Reports/Cbf
# re-prepends the basepath, so the temp copy — outside every repo — is written
# inside the basepath tree and the write dies. The hk dprint step then fails a
# commit holding a .php file that needed a fix, with
# "file_put_contents(<repo>/private/var/...): Failed to open stream".
# phpcbf must rewrite the file it was given: the fix passes an explicit empty
# --basepath= so no standard can move the write.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scratch="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${scratch}"' EXIT

fail() {
	echo "FAIL: $*" >&2
	exit 1
}

command -v phpcbf >/dev/null 2>&1 || {
	echo "SKIP: phpcbf is not installed" >&2
	exit 0
}

# The repo shape that tripped: WordPress-marked, standard sets basepath.
mkdir -p "${scratch}/site/wp-content/plugins"
cat >"${scratch}/site/phpcs.xml.dist" <<'XML'
<?xml version="1.0"?>
<ruleset name="fixture">
	<description>basepath fixture standard</description>
	<arg name="basepath" value="./"/>
	<rule ref="Generic.Files.EndFileNewline"/>
</ruleset>
XML

# Needs the fix (no newline at EOF), so phpcbf must write the file it formatted.
printf '<?php\necho 1;' >"${scratch}/site/wp-content/plugins/plugin.php"
printf '<?php\necho 1;\n' >"${scratch}/want.php"

# The hk dprint step runs from the repo root, so basepath resolves there.
cd "${scratch}/site"
code=0
"${repo}/bin/dev-profile-php-fmt" --stdin-path "${scratch}/site/wp-content/plugins/plugin.php" \
	<"${scratch}/site/wp-content/plugins/plugin.php" >"${scratch}/got.php" 2>/dev/null || code=$?

[[ "${code}" -eq 0 ]] || fail "the stdin format exited ${code}: phpcbf could not write the temp copy it fixed"
cmp -s "${scratch}/want.php" "${scratch}/got.php" || fail "stdout must carry the fix phpcbf made, got: $(cat "${scratch}/got.php")"
[[ ! -e "${scratch}/site/private" ]] || fail "phpcbf wrote into the basepath tree instead of the temp copy"

echo "ok php-fmt-basepath"
