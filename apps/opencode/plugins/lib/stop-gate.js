// Stop gate for OpenCode: on session.idle, hand the final assistant message to
// the completion gate and, when it blocks, feed the reason back into the
// session so the agent keeps working. Fails open on every error.

export const MAX_CONSECUTIVE_BLOCKS = 3
export const HARNESS_NAME = 'opencode'
export const FEEDBACK_PREFIX = 'Stop hook feedback:\n'

function lastAssistantText(messages) {
  const lastAssistant = [...(messages ?? [])].reverse().find((m) => m?.info?.role === 'assistant')
  return (lastAssistant?.parts ?? [])
    .filter((part) => part.type === 'text' && !part.ignored)
    .map((part) => part.text)
    .join('\n')
}

// gateBlockReason(payload) -> string | null (reason when the gate blocks).
export function createStopGate({ client, directory, gateBlockReason }) {
  const consecutiveBlocks = new Map()

  async function reprompt(sessionID, reason) {
    await client.session.promptAsync({
      path: { id: sessionID },
      body: { parts: [{ type: 'text', text: `${FEEDBACK_PREFIX}${reason}` }] },
    })
  }

  return async function onIdle(sessionID) {
    if (!sessionID) return
    try {
      const previousBlocks = consecutiveBlocks.get(sessionID) ?? 0
      const { data: messages } = await client.session.messages({ path: { id: sessionID } })
      const reason = gateBlockReason({
        session_id: sessionID,
        hook_event_name: 'Stop',
        harness: HARNESS_NAME,
        last_assistant_message: lastAssistantText(messages),
        cwd: directory,
        stop_hook_active: previousBlocks > 0,
      })
      if (!reason) {
        consecutiveBlocks.delete(sessionID)
        return
      }
      if (previousBlocks >= MAX_CONSECUTIVE_BLOCKS) return
      consecutiveBlocks.set(sessionID, previousBlocks + 1)
      await reprompt(sessionID, reason)
    } catch (err) {
      console.error(`[claude-hooks] stop gate failed: ${err?.message ?? err}`)
    }
  }
}
