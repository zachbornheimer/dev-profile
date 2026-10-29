# Self-Healing Tool Discovery: Transparent Middleware Architecture

**Status**: Pragmatic hooks implemented. This specifies the full transparent middleware design.

**Goal**: When an agent calls a missing tool, the system automatically discovers, loads, and retries with alternatives—transparently.

## Problem (from forensic analysis)

Transcript claude:2ed0c871-6035-437f-b0a4-99497db72f96:

- 4 Bash calls, all denied "No such tool available"
- Zero discovery attempts for 38 minutes
- User had to say "run command is the way"

**Root**: Discovery is instruction-dependent, not system-guaranteed.

## Architecture

### 1. Tool Call Interception (Harness Layer)

Tool calls go through middleware BEFORE reaching denial:

```typescript
class ToolMiddleware {
  intercept(call: ToolCall): Result {
    if (!catalog.has(call.tool)) {
      alternatives = discover(call.tool);
      if (alternatives) return retryWith(alternatives[0], call.args);
    }
    return execute(call.tool, call.args);
  }
}
```

**Key**: Harness checks existence; agent never sees denial.

### 2. Capability Inference

```typescript
inferCapability(toolName: string, args: any): string {
  // Static map: Bash → command_execution
  if (CAPABILITY_MAP[toolName]) return CAPABILITY_MAP[toolName];

  // Arg analysis: {command: "ls"} → command_execution
  if (args.command || args.shell) return 'command_execution';

  // LLM classify (cached)
  return llmClassify(toolName, args);
}
```

### 3. Discovery Service

```typescript
discover(capability: string): Tool[] {
  // 1. MCP server catalog
  candidates.push(...mcpSearch(capability));

  // 2. Local registry
  candidates.push(...localRegistry(capability));

  // 3. Web search (cached)
  if (!candidates.length) candidates.push(...webSearch(capability));

  return rank(candidates); // by availability, match, reliability
}
```

### 4. Transparent Retry

```typescript
retryWith(alternative: Tool, originalArgs: any): Result {
  // Translate args to alternative's schema
  translated = translateArgs(originalArgs, alternative.schema);

  // Execute
  result = alternative.execute(translated);

  // Log substitution (not shown to agent)
  logSubstitution(original, alternative, result.ok);

  return result;
}
```

### 5. Learning Loop

```typescript
class AdaptiveCatalog {
  recordSubstitution(original: string, alternative: string, success: bool) {
    db.insert({original, alternative, success, timestamp, environment});
  }

  getPreferredAlternative(tool: string): string {
    return db.query(
      "SELECT alternative FROM subs WHERE original=? AND success=true
       ORDER BY COUNT(*) DESC LIMIT 1", tool
    ).one();
  }
}
```

## Implementation Phases

### Phase 1: Pragmatic Hooks ✅

**Implemented** (2024-10-21):

- `missing-tool-discovery.py`: Injects ToolSearch after denial
- `escalation-budget.py`: Prevents repeated asks
- `tool-denial-recovery` skill
- AGENTS.md instruction

**Limitation**: Requires agent to follow instructions. Denial still occurs.

### Phase 2: Harness Middleware (Next)

Location: `packages/mcp-agent/src/middleware/tool-discovery.ts`

```typescript
export class ToolDiscoveryMiddleware {
  async intercept(call: ToolCall): Promise<ToolResult> {
    if (!catalog.has(call.tool)) {
      alternatives = await discover(call.tool);
      if (alternatives.length) return retryWith(alternatives[0], call.args);
    }
    return next(call);
  }
}
```

**Advantage**: Works regardless of instructions. Zero prompt dependency.

### Phase 3: MCP Standard (Future)

Extend MCP Tool Protocol:

```typescript
interface MCPToolManifest {
  capabilities: string[];    // ["command_execution"]
  replaces: string[];        // ["Bash", "sh"]
  fallback_for: string[];    // What this substitutes
}

interface MCPDiscoveryProtocol {
  discover(capability: string): Promise<Tool[]>;
  substitute(original: Tool, args: any): Promise<{tool: Tool, args: any}>;
}
```

## Success Criteria

1. **Zero instruction dependency**: Agent doesn't need to "know" to call ToolSearch
2. **Sub-second discovery**: <1s from original call to retry
3. **100% transparent**: Agent sees success/failure, not "I discovered X"
4. **Learning-enabled**: Improves via substitution history
5. **Cross-environment**: Works in Claude Code, Cursor, Codex without reimplementation

## Metrics

Per session:

- `tool_denials`: Unavailable tool calls
- `auto_discoveries`: Successful automatic substitutions
- `discovery_latency_ms`: Denial to retry time
- `substitution_success_rate`: % successful
- `user_escalations_prevented`: Escalations avoided

**Target**:

- `auto_discoveries / tool_denials > 0.95` (95%+ auto-recovery)
- `discovery_latency_ms < 1000`
- `user_escalations_prevented > 0`

## Current State

**Implemented**: Hooks, skill, instruction
**Next**: Phase 2 middleware in mcp-agent
**Open**:

1. Sync vs async discovery?
2. Schema mismatch handling?
3. Expose discovery or keep transparent?
4. Discovery cache TTL?

## Novel Contribution

Transparent middleware at **harness layer**, not agent layer.

**Prior art**: Langchain (instruction-based), AutoGPT (plugin management)
**This**: System-level, transparent, learning-enabled
