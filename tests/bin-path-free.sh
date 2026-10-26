#!/usr/bin/env bash
# dprint and hk run the profile's bin scripts by absolute path, with a PATH that
# does not include the bin directory. A script that calls a sibling by bare name
# then dies with "command not found" (exit 127). Run each sibling-calling script
# the way dprint does and require it to work.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scratch="$(mktemp -d)"
trap 'rm -rf "${scratch}"' EXIT

# A bare PATH: no profile bin, no mise shims, so the formatter falls back to
# passing the file through unchanged.
bare="/usr/bin:/bin"
src=$'<?php\necho 1;\n'
mkdir -p "${scratch}/Downloads"

out="$(printf '%s' "${src}" | env -i HOME="${scratch}" PATH="${bare}" \
	"${repo}/bin/dev-profile-php-fmt" --stdin-path "${scratch}/Downloads/test.php")" || {

	echo "FAIL: dev-profile-php-fmt exited $? with PATH=${bare}" >&2
	exit 1
}
if [[ "${out}"$'\n' != "${src}" ]]; then
	echo "FAIL: dev-profile-php-fmt changed or lost the input" >&2
	exit 1
fi

# Through a symlinked bin dir, as deployed at ~/.local/share/dev-profile/bin.
ln -s "${repo}/bin" "${scratch}/bin"
printf '%s' "${src}" | env -i HOME="${scratch}" PATH="${bare}" \
	"${scratch}/bin/dev-profile-php-fmt" --stdin-path "${scratch}/Downloads/test.php" >/dev/null || {
	echo "FAIL: dev-profile-php-fmt via a linked bin dir" >&2
	exit 1
}

echo "ok bin-path-free"
