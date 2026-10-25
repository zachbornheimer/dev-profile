#!/usr/bin/env bash
# Write AOE instance status (running|idle|waiting). No-op if AOE is unset.
# Optional second arg: from-stdin — waiting if stdin JSON names AskUserQuestion.
set -eu
unset IFS
set -f
umask 077

STATUS="${1:-}"
FROM_STDIN="${2:-}"
case "${STATUS}" in
running | idle | waiting) ;;
*) exit 0 ;;
esac

IID=$(printenv AOE_INSTANCE_ID 2>/dev/null || true)
[ -n "${IID}" ] || exit 0
case "${IID}" in
*[!0-9a-zA-Z_-]*) exit 0 ;;
esac

B=/tmp/aoe-hooks-503
mkdir -p "${B}" 2>/dev/null || exit 0
LS=$(LC_ALL=C ls -ldn "${B}" 2>/dev/null) || exit 0
# shellcheck disable=SC2086
set -- ${LS}
M="${1}"
case "${M}" in
drwx------ | drwx------. | drwx------+ | drwx------@) ;;
*) exit 0 ;;
esac
ME=$(id -u 2>/dev/null) || exit 0
[ "${3}" = "${ME}" ] || exit 0
D="${B}/${IID}"
mkdir -p "${D}" 2>/dev/null
LS=$(LC_ALL=C ls -ldn "${D}" 2>/dev/null) || exit 0
# shellcheck disable=SC2086
set -- ${LS}
M="${1}"
case "${M}" in
drwx------ | drwx------. | drwx------+ | drwx------@) ;;
*) exit 0 ;;
esac
[ "${3}" = "${ME}" ] || exit 0

S="${STATUS}"
if [ "${STATUS}" = running ] && [ "${FROM_STDIN}" = from-stdin ]; then
	IN=$(cat 2>/dev/null || true)
	S=running
	case "${IN}" in
	*'"tool_name":"AskUserQuestion"'*) S=waiting ;;
	esac
fi
printf '%s' "${S}" >"${D}/status" 2>/dev/null
exit 0
