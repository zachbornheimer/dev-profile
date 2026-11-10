// ZYS-8563: resume turns a crash interrupted, using Neon as the one authority.
// Records turn start/stop and in-flight tools from omp's hooks, and on a (re)started session
// reconciles the session's latest turn against the harness transcript before saying anything.
// Install: list this directory under `extensions:` in ~/.omp/agent/config.yml, set SESSIONS_DB_URL.
import { hostname } from "node:os";
import {
  HEARTBEAT_MS,
  RECOVERY_CUSTOM_TYPE,
  decide,
  isIdempotentTool,
  readEvidence,
  recoveryMessage,
  terminalStateForStop,
  type Decision,
  type Evidence,
  type PendingTool,
  type TranscriptEntry,
} from "./recovery.ts";
import { TurnStore, type Fence, type StoredTurn } from "./store.ts";

export interface Ctx {
  hasUI?: boolean;
  sessionManager?: { getSessionId?(): string; getEntries?(): unknown[] };
  ui?: { notify(message: string, type?: "info" | "warning" | "error"): void };
}
type Handler = (event: Record<string, unknown>, ctx: Ctx) => unknown;
export interface OmpApi {
  on(name: string, handler: Handler): void;
  sendMessage(payload: Record<string, unknown>, options?: Record<string, unknown>): void;
  events?: { emit(channel: string, data: unknown): void };
  registerCommand?(name: string, options: { description?: string; handler(args: string, ctx: Ctx): unknown }): void;
}

export interface Deps {
  store: Pick<TurnStore, "begin" | "latest" | "heartbeat" | "transition" | "claimRecovery" | "ackRecovery" | "settle" | "record">;
  ownerId: string;
  host: string;
  paneId: string | null;
  /** Creates the schema on first use. A failure is an `unknown` outcome and is retried, never cached. */
  ready?(): Promise<void>;
  /**
   * Runs between the first read and the claim. A lease that has expired is only a suspicion until a
   * second read agrees: if the heartbeat moved, the owner was alive and merely cut off from Neon.
   * Defaults to waiting one heartbeat period; tests substitute the event they want to inject.
   */
  confirm?(): Promise<void>;
  /** Runs a registry mutation in this process's write order, so a recovery's claim, send and ack finish before the turn it triggers is recorded. */
  serialize?<T>(work: () => Promise<T>): Promise<T>;
  /** Publishes an operator-visible status (the Herdr pane report). Errors are swallowed. */
  publish?(state: "blocked" | "idle", message: string): void;
}

/** What a reconcile pass did, for the audit trail and for tests. */
export interface Outcome {
  decision: Decision["kind"] | "recovered" | "lost-race";
  reason?: string;
  turnId?: string;
  /** For `wait`: when the owner's lease runs out and a re-check can change the answer. */
  retryInMs?: number;
}

const NO_EVIDENCE: Evidence = { transcript: "unknown", recoveryMessageInTranscript: false };
/** Re-checks after a `wait` or `unknown` before the pane is left showing that state. */
const MAX_RETRIES = 12;
const UNKNOWN_RETRY_MS = 60_000;
const MIN_RETRY_MS = 5_000;
/** One registry operation. Past this the queue moves on and the operation's outcome is unknown. */
const OP_TIMEOUT_MS = 10_000;

async function withTimeout<T>(work: Promise<T>, ms: number): Promise<T> {
  const { promise, reject } = Promise.withResolvers<never>();
  const timer = setTimeout(() => reject(new Error(`registry operation timed out after ${ms} ms`)), ms);
  try {
    return await Promise.race([work, promise]);
  } finally {
    clearTimeout(timer);
  }
}

/** Reconcile the session's latest turn once. Never throws: ambiguity becomes an explicit outcome. */
export async function reconcile(pi: Pick<OmpApi, "sendMessage">, ctx: Ctx, deps: Deps): Promise<Outcome> {
  const sessionId = ctx.sessionManager?.getSessionId?.() ?? "";
  if (!sessionId) return { decision: "skip", reason: "no-session" };
  const entries = () => ctx.sessionManager?.getEntries?.() as TranscriptEntry[] | undefined;
  const confirm = deps.confirm ?? (() => Bun.sleep(HEARTBEAT_MS + 1_000));
  try {
    await deps.ready?.();
    let seen = await deps.store.latest(sessionId);
    let decision = decide(seen, seen ? readEvidence(entries(), seen.turnId, seen.startedMs) : NO_EVIDENCE, deps.ownerId);
    if (decision.kind === "recover" && seen) {
      // Verify before acting: an expired lease is only a suspicion until a second read agrees.
      await confirm();
      const again = await deps.store.latest(sessionId);
      const unchanged =
        again !== undefined &&
        again.turnId === seen.turnId &&
        again.generation === seen.generation &&
        again.heartbeatMs === seen.heartbeatMs &&
        again.state === seen.state;
      if (!unchanged) {
        seen = again;
        decision = decide(seen, seen ? readEvidence(entries(), seen.turnId, seen.startedMs) : NO_EVIDENCE, deps.ownerId);
        if (decision.kind === "recover") decision = { kind: "wait", reason: "owner-live", retryInMs: HEARTBEAT_MS };
      }
    }
    const run = () => act(pi, sessionId, seen, decision, deps);
    return await (deps.serialize ? deps.serialize(run) : run());
  } catch (error) {
    deps.publish?.("blocked", "turn state unknown: Neon unreachable");
    return { decision: "unknown", reason: `store-unavailable: ${String(error)}` };
  }
}

async function act(pi: Pick<OmpApi, "sendMessage">, sessionId: string, seen: StoredTurn | undefined, decision: Decision, deps: Deps): Promise<Outcome> {
  const turnId = seen?.turnId;
  const log = async (label: string, detail: unknown) => {
    try {
      await deps.store.record(sessionId, turnId ?? null, deps.ownerId, label, detail);
    } catch {
      // The audit trail must never block recovery.
    }
  };
  if (decision.kind === "close" && seen) {
    await deps.store.settle(seen, "completed");
  } else if (decision.kind === "ack" && seen) {
    await deps.store.settle(seen, "recovered");
  } else if (decision.kind === "attention" && seen) {
    await deps.store.settle(seen, "needs_attention");
    deps.publish?.("blocked", `turn ${seen.turnId} needs attention: ${decision.reason}`);
  } else if (decision.kind === "recover" && seen) {
    const fence = await deps.store.claimRecovery(seen, deps.ownerId);
    if (!fence) {
      await log("lost-race", { turnId: seen.turnId });
      return { decision: "lost-race", turnId: seen.turnId };
    }
    // The attempt is already durable; only now does the message go out.
    try {
      pi.sendMessage(
        {
          customType: RECOVERY_CUSTOM_TYPE,
          content: recoveryMessage(seen, decision.resend),
          display: true,
          attribution: "agent",
          details: { turnId: seen.turnId },
        },
        { triggerTurn: true, deliverAs: "nextTurn" },
      );
    } catch (error) {
      // Left `recovering` with no ack: the next pass sees an unacknowledged send and checks the transcript.
      deps.publish?.("blocked", `turn ${seen.turnId} recovery message was not delivered`);
      await log("send-failed", { turnId: seen.turnId, error: String(error) });
      return { decision: "unknown", reason: "send-failed", turnId: seen.turnId };
    }
    await deps.store.ackRecovery(fence);
    await log("recovered", { turnId: seen.turnId, resend: decision.resend, pendingTools: seen.pendingTools });
    return { decision: "recovered", turnId: seen.turnId };
  }
  const reason = "reason" in decision ? decision.reason : undefined;
  if (!(decision.kind === "skip" && decision.reason === "no-record")) await log(decision.kind, { reason });
  return { decision: decision.kind, reason, turnId, retryInMs: decision.kind === "wait" ? decision.retryInMs : undefined };
}

export interface WireOptions {
  ownerId: string;
  host: string;
  paneId: string | null;
  confirm?(): Promise<void>;
  opTimeoutMs?: number;
}

/** Handles for tests and diagnostics; omp itself ignores them. */
export interface Wiring {
  /** Resolves once every queued registry write and in-flight reconcile has finished. */
  idle(): Promise<void>;
  /** Runs one heartbeat now, as the timer would. */
  heartbeatNow(): Promise<void>;
}

/** Connect omp's lifecycle hooks to the registry. */
export function wire(pi: OmpApi, store: TurnStore, options: WireOptions): Wiring {
  const { ownerId } = options;
  const opTimeoutMs = options.opTimeoutMs ?? OP_TIMEOUT_MS;

  let migrated: Promise<void> | undefined;
  const ready = () =>
    (migrated ??= store.migrate().catch((error) => {
      migrated = undefined; // a failed attempt must not wedge every later one
      throw error;
    }));

  /**
   * One ordered lane for every registry write this process makes. Hooks fire in the order omp raises
   * them, but each one is an async round trip: without the lane `agent_end` can reach Neon before
   * `agent_start` has finished, find no turn to close, and leave a finished turn heartbeating.
   */
  let lane: Promise<void> = Promise.resolve();
  const inLane = <T>(work: () => Promise<T>): Promise<T> => {
    const result = lane.then(() => withTimeout((async () => (await ready(), work()))(), opTimeoutMs));
    lane = result.then(
      () => undefined,
      () => undefined,
    );
    return result;
  };
  /** Best effort: a turn's own work never waits on, or fails because of, the registry. */
  const record = (work: () => Promise<unknown>) => void inLane(work).catch(() => undefined);

  // `herdr:blocked` is the contract herdr-omp-agent-state.ts already turns into the sidebar's blocked row.
  let blocked = false;
  const setBlocked = (active: boolean, label: string) => {
    if (active === blocked) return;
    blocked = active;
    pi.events?.emit("herdr:blocked", { active, label });
  };
  const deps: Deps = {
    store,
    ownerId,
    host: options.host,
    paneId: options.paneId,
    ready,
    confirm: options.confirm,
    serialize: inLane,
    publish: (_state, message) => setBlocked(true, message),
  };

  let fence: Fence | undefined;
  let seq = 0;
  let closed = false;
  let heartbeatQueued = false;
  let timer: NodeJS.Timeout | undefined;
  let retryTimer: NodeJS.Timeout | undefined;
  let retries = 0;
  const pending = new Map<string, PendingTool>();
  const checks = new Set<Promise<void>>();

  /** Reconcile once, then re-check while the answer is still `wait` or `unknown` and no turn of ours has started. */
  const check = (ctx: Ctx) => {
    const sessionId = ctx.sessionManager?.getSessionId?.();
    const run = (async () => {
      const outcome = await reconcile(pi, ctx, deps);
      if (outcome.decision !== "unknown" && outcome.decision !== "wait") {
        if (outcome.decision !== "attention") setBlocked(false, "");
        return;
      }
      if (closed || retries >= MAX_RETRIES || fence) return;
      retries += 1;
      retryTimer = setTimeout(
        () => {
          if (!closed && !fence && ctx.sessionManager?.getSessionId?.() === sessionId) check(ctx);
        },
        Math.max(outcome.retryInMs ?? UNKNOWN_RETRY_MS, MIN_RETRY_MS),
      );
      retryTimer.unref?.();
    })();
    checks.add(run);
    void run.finally(() => checks.delete(run));
  };

  const heartbeat = () => {
    if (heartbeatQueued) return Promise.resolve();
    heartbeatQueued = true;
    return inLane(async () => {
      heartbeatQueued = false;
      const current = fence;
      if (!current) return;
      if (await store.heartbeat(current, [...pending.values()])) return;
      // The registry no longer recognises this turn: another system took it over, or a newer turn replaced it.
      if (fence === current) {
        fence = undefined;
        setBlocked(true, "this turn was taken over by another system");
      }
    }).catch(() => {
      heartbeatQueued = false;
    });
  };

  pi.on("session_start", (_event, ctx) => {
    if (ctx.hasUI !== true) return;
    retries = 0;
    check(ctx);
  });

  pi.on("session_switch", (event, ctx) => {
    if (ctx.hasUI !== true || event.reason !== "resume") return;
    clearTimeout(retryTimer);
    retries = 0;
    check(ctx);
  });

  pi.on("agent_start", (_event, ctx) => {
    const sessionId = ctx.sessionManager?.getSessionId?.();
    if (closed || ctx.hasUI !== true || !sessionId) return;
    // A turn starting here supersedes whatever recovery was still waiting or showing.
    clearTimeout(retryTimer);
    setBlocked(false, "");
    pending.clear();
    record(async () => {
      fence = await store.begin({ turnId: crypto.randomUUID(), sessionId, paneId: options.paneId, ownerId, ownerHost: options.host });
      seq = 0;
      timer ??= setInterval(() => {
        if (fence) void heartbeat();
      }, HEARTBEAT_MS);
      timer.unref?.();
    });
  });

  pi.on("tool_execution_start", (event) => {
    const toolCallId = String(event.toolCallId ?? "");
    const toolName = String(event.toolName ?? "");
    if (!toolCallId) return;
    pending.set(toolCallId, { toolCallId, toolName, startedAtMs: Date.now(), idempotent: isIdempotentTool(toolName) });
    // Land a possible side effect in the registry now, not at the next heartbeat: a crash seconds
    // after a write would otherwise leave the recovery notice with nothing to name.
    if (!isIdempotentTool(toolName)) void heartbeat();
    // "ask" waits on a person: that is not an interruption to resume.
    if (toolName === "ask") {
      record(async () => {
        if (fence) await store.transition(fence, "awaiting_input", ++seq);
      });
    }
  });

  pi.on("tool_execution_end", (event) => {
    pending.delete(String(event.toolCallId ?? ""));
    if (event.toolName === "ask") {
      record(async () => {
        if (fence) await store.transition(fence, "running", ++seq);
      });
    }
  });

  pi.on("agent_end", (event) => {
    // Not a settle: a continuation is scheduled, or background work may resume the turn.
    if (event.willContinue === true || event.awaitingAsyncWork === true) return;
    const messages = Array.isArray(event.messages) ? event.messages : [];
    const last = messages.findLast((m) => typeof m === "object" && m !== null && "role" in m && m.role === "assistant");
    const stopReason = last && typeof last === "object" && "stopReason" in last && typeof last.stopReason === "string" ? last.stopReason : undefined;
    record(async () => {
      const done = fence;
      if (!done) return;
      fence = undefined;
      await store.transition(done, terminalStateForStop(stopReason), ++seq);
    });
  });

  // Ctrl-C, /quit and SIGTERM are intentional: recorded as stopped, never resumed.
  pi.on("session_shutdown", async () => {
    closed = true;
    clearInterval(timer);
    clearTimeout(retryTimer);
    await inLane(async () => {
      const done = fence;
      if (!done) return;
      fence = undefined;
      await store.transition(done, "stopped", ++seq);
    }).catch(() => undefined);
  });

  pi.registerCommand?.("turn-recovery", {
    description: "Show why this session's last turn resumed, stayed stopped, or needs attention",
    handler: async (_args, ctx) => {
      const sessionId = ctx.sessionManager?.getSessionId?.() ?? "";
      try {
        await ready();
        const [turn, events] = await Promise.all([store.latest(sessionId), store.events(sessionId, 8)]);
        const lines = [`turn: ${turn ? `${turn.turnId} ${turn.state} (generation ${turn.generation}, owner ${turn.ownerId}, recovery attempts ${turn.recoveryAttempts})` : "none recorded"}`];
        for (const event of events) lines.push(`${event.at} ${event.actor} ${event.decision} ${JSON.stringify(event.detail)}`);
        ctx.ui?.notify(lines.join("\n"), "info");
      } catch (error) {
        ctx.ui?.notify(`turn state unknown: Neon unreachable (${String(error)})`, "warning");
      }
    },
  });

  return {
    async idle() {
      let settled: Promise<void>;
      do {
        settled = lane;
        await Promise.all([settled, ...checks]);
      } while (settled !== lane || checks.size > 0);
    },
    heartbeatNow: heartbeat,
  };
}

export default function register(pi: OmpApi): void {
  const url = process.env.SESSIONS_DB_URL;
  if (!url) return;
  wire(pi, new TurnStore(url), {
    ownerId: `${hostname()}:${process.pid}:${Date.now().toString(36)}`,
    host: hostname(),
    paneId: process.env.HERDR_PANE_ID ?? null,
  });
}
