ai() {
	emulate -L zsh
	umask 077

	# Validate the prompt and dependencies.
	if (($# == 0)); then
		__ -t failed 'Usage: ai "your prompt"'
		return 2
	fi

	for command in herdr omp jq; do
		if ! whence -p "$command" >/dev/null; then
			__ -t failed "ai: missing dependency: $command"
			return 1
		fi
	done

	# Store the prompt securely, avoiding shell interpolation.
	local dir response pane
	dir=$(mktemp -d /tmp/ai.XXXXXXXX) || return 1

	if ! printf '%s' "$*" >"$dir/prompt"; then
		rm -rf -- "$dir"
		return 1
	fi

	# Create the runner executed inside Herdr.
	if ! cat >"$dir/run" <<'SH'; then
#!/bin/sh

dir=${0%/*}
status=0

# Run OMP interactively with automatic exit enabled.
if prompt=$(cat "$dir/prompt"); then
  rm -f "$dir/prompt"

  OMP_ONE_SHOT=1 omp \
    --model @default \
    --no-session \
    --no-title \
    -- "$prompt" || status=$?
else
  status=1
fi

# Notify Kitty through Herdr.
if [ "$status" -eq 0 ]; then
  title="AI completed"
  sound="done"
else
  title="AI failed"
  sound="request"
fi

herdr --session one-shots notification show \
  "$title" \
  --body "Project: ${PWD##*/} (exit $status)" \
  --sound "$sound" >/dev/null 2>&1 || :

# Remove temporary files.
rm -f "$dir/prompt" "$dir/run"
rmdir "$dir" 2>/dev/null || :

# Close this exact pane, not whichever pane is focused.
if [ -n "${HERDR_PANE_ID:-}" ]; then
  herdr --session one-shots pane close \
    "$HERDR_PANE_ID" >/dev/null 2>&1 ||
    printf 'ai: could not close pane\n' >&2
fi

exit "$status"
SH

		rm -rf -- "$dir"
		return 1
	fi

	# Create a new workspace in the one-shots session.
	response=$(herdr --session one-shots workspace create \
		--cwd "$PWD" \
		--label "ai: ${PWD:t}" \
		--focus) || {
		rm -rf -- "$dir"
		return 1
	}

	# Extract the newly created pane ID.
	pane=$(jq -er '.result.root_pane.pane_id' <<<"$response") || {
		rm -rf -- "$dir"
		return 1
	}

	# Launch the runner in the new pane.
	if ! herdr --session one-shots pane run \
		"$pane" "sh $dir/run"; then
		herdr --session one-shots pane close \
			"$pane" >/dev/null 2>&1 || :
		rm -rf -- "$dir"
		return 1
	fi
}
