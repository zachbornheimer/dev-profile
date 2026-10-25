#!/usr/bin/env bash
# Stop hook: blocks Claude from ending its turn until the test suite passes.
# Wire in settings.json:
#   {"hooks": {"Stop": [{"type": "command", "command": ".claude/hooks/check-tests.sh"}]}}
#
# Copy to .claude/hooks/check-tests.sh in the target repo and customize:
#   VERIFY_TEST_CMD      — override default runner (default: mise run test)
#   VERIFY_TIMEOUT_SECS  — hard timeout before treating as hung (default: 120)
#   VERIFY_SLOW_SECS     — warn threshold; spawns investigation agent (default: 30)

set -euo pipefail

# Guard against infinite loops when the hook itself triggers a stop
if [[ ${stop_hook_active:-} == "1" ]]; then
  exit 0
fi
export stop_hook_active=1

TEST_CMD="${VERIFY_TEST_CMD:-mise run test}"
TIMEOUT="${VERIFY_TIMEOUT_SECS:-120}"
SLOW_THRESHOLD="${VERIFY_SLOW_SECS:-30}"

start_ts=$(date +%s)

if output=$(timeout "$TIMEOUT" bash -c "$TEST_CMD" 2>&1); then
  elapsed=$(($(date +%s) - start_ts))

  if ((elapsed > SLOW_THRESHOLD)); then
    # Tests passed but took too long — record it for investigation.
    note="Test suite passed in ${elapsed}s (warn threshold: ${SLOW_THRESHOLD}s)."
    claude_md="./.claude/CLAUDE.md"
    if [[ -f $claude_md ]]; then
      if ! grep -q "slow-tests" "$claude_md"; then
        printf '\n## Slow tests (auto-detected)\n%s Investigate with: mise run test --verbose\n' "$note" >>"$claude_md"
      fi
    fi
    # Spawn an investigation agent in the background (non-blocking).
    # The agent will profile the suite and propose fixes or update CLAUDE.md.
    claude --print \
      "The test suite passed but took ${elapsed}s (threshold ${SLOW_THRESHOLD}s). \
Profile which tests are slow using the project's test runner. \
For each test over 5s: identify the root cause (real I/O, sleep, missing stub). \
Either fix the root cause or add a note to .claude/CLAUDE.md under '## Slow tests' \
with the test name, measured duration, and why it can't be faster. \
Do not weaken tests; do not add sleep workarounds." \
      >/tmp/slow-test-investigation.log 2>&1 &
  fi

  exit 0
else
  exit_code=$?
  if [[ $exit_code -eq 124 ]]; then
    printf '{"decision":"block","reason":"Test suite timed out after %ss. Hung test or missing teardown — investigate before ending turn."}' "$TIMEOUT"
  else
    last_lines=$(echo "$output" | tail -20)
    printf '{"decision":"block","reason":"Tests failed (exit %d). Fix before ending turn.\n\n%s"}' \
      "$exit_code" "$last_lines"
  fi
  exit 0
fi
