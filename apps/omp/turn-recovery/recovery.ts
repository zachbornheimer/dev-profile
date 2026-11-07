// Pure rules for ZYS-8563: which turns a crash really interrupted, and what to tell the agent.
// No I/O and no omp imports, so every branch is testable. store.ts persists, index.ts wires.

/** A turn row's state. Terminal states are absorbing: nothing overwrites them. */
export type TurnState =
  | "running"
  | "awaiting_input"
  | "completed"
  | "failed"
  | "cancelled"
  | "stopped"
  | "recovering"
  | "recovered"
  | "needs_attention";

export const TERMINAL_STATES: readonly TurnState[] = [
  "completed",
  "failed",
  "cancelled",
  "stopped",
  "recovered",
  "needs_attention",
];

/** A heartbeat younger than this means the original owner may still be working, on any machine. */
export const LEASE_MS = 45_000;
export const HEARTBEAT_MS = 15_000;
/** Recovery messages sent for one turn chain before a person has to look. */
export const MAX_RECOVERY_ATTEMPTS = 2;
export const RECOVERY_CUSTOM_TYPE = "herder-turn-recovery";

export interface PendingTool {
  toolCallId: string;
  toolName: string;
  startedAtMs: number;
  /** false when a replay could repeat a side effect. Unknown tools count as non-idempotent. */
  idempotent: boolean;
}

/** Tools that only observe. Anything else (bash, edit, write, task, eval, MCP, ...) fails closed. */
const READ_ONLY_TOOLS: Record<string, true> = {
  read: true,
  grep: true,
  glob: true,
  find: true,
  web_search: true,
  lsp: true,
  todo: true,
  ast_grep: true,
  history: true,
  recall: true,
};

export function isIdempotentTool(toolName: string): boolean {
  return Object.hasOwn(READ_ONLY_TOOLS, toolName);
}

export interface TurnRow {
  turnId: string;
  sessionId: string;
  paneId: string | null;
  ownerId: string;
  ownerHost: string | null;
  generation: number;
  state: TurnState;
  /** Neon's clock: heartbeat and "now" come from the same source, so machine skew cannot matter. */
  heartbeatMs: number;
  nowMs: number;
  recoveryAttempts: number;
  recoverySentMs: number | null;
  recoveryAckedMs: number | null;
  pendingTools: PendingTool[];
}

/** What the harness's own transcript says about the turn, read independently of Neon. */
export interface Evidence {
  /** "completed": a final assistant answer follows the turn start. "unfinished": it does not. "unknown": unreadable. */
  transcript: "completed" | "unfinished" | "unknown";
  /** The recovery message for this turn is already in the transcript. */
  recoveryMessageInTranscript: boolean;
}

export type SkipReason =
  | "no-record"
  | "own-turn"
  | "completed"
  | "failed"
  | "cancelled"
  | "stopped"
  | "recovered"
  | "awaiting-input"
  | "needs-attention";

export type Decision =
  | { kind: "skip"; reason: SkipReason }
  | { kind: "wait"; reason: "owner-live"; retryInMs: number }
  | { kind: "close"; as: "completed"; reason: "transcript-shows-completion" }
  | { kind: "ack"; reason: "recovery-message-in-transcript" }
  | { kind: "recover"; resend: boolean; pendingTools: PendingTool[] }
  | { kind: "attention"; reason: "recovery-attempts-exhausted" | "transcript-unreadable" }
  | { kind: "unknown"; reason: "store-unavailable" };

const SKIP_FOR_STATE: Partial<Record<TurnState, SkipReason>> = {
  completed: "completed",
  failed: "failed",
  cancelled: "cancelled",
  stopped: "stopped",
  recovered: "recovered",
  awaiting_input: "awaiting-input",
  needs_attention: "needs-attention",
};

/**
 * Decide what a freshly started process does about the session's latest turn.
 * `selfOwnerId` is this process: a turn it owns is live by definition.
 */
export function decide(row: TurnRow | undefined, evidence: Evidence, selfOwnerId: string): Decision {
  if (!row) return { kind: "skip", reason: "no-record" };
  const terminal = SKIP_FOR_STATE[row.state];
  if (terminal) return { kind: "skip", reason: terminal };
  if (row.ownerId === selfOwnerId) return { kind: "skip", reason: "own-turn" };

  // running | recovering. A missing stop record is not proof of a crash: the owner may be alive.
  const age = row.nowMs - row.heartbeatMs;
  if (age < LEASE_MS) return { kind: "wait", reason: "owner-live", retryInMs: LEASE_MS - age + 1_000 };

  if (evidence.transcript === "completed") {
    return { kind: "close", as: "completed", reason: "transcript-shows-completion" };
  }
  // Sent but never acknowledged: the transcript, not the registry, says whether it arrived.
  if (row.recoverySentMs !== null && row.recoveryAckedMs === null && evidence.recoveryMessageInTranscript) {
    return { kind: "ack", reason: "recovery-message-in-transcript" };
  }
  if (evidence.transcript === "unknown") return { kind: "attention", reason: "transcript-unreadable" };
  if (row.recoveryAttempts >= MAX_RECOVERY_ATTEMPTS) {
    return { kind: "attention", reason: "recovery-attempts-exhausted" };
  }
  const resend = row.recoverySentMs !== null && row.recoveryAckedMs === null;
  return { kind: "recover", resend, pendingTools: row.pendingTools };
}

/** Mid-write transcript entry shapes this module needs; the real entries are wider. */
export interface TranscriptEntry {
  type: string;
  timestamp?: string;
  customType?: string;
  details?: { turnId?: string } | null;
  message?: { role?: string; stopReason?: string; content?: unknown; timestamp?: number };
}

function isToolCallBlock(block: unknown): boolean {
  return typeof block === "object" && block !== null && "type" in block && block.type === "toolCall";
}

/** Read the harness transcript for the turn that started at `turnStartedMs`. */
export function readEvidence(entries: readonly TranscriptEntry[] | undefined, turnId: string, turnStartedMs: number): Evidence {
  if (!entries) return { transcript: "unknown", recoveryMessageInTranscript: false };
  const recoveryMessageInTranscript = entries.some(
    (entry) => entry.customType === RECOVERY_CUSTOM_TYPE && entry.details?.turnId === turnId,
  );
  let last: TranscriptEntry | undefined;
  for (let i = entries.length - 1; i >= 0; i--) {
    if (entries[i]!.type === "message") {
      last = entries[i];
      break;
    }
  }
  const at = last?.message?.timestamp ?? Date.parse(last?.timestamp ?? "");
  const finalAnswer =
    last?.message?.role === "assistant" &&
    last.message.stopReason === "stop" &&
    !(Array.isArray(last.message.content) && last.message.content.some(isToolCallBlock)) &&
    Number.isFinite(at) &&
    at >= turnStartedMs;
  return { transcript: finalAnswer ? "completed" : "unfinished", recoveryMessageInTranscript };
}

/** Map the assistant's final stop reason to the turn's terminal state. */
export function terminalStateForStop(stopReason: string | undefined): TurnState {
  if (stopReason === "stop") return "completed";
  if (stopReason === "aborted") return "cancelled";
  return "failed";
}

/**
 * The note the agent receives. It reports an interruption and asks for verification. It is not a
 * user instruction and grants nothing: the original task and its authority are unchanged.
 */
export function recoveryMessage(row: Pick<TurnRow, "turnId" | "ownerHost" | "pendingTools">, resend: boolean): string {
  const unknown = row.pendingTools.length
    ? row.pendingTools
        .map((tool) => `- ${tool.toolName} (${tool.toolCallId})${tool.idempotent ? "" : " [may have side effects]"}`)
        .join("\n")
    : "- none recorded";
  return [
    "[Herder recovery notice. Automated. This is not a new user instruction and adds no authority.]",
    `Your previous turn (${row.turnId}${row.ownerHost ? ` on ${row.ownerHost}` : ""}) was cut off by a crash or lost process before it finished.${resend ? " An earlier notice for it may not have arrived." : ""}`,
    "Tool calls in flight at that moment have UNKNOWN outcomes:",
    unknown,
    "Before acting: re-read what this session already did, then check the real state (files, git, processes, remote systems).",
    "Do not repeat a write, push, deploy, message, or any other side effect until you have confirmed it did not already happen.",
    "If the checks settle it, continue the interrupted task exactly where it stopped. If they do not, stop and report what is unclear.",
  ].join("\n");
}
