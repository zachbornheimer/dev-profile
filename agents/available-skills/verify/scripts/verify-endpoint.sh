#!/usr/bin/env bash
# Assert an HTTP endpoint returns the expected status and body.
# Usage: ./verify-endpoint.sh <url> <expected-status> [fixture-file]
#
# Examples:
#   ./verify-endpoint.sh http://localhost:8080/v1/health 200
#   ./verify-endpoint.sh http://localhost:8080/v1/quote 200 fixtures/john-doe-response.json

set -euo pipefail

TIMEOUT="${VERIFY_TIMEOUT_SECS:-10}"

url="${1:?Usage: verify-endpoint.sh <url> <expected-status> [fixture-file]}"
expected_status="${2:?Usage: verify-endpoint.sh <url> <expected-status> [fixture-file]}"
fixture="${3:-}"

actual_status=$(curl -s -o /tmp/verify-endpoint-body.json -w "%{http_code}" \
  --max-time "$TIMEOUT" "$url")

if [[ $actual_status != "$expected_status" ]]; then
  echo "FAIL: expected HTTP $expected_status, got $actual_status" >&2
  echo "Response body:" >&2
  cat /tmp/verify-endpoint-body.json >&2
  exit 1
fi

if [[ -n $fixture ]]; then
  if ! diff <(jq -S . "$fixture") <(jq -S . /tmp/verify-endpoint-body.json) >/tmp/verify-diff.txt 2>&1; then
    echo "FAIL: response body does not match fixture $fixture" >&2
    cat /tmp/verify-diff.txt >&2
    exit 1
  fi
fi

echo "PASS: $url → $actual_status${fixture:+ (body matches $fixture)}"
