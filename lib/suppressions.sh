#!/usr/bin/env bash
set -euo pipefail
# Edit lib/suppressions.sh: `mise run generate` copies it into bin/ as dev-profile-suppressions.
# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/../lib/facts.sh"

# Find inline suppression directives. --tree: every tracked file (lint, doctor).
# --unpushed: lines added by commits not yet on a remote (pre-push).
# One scan per mode: the directives are joined into a single alternation, so the
# tree or diff is read once instead of once per directive. Only candidate lines
# reach the attribution pass, which decides the directive, the file scope and the
# declared exceptions.
mode="${1:?usage: dev-profile-suppressions --tree|--unpushed}"
policy="${PROFILE_SUPPRESSION_MODE:?}"
cd "$(git rev-parse --show-toplevel)"

work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT

# id|file extensions|ERE, one per line.
printf '%s\n' "${PROFILE_SUPPRESSION_DIRECTIVES:?}" >"${work}/directives"

# path|rule declared in profile.pkl suppressionExceptions.
printf '%s\n' "${PROFILE_SUPPRESSION_EXCEPTIONS?}" >"${work}/exceptions"

case "${mode}" in
--tree | --unpushed) ;;
*)
	echo "dev-profile-suppressions: unknown mode ${mode}" >&2
	exit 2
	;;
esac

# The profile's excluded directories, as git pathspecs (PROFILE_EXCLUDE: one per line).
excludes=()
while IFS= read -r dir; do
	excludes+=(":(exclude,glob)**/${dir}/**")
done <<<"${PROFILE_EXCLUDE:?}"

# Any of the directives, so the scan reads the tree or diff once: (re1)|(re2)|...
combined="$(
	awk '{
    line = $0
    sub(/^[^|]*\|[^|]*\|/, "", line)
    printf "%s(%s)", (NR > 1 ? "|" : ""), line
  }' "${work}/directives"
)"

# Lines "path:..." matching any directive, in the mode's own format.
if [[ "${mode}" == --tree ]]; then
	matched="$(git grep -nIE -e "${combined}" -- . "${excludes[@]}" || true)"
else
	matched="$(
		git log -p --format= --unified=0 --no-color --branches --not --remotes |
			awk 'index($0, "+++ b/") == 1 { file = substr($0, 7); next }
        index($0, "+") == 1 && index($0, "+++") != 1 { print file ":" substr($0, 2) }' |
			grep -E -e "${combined}" || true
	)"
fi

if [[ -z "${matched}" ]]; then
	exit 0
fi

# Attribute each candidate: path in the directive's file scope, not an exception,
# text matching the directive's own ERE. Prints "hit  [id]" exactly as reported.
reported="$(
	awk -v directives="${work}/directives" -v exceptions="${work}/exceptions" '
    BEGIN {
      n = 0
      while ((getline line < directives) > 0) {
        if (line == "") continue
        i = index(line, "|")
        id = substr(line, 1, i - 1)
        rest = substr(line, i + 1)
        j = index(rest, "|")
        n++
        did[n] = id
        dexts[n] = substr(rest, 1, j - 1)
        dre[n] = substr(rest, j + 1)
      }
      while ((getline line < exceptions) > 0) if (line != "") except[line] = 1
    }
    {
      c = index($0, ":")
      if (c == 0) next
      path = substr($0, 1, c - 1)
      text = substr($0, c + 1)
      for (k = 1; k <= n; k++) {
        scope = 0
        m = split(dexts[k], ext, " ")
        for (e = 1; e <= m; e++) {
          x = ext[e]
          if (x != "" && length(path) > length(x) && substr(path, length(path) - length(x)) == "." x) {
            scope = 1
            break
          }
        }
        if (!scope) continue
        if ((path "|" did[k]) in except) continue
        if (text !~ dre[k]) continue
        print $0 "  [" did[k] "]"
      }
    }
  ' <<<"${matched}"
)"

if [[ -z "${reported}" ]]; then
	exit 0
fi

printf '%s
' "${reported}"
found="$(grep -c '' <<<"${reported}")"
if [[ "${policy}" == enforce ]]; then
	echo "${found} inline suppression(s). Fix the code, or declare {path, rule, ticket} in profile.pkl suppressionExceptions." >&2
	exit 1
fi
echo "report mode: ${found} inline suppression(s), not blocking. Set suppressionMode = 'enforce' in profile.pkl to block." >&2
