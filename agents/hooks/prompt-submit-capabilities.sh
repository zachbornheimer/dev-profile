#!/usr/bin/env bash
# UserPromptSubmit hook: runs the identify_intent, select_project and suggest_skills_tools_and_mcp capabilities.
# It returns intent/project text followed by the skill capability's XML context, so the agent receives
# each selected skill's path and description. A repeat of the same suggestions in one session (or a block
# over the size cap) is emitted as a names-only pointer instead of the full block. The per-session
# skill-picks JSON is a fallback, not the injection path.
# Prompt-level questions and the scripts they start live in prompt-respond.py, not here.
# The capability runtime calls model APIs or the local proxy; this hook never starts a harness session.
# Each capability declares the access it needs (tools, mcp, hooks) in its definition; the runtime grants only that.
#
# stdin:  the harness hook payload (UserPromptSubmit JSON: prompt, session_id, cwd)
# stdout: one hookSpecificOutput JSON with intent/project context followed by the raw skill XML, or nothing
# A hook must never block a prompt: every failure prints nothing and exits 0.
#
#   prompt-submit-capabilities.sh              run as a hook
#   prompt-submit-capabilities.sh --self-test  run on a fixed prompt, assert the output shape and that no
#                                              harness or MCP child process appeared; prints "ok"
set -uo pipefail

readonly KEYS_FILE="$HOME/.cache/ai/keys.env"
readonly NESTED_RUN_GUARD="$HOME/.agents/hooks/nested-run-guard.sh"
readonly SKILL_PICKS_DIR="$HOME/.agents/hooks/state/skill-picks"
readonly SUGGEST_STATE_DIR="$HOME/.agents/hooks/state/suggest-context"
readonly CAPABILITY_BIN_DIR="$HOME/.local/share/aube/bin"
readonly CAPABILITY_WALL_SECONDS=20
readonly MODEL_TIMEOUT_MS=15000
readonly PROMPT_MAX_CHARS=4000
readonly SUGGEST_CAP_CHARS=8192
readonly MAX_INTENT_PARTS=3
readonly SELF_TEST_PROMPT="fix the flaky test in the cache module"
readonly SELF_TEST_POLL_SECONDS=0.1
readonly SELF_TEST_WALL_SECONDS=$((CAPABILITY_WALL_SECONDS + 10))
# Commands that mean a harness session or an MCP gateway started under the hook.
readonly FORBIDDEN_CHILD_PATTERN='(^|/| )(grok|claude --print|claude -p|codex exec|docker mcp|chrome-devtools)'
readonly SELF="${BASH_SOURCE[0]}"

# --- payload ---------------------------------------------------------------------------------------------

# The prompt text of a payload, or nothing for empty and machine-sent (tag-wrapped) prompts.
prompt_of() {
	jq -r '
    [.prompt, .user_prompt, .text, .message | select(type == "string" and test("\\S"))] | first // empty
    | select(test("\\A\\s*<([A-Za-z][\\w:.-]*)(\\s[^>]*)?>.*</\\1>\\s*\\Z"; "s") | not)
    | .[0:'"$PROMPT_MAX_CHARS"']' 2>/dev/null
}

# --- capability calls ------------------------------------------------------------------------------------

# run_capability <outfile> <cwd> <name> <--input|--text> <value>: bounded, quiet, never fails the hook.
run_capability() {
	local out="$1" cwd="$2" name="$3" flag="$4" value="$5" freshness="${6:-yes}"
	(
		cd "$cwd" 2>/dev/null || cd "$HOME" || exit 0
		# AGENTMUX_NESTED_RUN marks everything below as nested, so no hook it reaches runs this one again.
		if [[ "$freshness" == yes && -n "${PROMPT_SUBMIT_FRESH:-}" ]]; then
			AGENTMUX_NESTED_RUN=1 AGENTMUX_MODEL_TIMEOUT_MS="$MODEL_TIMEOUT_MS" \
				timeout "$CAPABILITY_WALL_SECONDS" capability run "$name" --fresh "$flag" "$value" \
				>"$out" 2>/dev/null
		else
			AGENTMUX_NESTED_RUN=1 AGENTMUX_MODEL_TIMEOUT_MS="$MODEL_TIMEOUT_MS" \
				timeout "$CAPABILITY_WALL_SECONDS" capability run "$name" "$flag" "$value" \
				>"$out" 2>/dev/null
		fi
	) || : >"$out"
}

run_all() {
	local prompt="$1" cwd="$2" dir="$3" xml_input
	# One suggest call: its XML carries every skill path, so the pick file is derived from it. The earlier
	# JSON-then-cached-XML pair spent a second process start (about 2.7 s, serial) to re-read the same result.
	xml_input="$(jq -nc --arg t "$prompt" '{text: $t, output: "xml"}')"
	run_capability "$dir/intent.json" "$cwd" identify_intent --input "$(jq -nc --arg t "$prompt" '{text: $t}')" &
	run_capability "$dir/project.json" "$cwd" select_project --text "$prompt" &
	run_capability "$dir/skills.xml" "$cwd" suggest_skills_tools_and_mcp --input "$xml_input" &
	wait
}

# --- the three lines -------------------------------------------------------------------------------------

intent_line() {
	jq -r '
    [.output.Parts[]? | "\(.Type.Value)/\(.Intent.Value)"] | unique | .[0:'"$MAX_INTENT_PARTS"']
    | select(length > 0) | "Intent: " + join("; ")' "$1" 2>/dev/null
}

project_line() {
	jq -r '
    .output | select(.Probabilities != null)
    | (if .NeedsNewProject then "new" else .ProjectName end) as $name
    | ((.Probabilities[$name] // 0) * 100 | round / 100) as $probability
    | "Project: \($name) (p=\($probability))"' "$1" 2>/dev/null
}


# Where the skill files are, for AGENTS.md's "read skill-picks/<session_id>.json" fallback. Read from the skill
# XML; a prompt whose suggestion call failed leaves no file rather than the previous prompt's picks.
write_skill_pick() {
	local session="$1" file="$2" pick
	[[ -n "$session" ]] || return 0
	pick="$SKILL_PICKS_DIR/$session.json"
	mkdir -p "$SKILL_PICKS_DIR" 2>/dev/null || return 0
	rm -f "$pick"
	[[ "$(head -c 15 "$file" 2>/dev/null)" == '<system-context' ]] || return 0
	python3 - "$file" >"$pick" 2>/dev/null <<'PY' || rm -f "$pick"
import json
import sys
import xml.etree.ElementTree as ET

skills = ET.parse(sys.argv[1]).getroot().findall("./resources/skills/skill")
names = [skill.findtext("name", "") for skill in skills]
paths = [path for path in (skill.findtext("path", "") for skill in skills) if path]
print(json.dumps({"source": "capability", "choice": names[0] if names else "none", "load": names, "paths": paths},
                 ensure_ascii=False, separators=(",", ":")))
PY
}

# The fingerprint of the suggestion set last emitted whole for this session, or empty when none was.
last_suggest_hash() {
	local session="$1"
	[[ -n "$session" ]] || return 0
	cat "$SUGGEST_STATE_DIR/$session" 2>/dev/null || :
}

# The fingerprint of the suggestion SET in skills.xml: names and descriptions per kind, in order,
# without the model's confidences, which jitter run to run. Equal fingerprints mean the same advice.
suggest_fingerprint() {
	python3 - "$1" 2>/dev/null <<'PY'
import hashlib
import sys
import xml.etree.ElementTree as ET

root = ET.parse(sys.argv[1]).getroot()

def entries_of(section, child):
    return [(node.findtext("name", ""), node.findtext("description", "")) for node in root.findall(f"./resources/{section}/{child}")]

canon = "".join(
    f"{section}\0" + "\0".join(f"{name}\x1f{description}" for name, description in entries)
    for section, entries in (
        ("skills", entries_of("skills", "skill")),
        ("tools", entries_of("tools", "tool")),
        ("mcp-tools", entries_of("mcp-tools", "tool")),
    )
)
print(hashlib.sha256(canon.encode()).hexdigest())
PY
}

# The names-only pointer for skills.xml: the same <system-context> shape, one name list per kind,
# no per-item prose. Printed only when at least one suggestion exists.
suggest_pointer() {
	python3 - "$1" 2>/dev/null <<'PY'
import sys
import xml.etree.ElementTree as ET

root = ET.parse(sys.argv[1]).getroot()

def names_of(section, child):
    return [node.findtext("name", "") for node in root.findall(f"./resources/{section}/{child}") if node.findtext("name", "")]

skills = names_of("skills", "skill")
tools = names_of("tools", "tool")
mcps = names_of("mcp-tools", "tool")
if not skills and not tools and not mcps:
    sys.exit(1)

def line(tag, names):
    return f"    <{tag}>{', '.join(names)}</{tag}>" if names else f"    <{tag} />"

print("\n".join([
    "<system-context",
    '  source="suggest_skills_tools_and_mcp"',
    '  origin="runtime"',
    '  mode="pointer"',
    ">",
    "  <description>",
    "This context was automatically injected by the agent runtime",
    "after the user's message. It was not authored by the user.",
    "",
    "The full suggestions were already injected this session (or exceed the",
    "size cap), so only their names repeat here.",
    "Open a suggested skill with read_skill (pass the bare name), or search",
    "for more with find_skills — never construct file paths from a suggestion.",
    "Load a suggested tool with search_tools (pass its name), then call it.",
    "  </description>",
    "  <resources>",
    line("skills", skills),
    line("tools", tools),
    line("mcp-tools", mcps),
    "  </resources>",
    "</system-context>",
]))
PY
}

emit_context() {
	local dir="$1" session="$2" lines="" line xml pointer=""
	for line in "$(intent_line "$dir/intent.json")" "$(project_line "$dir/project.json")"; do
		[[ -n "$line" ]] && lines+="${lines:+$'\n'}$line"
	done
	xml="$(cat "$dir/skills.xml" 2>/dev/null)"
	if [[ "$xml" == '<system-context'* ]]; then
		local hash prior
		hash="$(suggest_fingerprint "$dir/skills.xml")"
		prior="$(last_suggest_hash "$session")"
		if [[ -n "$hash" && ("$prior" == "$hash" || ${#xml} -gt $SUGGEST_CAP_CHARS) ]]; then
			pointer="$(suggest_pointer "$dir/skills.xml")"
		fi
		if [[ -n "$pointer" ]]; then
			lines+="${lines:+$'\n'}$pointer"
		else
			lines+="${lines:+$'\n'}$xml"
			if [[ -n "$session" && -n "$hash" ]]; then
				mkdir -p "$SUGGEST_STATE_DIR" 2>/dev/null || :
				printf '%s' "$hash" >"$SUGGEST_STATE_DIR/$session" 2>/dev/null || :
			fi
		fi
	fi
	[[ -n "$lines" ]] || return 0
	jq -nc --arg context "$lines" \
		'{hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext: $context}}'
}

# --- the hook --------------------------------------------------------------------------------------------

run_hook() {
	command -v jq >/dev/null && command -v capability >/dev/null || return 0
	local payload prompt cwd session dir
	payload="$(cat)"
	prompt="$(prompt_of <<<"$payload")"
	[[ -n "$prompt" ]] || return 0
	cwd="$(jq -r '.cwd // .CWD // empty' <<<"$payload" 2>/dev/null)"
	session="$(jq -r '.session_id // .sessionId // empty' <<<"$payload" 2>/dev/null)"
	# shellcheck source=/dev/null
	[[ -f "$KEYS_FILE" ]] && {
		set -a
		source "$KEYS_FILE"
		set +a
	}
	dir="$(mktemp -d)" || return 0
	run_all "$prompt" "${cwd:-$HOME}" "$dir"
	write_skill_pick "$session" "$dir/skills.xml"
	emit_context "$dir" "$session"
	rm -rf "$dir"
}

# --- self-test -------------------------------------------------------------------------------------------

# Commands of every descendant of <pid>, one per line. Empty when `ps` cannot run.
descendant_commands() {
	ps -axo pid=,ppid=,command= 2>/dev/null | awk -v root="$1" '
    { pid = $1; parent[pid] = $2; $1 = ""; $2 = ""; command[pid] = substr($0, 3) }
    END {
      for (pid in parent) {
        for (at = parent[pid]; at != "" && at != 0 && at != 1; at = parent[at]) {
          if (at == root) { print command[pid]; break }
        }
      }
    }'
}

# Executables named like a harness or MCP launcher that only record the call and fail. Anything the hook starts by
# name lands here even where `ps` is not permitted (a sandbox).
write_canaries() {
	local dir="$1" name
	for name in grok claude codex docker chrome-devtools; do
		printf '#!/bin/sh\necho "%s $*" >>"%s/called"\nexit 1\n' "$name" "$dir" >"$dir/$name"
		chmod +x "$dir/$name"
	done
}

# Prints the hook's output on stdout; the harness or MCP commands seen under it go to <dir>/forbidden.
observe_hook() {
	local dir="$1" payload="$2" pid started
	PATH="$dir:$PATH" PROMPT_SUBMIT_FRESH=1 env -u AGENTMUX_NESTED_RUN "$SELF" --skip-guard <<<"$payload" \
		>"$dir/output" &
	pid=$!
	started=$SECONDS
	while kill -0 "$pid" 2>/dev/null; do
		descendant_commands "$pid" | grep -E "$FORBIDDEN_CHILD_PATTERN" >>"$dir/forbidden" || true
		if ((SECONDS - started > SELF_TEST_WALL_SECONDS)); then
			kill "$pid" 2>/dev/null
			break
		fi
		sleep "$SELF_TEST_POLL_SECONDS"
	done
	wait "$pid" 2>/dev/null
}

# The hook JSON: the intent line first, then the capability's complete XML as the last block. The project line
# depends on the host's atask registry, so a missing one is reported by the caller, not failed here.
has_hook_shape() {
	jq -e '
    .hookSpecificOutput.hookEventName == "UserPromptSubmit"
    and (.hookSpecificOutput.additionalContext as $c
         | ($c | startswith("Intent: "))
           and ($c | contains("<system-context"))
           and ($c | rtrimstr("\n") | endswith("</system-context>")))' "$1" >/dev/null 2>&1
}

self_test() {
	command -v jq >/dev/null || {
		echo "self-test: jq is missing" >&2
		return 1
	}
	local dir payload verdict=0
	dir="$(mktemp -d)" || return 1
	write_canaries "$dir"
	payload="$(jq -nc --arg p "$SELF_TEST_PROMPT" --arg c "$PWD" '{prompt: $p, cwd: $c, session_id: ""}')"
	ps -p $$ >/dev/null 2>&1 || echo "self-test: note: ps is not permitted here; checking launcher canaries only" >&2
	observe_hook "$dir" "$payload"
	if [[ -s "$dir/called" || -s "$dir/forbidden" ]]; then
		echo "self-test: a harness or MCP process ran under the hook:" >&2
		cat "$dir/called" "$dir/forbidden" >&2 2>/dev/null
		verdict=1
	elif ! has_hook_shape "$dir/output"; then
		echo "self-test: output is not the hook shape (Intent line first, XML block last):" >&2
		cat "$dir/output" >&2
		verdict=1
	else
		jq -r '.hookSpecificOutput.additionalContext | split("<system-context")[0] | gsub("\\n$"; "")' "$dir/output" |
			sed 's/^/self-test: preceding context: /' >&2
		echo "self-test: XML context is the final block" >&2
		echo ok
	fi
	rm -rf "$dir"
	return "$verdict"
}

# --- entry -----------------------------------------------------------------------------------------------

main() {
	if [[ "${1:-}" == "--self-test" ]]; then
		self_test
		return
	fi
	case "${1:-}" in
	--skip-guard) ;;
	*) [[ -z "${AGENTMUX_NESTED_RUN:-}" ]] && "$NESTED_RUN_GUARD" || return 0 ;;
	esac
	export PATH="$CAPABILITY_BIN_DIR:$PATH"
	run_hook
}

if [[ "${1:-}" == "--self-test" ]]; then
	main "$@"
	exit $?
fi
main "$@" || true
exit 0
