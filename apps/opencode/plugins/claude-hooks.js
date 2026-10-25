// Bridges Zach's Claude Code hooks (~/.claude/hooks/*.py) into OpenCode.
//
// OpenCode has no Claude-compatible hooks.json import (unlike Grok, which
// natively scans ~/.claude/settings.json via [compat.claude]). This plugin
// re-implements the same wiring using OpenCode's JS hook API, shelling out
// to the *same* scripts so there is exactly one source of truth for hook
// logic. Every one of those scripts is written to fail open on unexpected
// input (see hook-common.sh), so an imperfect field mapping here degrades
// to "hook silently no-ops" rather than "breaks opencode."
//
// Confirmed against the compiled opencode 1.3.17 binary (tool ids, trigger
// payload shapes, and the "task" tool's {prompt, description, subagent_type,
// command} args all match Claude's Task tool_input 1:1) and verified live —
// see the SessionStart, PreToolUse/Bash, and PreToolUse/Task round trips in
// ~/.claude/hooks/state/hooks.log dated 2026-07-23.
//
// Stop (completion-gate.py) runs on session.idle with the real final
// assistant message (fetched via client.session.messages). A block verdict is
// sent back into the session as "Stop hook feedback:" through
// client.session.promptAsync so the agent continues; re-prompting stops after
// 3 consecutive blocks. Any SDK/gate error fails open. See lib/stop-gate.js.
//
// Remaining gaps vs. Claude Code (no equivalent OpenCode hook point exists):
//   - subagent-model-guard.sh's model-injection half: OpenCode's
//     tool.execute.before has no documented "rewrite tool args" return, so
//     only its enforcement (deny) half applies here, not the default-model
//     injection.
//   - SessionStart context injection (goals-recall.sh): OpenCode has no
//     "inject text as context at session start" hook. The goals file is
//     logged to the opencode log instead of folded into context.
//   - PreCompact (goals-note-compaction.sh) fires on session.compacted
//     (post-compaction) since OpenCode has no pre-compact hook.

import { homeDir, runProcess } from './lib/system.js'
import { createStopGate } from './lib/stop-gate.js'

const HOOKS_DIR = `${homeDir()}/.claude/hooks`
const RELOCATE_SYNCED_SKILLS = `${homeDir()}/.agents/hooks/relocate-synced-skills.py`

function dispatch(eventName, stdinObj) {
  try {
    const payload = { ...stdinObj, hook_event_name: eventName }
    const out = runProcess(
      'agent-hooks',
      ['--agent', 'opencode', eventName],
      JSON.stringify(payload),
    )
    return out.trim()
  } catch (err) {
    console.error(`[claude-hooks] agent-hooks ${eventName} failed: ${err?.message ?? err}`)
    return err.stdout ? String(err.stdout).trim() : ''
  }
}

function runHook(script, stdinObj, args = []) {
  try {
    const out = runProcess(`${HOOKS_DIR}/${script}`, args, JSON.stringify(stdinObj))
    return out.trim()
  } catch (err) {
    // Hook scripts fail open by design; a nonzero exit here just means no
    // deny/context was produced. Never let a hook error break the tool call.
    console.error(`[claude-hooks] ${script} failed: ${err?.message ?? err}`)
    return err.stdout ? String(err.stdout).trim() : ''
  }
}

// Fire-and-forget informational hooks (never deny, only log/react async).
// Named explicitly so a reader never mistakes this for an unhandled error.
function runHookFireAndForget(script, stdinObj, args = []) {
  try {
    runHook(script, stdinObj, args)
  } catch {
    // already fails open inside runHook; this catch exists only to make
    // "we deliberately never surface this" explicit at the call site.
  }
}

// Hooks print one JSON document, usually pretty-printed across many lines;
// older ones print one JSON object per line. Accept both.
function hookDocuments(rawOutput) {
  try {
    return [JSON.parse(rawOutput)]
  } catch {
    return rawOutput.split('\n').flatMap((line) => {
      try {
        return [JSON.parse(line)]
      } catch {
        return []
      }
    })
  }
}

function contextFrom(rawOutput) {
  if (!rawOutput) return ""
  for (const parsed of hookDocuments(rawOutput)) {
    const text = parsed?.hookSpecificOutput?.additionalContext ?? parsed?.additionalContext ?? parsed?.context
    if (typeof text === "string" && text) return text
  }
  return ""
}

function denyReasonFrom(rawOutput) {
  if (!rawOutput) return null
  for (const parsed of hookDocuments(rawOutput)) {
    const decision = parsed?.hookSpecificOutput?.permissionDecision ?? parsed?.decision
    if (decision === 'deny') {
      return (
        parsed?.hookSpecificOutput?.permissionDecisionReason ?? parsed?.reason ?? 'denied by hook'
      )
    }
  }
  return null
}

function blockReasonFrom(rawOutput) {
  if (!rawOutput) return null
  const blocked = hookDocuments(rawOutput).find((doc) => doc?.decision === 'block')
  return blocked ? (blocked.reason ?? 'blocked by completion gate') : null
}

// Best-effort OpenCode-tool-id -> Claude-tool-name + arg-shape mapping.
// bash/read field names (command, filePath) are confirmed from OpenCode
// docs; edit/write field names follow the same filePath convention but are
// unconfirmed for oldString/newString/content — those only matter to
// scripts that don't inspect them (none of the wired hooks do today).
const TOOL_NAME = {
  bash: 'Bash',
  edit: 'Edit',
  write: 'Write',
  read: 'Read',
  task: 'Task',
}

function toClaudeToolInput(toolId, args) {
  if (toolId === 'bash') return { command: args?.command }
  if (toolId === 'edit' || toolId === 'write' || toolId === 'read') {
    return { file_path: args?.filePath, ...args }
  }
  if (toolId === 'task') {
    // Confirmed field names (opencode binary): prompt, description,
    // subagent_type, command — identical to Claude's Task tool_input shape.
    return args ?? {}
  }
  return args ?? {}
}

export const ClaudeHooksPlugin = async ({ client, directory, $ }) => {
  const sessionStartPayload = { cwd: directory, hook_event_name: 'SessionStart' }

  // SessionStart equivalent: runs once, here, at plugin load.
  await $`git config --global user.email z@chary.me`.quiet().nothrow()
  await $`git config --global user.name ${'Zach Bornheimer'}`.quiet().nothrow()
  await $`git config --global user.signingkey 0D741E83928F06F099F11C331AB073BDF43DBBF3`
    .quiet()
    .nothrow()
  await $`git config --global commit.gpgsign true`.quiet().nothrow()

  try {
    runProcess('python3', [RELOCATE_SYNCED_SKILLS], JSON.stringify(sessionStartPayload))
  } catch (err) {
    // Fail open: a relocate miss must not break plugin load.
    console.error(`claude-hooks relocate-synced-skills failed: ${err?.message ?? err}`)
  }

  const goals = runHook('goals-recall.py', sessionStartPayload)
  if (goals) {
    // No context-injection hook exists in OpenCode's plugin API; surface it
    // to the log instead so it isn't silently lost. Avoid a leading "[" so
    // `opencode debug skill` JSON still starts at the catalog array.
    console.log(`claude-hooks goals-recall:\n${goals}`)
  }

  const stopGate = createStopGate({
    client,
    directory,
    gateBlockReason: (payload) => blockReasonFrom(runHook('completion-gate.py', payload)),
  })

  return {

    "experimental.chat.system.transform": async (input, output) => {
      const base = { cwd: directory, session_id: input?.sessionID, prompt: "" }
      const extra = [
        contextFrom(dispatch("UserPromptSubmit", { ...base, hook_event_name: "UserPromptSubmit" })),
        contextFrom(dispatch("SessionStart", { ...base, hook_event_name: "SessionStart", source: "startup" })),
      ].filter(Boolean).join("\n\n")
      if (extra && output && Array.isArray(output.system)) output.system.push(extra)
    },

    'tool.execute.before': async (input, output) => {
      const claudeTool = TOOL_NAME[input.tool]
      if (!claudeTool) return
      const payload = {
        session_id: input.sessionID,
        tool_name: claudeTool,
        tool_input: toClaudeToolInput(input.tool, output.args),
        cwd: directory,
        hook_event_name: 'PreToolUse',
      }
      const raw = dispatch('PreToolUse', payload)
      const deny = denyReasonFrom(raw)
      if (deny) throw new Error(deny)
    },

    'tool.execute.after': async (input, output) => {
      if (input.tool !== 'bash') return
      const failed = /error|exit code [1-9]/i.test(output?.title ?? '')
      dispatch(failed ? 'PostToolUseFailure' : 'PostToolUse', {
        session_id: input.sessionID,
        tool_name: 'Bash',
        tool_input: { command: input.args?.command },
      })
    },

    event: async ({ event }) => {
      if (event.type === 'session.idle') {
        await stopGate(event.properties?.sessionID)
      }
      if (event.type === 'session.compacted') {
        dispatch('PreCompact', {
          cwd: directory,
          hook_event_name: 'PreCompact',
        })
      }
    },
  }
}
