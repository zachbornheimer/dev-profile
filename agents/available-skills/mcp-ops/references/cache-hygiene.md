# Cache Hygiene — Keep the Prefix Hot

Sources:

- Anthropic, "Lessons from building Claude Code: Prompt caching is everything" (2026-04-30)
- Anthropic, "Harnessing Claude's Intelligence" (2026-04-02)

## The rule: static first, dynamic last

Prompt caching is prefix-matching. Every byte before the first change in the prefix
is reused; every byte after is re-computed at full input cost. Get the ordering
right once and most caching is free:

```
1. Static system prompt + tool stubs   ← globally cached across all sessions
2. Standing instructions / CLAUDE.md   ← cached per project
3. Session context                     ← cached per session
4. Conversation messages               ← dynamic; not cached
```

Any change to layers 1–2 busts the cache for every session. Changes to layer 4 are
expected and cost only the new tokens.

Common ways the prefix silently changes and breaks caching:

- Injecting a timestamp or date into the system prompt on every turn
- Shuffling tool definitions non-deterministically (sort them; lock the order)
- Adding/removing MCP tools mid-conversation
- Switching models within the same thread

## Never switch models mid-thread

**Wrong:** "This sub-question is easy — let me switch to Haiku to save tokens."

If the thread is 100k tokens into an Opus conversation, switching to Haiku costs
MORE, not less:

- Haiku must rebuild its prompt cache from zero — 100k uncached input tokens.
- You pay Haiku's full uncached rate on the full history.
- You still pay Opus's cost for subsequent turns.

**Right:** fork a fresh worker with a hand-off summary.

```
Orchestrator (Opus, 100k-token thread):
  → Task reaches a self-contained sub-question
  → Write a 500-token hand-off summary of what Haiku needs to know
  → Spawn Haiku subagent with: [system prompt] + [hand-off summary only]
  → Haiku answers on a cold ~600-token context (genuinely cheap)
  → Return the answer to the Opus thread; continue
```

The fork inherits none of the parent's history — it starts clean. The cost is
proportional to the hand-off, not the accumulated conversation.

## Inject volatile info via `<system-reminder>` — never edit the system prompt

The current time, a changed file, a config value that updated — these change
between turns.

**Wrong:** edit the system prompt to include `Current time: 14:32:01Z`. This
invalidates the cached prefix on every single turn.

**Right:** inject as the next user-turn message or appended to a tool result:

```xml
<system-reminder>Current date: 2026-07-01. The file /workspace/config.yaml changed since last read.
Re-read it before referencing any values from it.</system-reminder>
```

The system prompt stays byte-identical. The cache stays hot. The model sees the
fresh value exactly where it appears in the conversation — as dynamic context, not
as a static prefix rewrite.

## Use `defer_loading` stubs — never remove tools mid-conversation

**Wrong:** "The agent doesn't need the Sentry tool right now — remove it to reduce
context."

Removing a tool changes the tool list, which is part of the cached prefix → cache
miss for the entire conversation history.

**Right:** keep a lightweight stub with `defer_loading: true`:

```json
{
  "name": "sentry__get_issues",
  "description": "Fetch Sentry issues by project. Load full schema via tool_search.",
  "defer_loading": true
}
```

The stub is always present in the same position. When the agent needs the full
definition, it calls `tool_search("sentry")` and gets the real schema loaded on
demand. The cached prefix never changes; only the dynamic tool-search result does.

This is the same principle behind Claude Code's Plan Mode: instead of swapping tool
sets when the user enters plan mode, `EnterPlanMode` and `ExitPlanMode` are tools
the model calls itself. The tool list is identical in every request; the agent's
active constraints change through messages, not through tool mutations.

## Cache-safe forking for compaction

When the context window fills, compaction must preserve the **identical prefix** as
the parent conversation — same system prompt, same tool stubs, same session context
— with the compaction instruction appended as a new user message at the end.

**Wrong approach — breaks the cache:**

```
Summarization call:  [summarize_system_prompt][no tools][full history]
Parent cache key:    [real_system_prompt][tools][session][history]
```

The prefix diverges at token 1 → zero cache hits on potentially 200k tokens of
history. You pay the full uncached rate at exactly the moment the conversation is
longest.

**Right approach — cache-safe fork:**

```
Parent conversation: [system][tools][session][messages…]
Compaction request:  [system][tools][session][messages…][compact_this_prompt]
```

Everything before `[compact_this_prompt]` is already cached. Only the compaction
instruction is new. Keep a "compaction buffer" — headroom in the context window for
the compaction prompt plus the summary output before the next turn.

The API's built-in compaction uses this structure. If you build your own compaction
layer, match it exactly.

## Monitor cache-hit-rate like uptime

Claude Code treats cache-hit-rate as a first-class SLO — incidents fire when it
drops unexpectedly. For MCP-connected pipelines:

**Alert when hit-rate drops suddenly:**

- Something changed in the prefix: tool order shuffled non-deterministically,
  timestamp injected into the system prompt, model switched mid-session.

**Common culprits to instrument:**

- Tool definition order (sort alphabetically or by last-access frequency; lock it)
- System prompt mutations (any field that changes turn-to-turn belongs in messages)
- Model routing (all turns in a session must use the same model)

A few percentage points of cache miss compounds across every turn. On a 50-turn
MCP pipeline with 50k-token sessions, a 5% hit-rate drop is not 5% more cost —
it is 5% of turns paying 10× the input rate. The longer the task, the worse the
miss multiplies.
