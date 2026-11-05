#!/usr/bin/env bash
# UserPromptSubmit hook: runs the intent, project and suggestion capabilities.
# It returns the session's scope line, intent/project text and the suggester's XML context: at most 5 skills (name and
# one line) and 3 tool cards, 3,000 characters in all, so nothing here shortens or drops a block for size. The block's
# description tells the agent to reach skills via skill_search and tool_call({ address: "skill/<name>" }), tools via
# tool_search and tool_call({ address, args }). The same set repeated in one session is emitted as a names-only pointer.
# The per-session skill-picks JSON is a fallback, not the injection path.
# Frustration and dictation run in agent-hooks' question-pipeline policy (~/.config/agent-hooks/pipeline), not here.
# The capability runtime calls model APIs or the local proxy; this hook never starts a harness session.
# Each capability declares the access it needs (tools, mcp, hooks) in its definition; the runtime grants only that.
#
# stdin:  the harness hook payload (UserPromptSubmit JSON: prompt, session_id, cwd)
# stdout: one hookSpecificOutput JSON with the scope, intent and project lines followed by the skill XML
#         (tool suggestions as gateway tool_call cards), or nothing
# A hook must never block a prompt: every failure prints nothing and exits 0.
#
#   prompt-submit-capabilities.sh              run as a hook
#   prompt-submit-capabilities.sh --self-test  run the whole hook on a fixed prompt against stub capabilities (5 skills,
#                                              3 tool cards): assert the context shape, its size, its wording, the
#                                              repeat pointer and the unavailable notice, and that no harness or MCP
#                                              child process appeared; prints "ok". SELF_TEST_SHOW_CONTEXT=1 prints it.
set -uo pipefail

readonly KEYS_FILE="$HOME/.cache/ai/keys.env"
readonly NESTED_RUN_GUARD="$HOME/.agents/hooks/nested-run-guard.sh"
readonly SKILL_PICKS_DIR="$HOME/.agents/hooks/state/skill-picks"
readonly SUGGEST_STATE_DIR="$HOME/.agents/hooks/state/suggest-context"
# A session id names a state file; anything else (a `/`, a `..`) could reach outside the state directories.
readonly SESSION_ID_PATTERN='^[A-Za-z0-9][A-Za-z0-9_-]*$'
# The self-test points this at a directory holding a stub `capability`; nothing else sets it.
readonly CAPABILITY_BIN_DIR="${CAPABILITY_BIN_DIR:-$HOME/.local/share/aube/bin}"
readonly CAPABILITY_WALL_SECONDS=20
readonly MODEL_TIMEOUT_MS=15000
readonly PROMPT_MAX_CHARS=4000
readonly MAX_INTENT_PARTS=3
readonly SELF_TEST_PROMPT="fix the flaky test in the cache module"
readonly SELF_TEST_POLL_SECONDS=0.1
readonly SELF_TEST_WALL_SECONDS=$((CAPABILITY_WALL_SECONDS + 10))
readonly SELF_TEST_CONTEXT_MAX_CHARS=3500
readonly SELF_TEST_SKILLS=5
readonly SELF_TEST_TOOL_CARDS=3
# What the agent is told, word for word, about reaching skills and tools; and the tools it must no longer be sent to.
readonly -a SELF_TEST_REQUIRED_WORDING=(
	'skill_search'
	'tool_call({ address: "skill/<name>" })'
	'tool_search'
	'tool_call({ address, args })'
)
readonly SELF_TEST_RETIRED_WORDING='read_skill|find_skills|search_tools'
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

# The scope the MCP header carries for this session — omp writes `omp-<session_id>` into `x-scope` —
# beside the working directory it started in. Emitted on every prompt, outside the suggestion block,
# so a repeat or an over-cap block never erases it.
scope_line() {
	printf 'Scope: omp-%s · cwd: %s' "$1" "$2"
}

# Where the skill files are, for AGENTS.md's "read skill-picks/<session_id>.json" fallback. Read from the skill
# XML; a prompt whose suggestion call failed leaves no file rather than the previous prompt's picks.
# Reads SESSION_ID and RUN_DIR, which run_hook sets once per prompt.
write_skill_pick() {
	[[ "$SESSION_ID" =~ $SESSION_ID_PATTERN ]] || return 0
	local pick="$SKILL_PICKS_DIR/$SESSION_ID.json" skills_xml="$RUN_DIR/skills.xml"
	mkdir -p "$SKILL_PICKS_DIR" 2>/dev/null || return 0
	rm -f "$pick"
	[[ "$(head -c 15 2>/dev/null <"$skills_xml")" == '<system-context' ]] || return 0
	python3 - "$skills_xml" >"$pick" 2>/dev/null <<'PY' || rm -f "$pick"
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

# The fingerprint of the suggestion set last emitted whole for this session (SESSION_ID), or empty when none was.
last_suggest_hash() {
	[[ "$SESSION_ID" =~ $SESSION_ID_PATTERN ]] || return 0
	cat 2>/dev/null <"$SUGGEST_STATE_DIR/$SESSION_ID" || :
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

# skills.xml as the injection block (mode `block`) or its names-only pointer (mode `pointer`). The suggester bounds
# the block (at most 5 skills and 3 tool cards, 3,000 characters), so neither mode shortens anything. Skills stay as
# the capability wrote them. A tool arrives as a gateway address (`capability/memory_search`) with its complete
# card in <how-to-call> (name, description, input, example call, returns, flags); it renders as that card, at most
# MAX_TOOL_CARDS of them, best confidence first, and the pointer names the same kept tools. A tool with no card
# cannot be called from the suggestion, so it is dropped. The block's description and the unavailable notice are this
# hook's own text, so how the agent is told to reach skills and tools never depends on the capability build. The
# pointer prints nothing (exit 1) when no skill and no kept tool is left.
suggest_render() {
	python3 - "$1" "$2" 2>/dev/null <<'PY'
import re
import sys
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

mode, path = sys.argv[1], sys.argv[2]

MAX_TOOL_CARDS = 3
REACH_SKILLS_AND_TOOLS = (
    'Skills via skill_search and tool_call({ address: "skill/<name>" }); '
    "tools via tool_search and tool_call({ address, args })."
)
NO_FILE_PATHS = "Never construct file paths from a suggestion."
INJECTED_BY_RUNTIME = "Injected by the agent runtime after the user's message; not authored by the user."
BLOCK_DESCRIPTION = "\n".join([
    INJECTED_BY_RUNTIME,
    "Suggestions are optional; confidence indicates relevance, not authority.",
    REACH_SKILLS_AND_TOOLS,
    NO_FILE_PATHS,
])
POINTER_DESCRIPTION = "\n".join([
    INJECTED_BY_RUNTIME,
    "The full suggestions were already injected this session, so only their names repeat here.",
    REACH_SKILLS_AND_TOOLS,
    NO_FILE_PATHS,
])
# The capability's own closing advice on an unavailable notice, whatever tools it names; replaced by ours.
CAPABILITY_ADVICE = re.compile(r"\s+Find (?:tools|skills)\b.*\Z", re.S)


def confidence_of(node):
    try:
        return float(node.findtext("confidence") or 0)
    except ValueError:
        return 0.0


def unavailable_notice(text):
    return f"{CAPABILITY_ADVICE.sub('', text.strip())} {REACH_SKILLS_AND_TOOLS}"


root = ET.parse(path).getroot()
resources = root.find("resources")
notice = resources.find("notice") if resources is not None else None
tools = []
for tag in ("tools", "mcp-tools"):
    collection = resources.find(tag) if resources is not None else None
    if collection is None:
        continue
    for node in list(collection):
        name = (node.findtext("name") or "").strip()
        card = (node.findtext("how-to-call") or "").strip()
        # Only a gateway card (it opens with `name:` and carries the address) is callable from the suggestion;
        # anything else, such as an older "call the harness tool X directly" line, is dropped.
        if name and card.startswith("name:"):
            tools.append({"tag": tag, "name": name, "card": card, "confidence": confidence_of(node)})
        collection.remove(node)
kept = sorted(tools, key=lambda tool: tool["confidence"], reverse=True)[:MAX_TOOL_CARDS]

if mode == "block":
    for tag in ("tools", "mcp-tools"):
        collection = resources.find(tag) if resources is not None else None
        if collection is None:
            continue
        cards = [tool for tool in kept if tool["tag"] == tag]
        collection.text = "\n      " if cards else None
        for index, tool in enumerate(cards):
            node = ET.SubElement(collection, "tool")
            node.text = tool["card"]
            node.tail = "\n    " if index == len(cards) - 1 else "\n      "
    description = root.find("description")
    if description is None:
        description = ET.Element("description")
        root.insert(0, description)
    description.text = f"\n{BLOCK_DESCRIPTION}\n  "
    if notice is not None:
        notice.text = unavailable_notice(notice.text or "")
    # ElementTree escapes < and > in text; the agent reads the call forms as written.
    print(ET.tostring(root, encoding="unicode").replace(escape(REACH_SKILLS_AND_TOOLS), REACH_SKILLS_AND_TOOLS))
    sys.exit(0)

skills = [name for name in (node.findtext("name", "").strip() for node in root.findall("./resources/skills/skill")) if name]
names = {tag: [tool["name"] for tool in kept if tool["tag"] == tag] for tag in ("tools", "mcp-tools")}
if root.get("status") == "unavailable" and notice is not None and (notice.text or "").strip():
    # A degraded run is never silent, even on a repeat: name the outage instead of dropping the block.
    print(unavailable_notice(notice.text))
    sys.exit(0)
if not skills and not names["tools"] and not names["mcp-tools"]:
    sys.exit(1)

def line(tag, values):
    return f"    <{tag}>{', '.join(values)}</{tag}>" if values else f"    <{tag} />"

print("\n".join([
    "<system-context",
    '  source="suggest_skills_tools_and_mcp"',
    '  origin="runtime"',
    '  mode="pointer"',
    ">",
    "  <description>",
    POINTER_DESCRIPTION,
    "  </description>",
    "  <resources>",
    line("skills", skills),
    line("tools", names["tools"]),
    line("mcp-tools", names["mcp-tools"]),
    "  </resources>",
    "</system-context>",
]))
PY
}

emit_context() {
	local dir="$1" session="$2" cwd="$3" lines="" line xml block pointer=""
	for line in "$(intent_line "$dir/intent.json")" "$(project_line "$dir/project.json")" "$(scope_line "$session" "$cwd")"; do
		[[ -n "$line" ]] && lines+="${lines:+$'\n'}$line"
	done
	xml="$(cat 2>/dev/null <"$dir/skills.xml")"
	if [[ "$xml" == '<system-context'* ]]; then
		local hash prior
		block="$(suggest_render block "$dir/skills.xml")"
		hash="$(suggest_fingerprint "$dir/skills.xml")"
		prior="$(last_suggest_hash)"
		if [[ -n "$hash" && "$prior" == "$hash" ]]; then
			pointer="$(suggest_render pointer "$dir/skills.xml")"
		fi
		if [[ -n "$pointer" ]]; then
			lines+="${lines:+$'\n'}$pointer"
		elif [[ -n "$block" ]]; then
			lines+="${lines:+$'\n'}$block"
			if [[ "$session" =~ $SESSION_ID_PATTERN && -n "$hash" ]]; then
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
	SESSION_ID="$session"
	RUN_DIR="$dir"
	run_all "$prompt" "${cwd:-$HOME}" "$dir"
	write_skill_pick
	emit_context "$dir" "$session" "${cwd:-$HOME}"
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

# The suggester's largest answer for the self-test prompt: 5 skills and 3 tool cards. Its description is in the retired
# wording on purpose: the hook owns that text and must replace it.
write_fixture_suggestions() {
	cat >"$1" <<'XML'
<system-context
  source="suggest_skills_tools_and_mcp"
  origin="runtime"
>
  <description>
This context was automatically injected by the agent runtime
after the user's message. It was not authored by the user.

These resources are available for consideration. Select and
use them when relevant to the user's request. Suggested skills
are optional, and confidence scores indicate relevance,
not authority. Open a suggested skill with read_skill (pass the
bare name) or search for more with find_skills — never construct
file paths from a suggestion.
  </description>
  <resources>
    <skills>
      <skill>
        <name>verification-before-completion</name>
        <description>Run the verification commands and confirm their output before claiming work is complete, fixed or passing.</description>
        <path>verification-before-completion</path>
        <confidence>0.91</confidence>
      </skill>
      <skill>
        <name>code-construction</name>
        <description>Use when creating, changing, refactoring or reviewing code; keeps domain workflows visible and effects explicit.</description>
        <path>code-construction</path>
        <confidence>0.89</confidence>
      </skill>
      <skill>
        <name>systematic-debugging</name>
        <description>Use for any bug, test failure or unexpected behavior, before proposing fixes.</description>
        <path>systematic-debugging</path>
        <confidence>0.84</confidence>
      </skill>
      <skill>
        <name>code-style</name>
        <description>Approval bar for code: atomic composition, facades, names that say what and not how, no magic values.</description>
        <path>code-style</path>
        <confidence>0.83</confidence>
      </skill>
      <skill>
        <name>verify</name>
        <description>Drive the running app or CLI end to end and assert the real end state before saying done.</description>
        <path>verify</path>
        <confidence>0.80</confidence>
      </skill>
    </skills>
    <tools>
      <tool>
        <name>capability/memory_search</name>
        <description>Search this machine's past agent sessions: what was tried, what broke, what was decided, and in which repository.</description>
        <how-to-call><![CDATA[
name:        capability/memory_search
description: Search this machine's past agent sessions: what was tried, what broke, what was decided, and in which repository.
input:       { query: string (required), limit?: integer 1-50, repository?: string, as_of?: string }
example:     tool_call("capability/memory_search", {"query":"what did we decide about the memory backend"})
returns:     { evidence: [{ id: string, score: number, source: string, session: string, at: string, repository?: string, text: string }], arms: object, degraded?: boolean, reason?: string }
flags:       read-only
]]></how-to-call>
        <confidence>0.86</confidence>
      </tool>
      <tool>
        <name>capability/summarize</name>
        <description>Summarize a command's output or a file for another agent and return the path and line count of the raw output.</description>
        <how-to-call><![CDATA[
name:        capability/summarize
description: Summarize a command's output or a file for another agent and return the path and line count of the raw output.
input:       { text: string (required), purpose?: string }
example:     tool_call("capability/summarize", {"text":"string"})
returns:     { summary: string, path: string, lines: integer }
flags:       read-only
]]></how-to-call>
        <confidence>0.82</confidence>
      </tool>
    </tools>
    <mcp-tools>
      <tool>
        <name>linear/save_issue</name>
        <description>Create or update a Linear issue; pass id to update, otherwise team and title create one.</description>
        <how-to-call><![CDATA[
name:        linear/save_issue
description: Create or update a Linear issue; pass id to update, otherwise team and title create one.
input:       { id?: string, team?: string, title?: string, description?: string }
example:     tool_call("linear/save_issue", {})
returns:     { id: string, url: string }
flags:       writes
]]></how-to-call>
        <confidence>0.78</confidence>
      </tool>
    </mcp-tools>
  </resources>
</system-context>
XML
}

# A degraded run: the suggester could not judge, so it says so in a notice (in the retired wording again).
write_fixture_unavailable() {
	cat >"$1" <<'XML'
<system-context
  source="suggest_skills_tools_and_mcp"
  origin="runtime"
  status="unavailable"
>
  <description>
This context was automatically injected by the agent runtime
after the user's message. It was not authored by the user.
  </description>
  <resources>
    <notice status="unavailable">Recommendations are unavailable this turn (judge timed out). Find tools with tool_search and skills with find_skills.</notice>
    <skills />
    <tools />
    <mcp-tools />
  </resources>
</system-context>
XML
}

# A `capability` that answers from the fixtures in <dir>, so the self-test needs no model, no network and no
# installed runtime.
write_stubs() {
	local dir="$1"
	mkdir -p "$dir/bin"
	printf '%s' '{"output":{"Parts":[{"Type":{"Value":"task"},"Intent":{"Value":"fix"}}]}}' >"$dir/intent.json"
	printf '%s' '{"output":{"ProjectName":"agent-hooks","NeedsNewProject":false,"Probabilities":{"agent-hooks":0.39}}}' \
		>"$dir/project.json"
	cat >"$dir/bin/capability" <<STUB
#!/bin/sh
case "\$2" in
identify_intent) cat "$dir/intent.json" ;;
select_project) cat "$dir/project.json" ;;
suggest_skills_tools_and_mcp) cat "$dir/suggestions.xml" ;;
*) exit 1 ;;
esac
STUB
	chmod +x "$dir/bin/capability"
}

# Runs the hook once on <payload> and leaves its stdout in <output>; the harness or MCP commands seen under it go to
# <dir>/forbidden. The stubs in <dir>/bin answer every capability call.
observe_hook() {
	local dir="$1" payload="$2" output="$3" pid started
	PATH="$dir:$PATH" PROMPT_SUBMIT_FRESH=1 env -u AGENTMUX_NESTED_RUN \
		CAPABILITY_BIN_DIR="$dir/bin" \
		"$SELF" --skip-guard <<<"$payload" >"$output" &
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

# One prompt of <session> through the hook: run_turn <dir> <session> <name> leaves the hook output in <dir>/<name>.
run_turn() {
	local dir="$1" session="$2" name="$3" payload
	payload="$(jq -nc --arg p "$SELF_TEST_PROMPT" --arg c "$PWD" --arg s "$session" '{prompt: $p, cwd: $c, session_id: $s}')"
	observe_hook "$dir" "$payload" "$dir/$name"
}

# The hook JSON: the intent line first, the scope line beside it, then the capability's XML as the last block.
has_hook_shape() {
	jq -e '
    .hookSpecificOutput.hookEventName == "UserPromptSubmit"
    and (.hookSpecificOutput.additionalContext as $c
         | ($c | startswith("Intent: "))
           and ($c | split("\n") | any(startswith("Scope: omp-") and contains(" · cwd: ")))
           and ($c | contains("<system-context"))
           and ($c | rtrimstr("\n") | endswith("</system-context>")))' "$1" >/dev/null 2>&1
}

context_of() {
	jq -r '.hookSpecificOutput.additionalContext // empty' "$1" 2>/dev/null
}

# The context's length in characters, as the agent counts it (jq counts code points, not bytes).
chars_of() {
	jq -r '(.hookSpecificOutput.additionalContext // "") | length' "$1" 2>/dev/null
}

# check_wording <label> <context>: the agent is told how to reach skills and tools, and no retired tool is named.
check_wording() {
	local label="$1" context="$2" phrase failed=0
	for phrase in "${SELF_TEST_REQUIRED_WORDING[@]}"; do
		[[ "$context" == *"$phrase"* ]] || {
			echo "self-test: $label: the context does not say: $phrase" >&2
			failed=1
		}
	done
	if grep -Eq "$SELF_TEST_RETIRED_WORDING" <<<"$context"; then
		echo "self-test: $label: the context still names a retired tool ($SELF_TEST_RETIRED_WORDING)" >&2
		failed=1
	fi
	return "$failed"
}

# The first turn of a session: the full block, the scope/intent/project lines, and the whole context within budget.
check_first_turn() {
	local output="$1" context chars skills cards failed=0
	if ! has_hook_shape "$output"; then
		echo "self-test: first turn: output is not the hook shape (Intent line first, a Scope line, XML block last):" >&2
		cat <"$output" >&2
		return 1
	fi
	context="$(context_of "$output")"
	chars="$(chars_of "$output")"
	skills="$(grep -c '<skill>' <<<"$context")" || :
	cards="$(grep -c '<tool>name:' <<<"$context")" || :
	echo "self-test: first turn context: $chars characters (limit $SELF_TEST_CONTEXT_MAX_CHARS), $skills skills, $cards tool cards" >&2
	if [[ -n "${SELF_TEST_SHOW_CONTEXT:-}" ]]; then printf '%s\n' "$context" >&2; fi
	((chars <= SELF_TEST_CONTEXT_MAX_CHARS)) || {
		echo "self-test: first turn: the context is over $SELF_TEST_CONTEXT_MAX_CHARS characters" >&2
		failed=1
	}
	((skills == SELF_TEST_SKILLS && cards == SELF_TEST_TOOL_CARDS)) || {
		echo "self-test: first turn: expected $SELF_TEST_SKILLS skills and $SELF_TEST_TOOL_CARDS tool cards" >&2
		failed=1
	}
	[[ "$context" == *$'\nProject: agent-hooks (p=0.39)'* ]] || {
		echo "self-test: first turn: the project line is missing" >&2
		failed=1
	}
	check_wording "first turn" "$context" || failed=1
	return "$failed"
}

# The same suggestions again in the session: only the names-only pointer, still with the scope line, and shorter.
check_repeat_turn() {
	local output="$1" first="$2" context failed=0
	if ! has_hook_shape "$output"; then
		echo "self-test: repeat turn: output is not the hook shape:" >&2
		cat <"$output" >&2
		return 1
	fi
	context="$(context_of "$output")"
	[[ "$context" == *'mode="pointer"'* && "$context" != *'<skill>'* && "$context" == *verification-before-completion* ]] || {
		echo "self-test: repeat turn: expected the names-only pointer" >&2
		failed=1
	}
	(($(chars_of "$output") < $(chars_of "$first"))) || {
		echo "self-test: repeat turn: the pointer is not shorter than the full block" >&2
		failed=1
	}
	check_wording "repeat turn" "$context" || failed=1
	return "$failed"
}

# A degraded suggester names the outage on every turn, in the hook's wording; <label> says which turn.
check_unavailable_turn() {
	local label="$1" output="$2" context failed=0
	context="$(context_of "$output")"
	[[ "$context" == Intent:* && "$context" == *$'\nScope: omp-'* && "$context" == *'Recommendations are unavailable'* ]] || {
		echo "self-test: $label: expected the intent line, the scope line and the unavailable notice:" >&2
		printf '%s\n' "$context" >&2
		return 1
	}
	check_wording "$label" "$context" || failed=1
	return "$failed"
}

self_test() {
	command -v jq >/dev/null || {
		echo "self-test: jq is missing" >&2
		return 1
	}
	local dir session="self-test-$$" verdict=0
	dir="$(mktemp -d)" || return 1
	write_canaries "$dir"
	write_stubs "$dir"
	write_fixture_suggestions "$dir/suggestions.xml"
	ps -p $$ >/dev/null 2>&1 || echo "self-test: note: ps is not permitted here; checking launcher canaries only" >&2
	run_turn "$dir" "$session-block" first
	run_turn "$dir" "$session-block" repeat
	write_fixture_unavailable "$dir/suggestions.xml"
	run_turn "$dir" "$session-down" down
	run_turn "$dir" "$session-down" down-repeat
	if [[ -s "$dir/called" || -s "$dir/forbidden" ]]; then
		echo "self-test: a harness or MCP process ran under the hook:" >&2
		cat "$dir/called" "$dir/forbidden" >&2 2>/dev/null
		verdict=1
	else
		check_first_turn "$dir/first" || verdict=1
		check_repeat_turn "$dir/repeat" "$dir/first" || verdict=1
		check_unavailable_turn "unavailable turn" "$dir/down" || verdict=1
		check_unavailable_turn "unavailable repeat" "$dir/down-repeat" || verdict=1
	fi
	rm -f "$SUGGEST_STATE_DIR/$session-block" "$SUGGEST_STATE_DIR/$session-down" \
		"$SKILL_PICKS_DIR/$session-block.json" "$SKILL_PICKS_DIR/$session-down.json"
	rm -rf "$dir"
	if ((verdict == 0)); then echo ok; fi
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
