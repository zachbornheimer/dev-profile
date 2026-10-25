---
name: tool-denial-recovery
description: Load when a tool is denied or unavailable. Teaches discovery-first recovery process to find alternatives automatically.
---

# Tool Denial Recovery

Use this skill when you call a tool and receive "No such tool available", "disabled", or similar denial.

## Recovery Process

1. **Extract capability category**: What does the denied tool do?
   - Bash/sh/zsh/exec → "command execution"
   - WebSearch/GoogleSearch → "web search"  
   - Read/Write/Edit → "file operations"
   - WebFetch → "web operations"

2. **Call ToolSearch immediately**: `ToolSearch("<capability category>")`
   - Do NOT retry the denied tool
   - Do NOT ask user before attempting discovery

3. **If alternatives found**: Use them. Example:
   - Bash denied → ToolSearch("command execution") → found `agentmux_capability_run_command` → use it

4. **If no alternatives found**: Research the capability via web/docs:
   - Search for "how to <capability> in <environment>"
   - Read tool catalogs, API documentation
   - Check MCP server listings

5. **Escalate only after exhausting discovery**, with evidence:
   - "I attempted: ToolSearch('X'), web search 'Y', read docs Z. No alternatives found. Need: <specific input>."

## Example from Real Failure

**Transcript**: claude:2ed0c871-6035-437f-b0a4-99497db72f96

❌ **Anti-pattern** (what actually happened):
1. Call Bash → denied "No such tool available"
2. Call Bash again 4 minutes later → denied again
3. Call Bash again 9 minutes later → denied again
4. Call Bash again 13 minutes later → denied again
5. Ask user "I can't run commands" three times
6. Wait 38 minutes for user to say "use run_command"
7. Finally discover and use run_command

**Waste**: 4 denials, 0 discovery attempts, 38-minute delay, 3 user escalations

✅ **Correct pattern**:
1. Call Bash → denied "No such tool available"
2. **Immediately** call ToolSearch("command execution") → found run_command
3. Use run_command
4. Complete task in <2 minutes

**Time saved**: 36 minutes, 3 user interruptions eliminated

## When to Load This Skill

- After receiving any tool denial
- When planning command execution in a new environment
- When debugging "tool not found" errors
- As a preventive measure in automation scripts

## Integration

This skill is enforced by the `missing-tool-discovery` hook at `~/.agents/hooks/missing-tool-discovery.py`, which auto-injects ToolSearch after denials. Loading this skill makes the discovery process explicit in your reasoning and helps you understand why ToolSearch calls appear automatically.

## Anti-Patterns to Avoid

1. **Repeated retry**: Calling the same denied tool multiple times
2. **Premature escalation**: Asking user before attempting discovery
3. **Wrong research target**: Researching the denied tool's docs instead of searching for alternatives
4. **No capability extraction**: Not identifying what category of tool you need

## Success Criteria

- Zero repeat calls to denied tools
- ToolSearch attempted within same decision round as denial
- User escalation only after exhausting discovery
- Time to recovery <2 minutes
