#!/usr/bin/env bash
# test-classify.sh — fixture-driven tests for tofu-safe-apply.sh's classifier.
# No tofu backend required: drives --classify-only against saved plan JSON.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly TARGET="${SCRIPT_DIR}/tofu-safe-apply.sh"
readonly FIXTURES="${SCRIPT_DIR}/fixtures"

pass_count=0
fail_count=0

expect_exit_and_output() {
	local description="$1"
	local fixture="$2"
	local expected_exit="$3"
	local expected_grep="$4"

	local output
	local actual_exit=0
	output=$("$TARGET" --classify-only "${FIXTURES}/${fixture}" 2>&1) || actual_exit=$?

	if [[ "$actual_exit" -ne "$expected_exit" ]]; then
		echo "FAIL: ${description} — expected exit ${expected_exit}, got ${actual_exit}"
		echo "--- output ---"
		echo "$output"
		fail_count=$((fail_count + 1))
		return
	fi

	if ! grep -q "$expected_grep" <<<"$output"; then
		echo "FAIL: ${description} — expected output to contain '${expected_grep}'"
		echo "--- output ---"
		echo "$output"
		fail_count=$((fail_count + 1))
		return
	fi

	echo "PASS: ${description}"
	pass_count=$((pass_count + 1))
}

expect_exit_and_output \
	"pure creates classify SAFE" \
	"pure-create.json" 0 "SAFE"

expect_exit_and_output \
	"in-place update classifies SAFE" \
	"in-place-update.json" 0 "SAFE"

expect_exit_and_output \
	"delete of aws_iam_role classifies UNSAFE and names the row" \
	"delete-iam-role.json" 1 "aws_iam_role.deploy"

expect_exit_and_output \
	"replace with create_before_destroy classifies SAFE" \
	"replace-create-before-destroy.json" 0 "SAFE"

expect_exit_and_output \
	"replace destroy-before-create classifies UNSAFE" \
	"replace-destroy-before-create.json" 1 "destroy-before-create"

echo ""
echo "${pass_count} passed, ${fail_count} failed"
[[ "$fail_count" -eq 0 ]]
