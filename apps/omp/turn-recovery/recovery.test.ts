// ZYS-8563 fault-injection suite. Runs against a real Postgres (TURN_RECOVERY_TEST_DB), with a second
// connection pool standing in for the second machine. Skipped when no database is configured.
import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { SQL } from "bun";
import { LEASE_MS, RECOVERY_CUSTOM_TYPE, decide, isIdempotentTool, readEvidence, recoveryMessage, terminalStateForStop } from "./recovery.ts";
import { reconcile, type Deps } from "./index.ts";
import { TurnStore } from "./store.ts";

const DB = process.env.TURN_RECOVERY_TEST_DB;
const run = DB ? describe : describe.skip;

interface Sent {
  payload: Record<string, unknown>;
  options: unknown;
}

function harness() {
  const sent: Sent[] = [];
  return { sent, pi: { sendMessage: (payload: Record<string, unknown>, options?: unknown) => void sent.push({ payload, options }) } };
}
function ctxFor(sessionId: string, entries: unknown[] = []) {
  return { hasUI: true, sessionManager: { getSessionId: () => sessionId, getEntries: () => entries } };
}
const finalAnswer = (at: number) => ({ type: "message", message: { role: "assistant", stopReason: "stop", content: [{ type: "text", text: "done" }], timestamp: at } });

run("turn recovery against Neon-shaped Postgres", () => {
  let mac: TurnStore;
  let vps: TurnStore;
  let admin: SQL;
  let n = 0;
  const sid = () => `sess-${Date.now()}-${n++}`;
  const deps = (store: TurnStore, ownerId: string, publish?: Deps["publish"]): Deps => ({ store, ownerId, host: ownerId.split(":")[0]!, paneId: "w1:p1", publish, confirm: async () => {} });
  /** Make the owner look dead: its lease expired without any stop record, which is what a crash leaves. */
  const crash = (sessionId: string) => admin.unsafe(`UPDATE herder_turns SET heartbeat_at = now() - interval '5 minutes' WHERE session_id = $1`, [sessionId]);
  const row = async (sessionId: string) => (await admin.unsafe(`SELECT * FROM herder_turns WHERE session_id = $1 ORDER BY generation DESC LIMIT 1`, [sessionId]))[0];
  const start = (store: TurnStore, sessionId: string, ownerId: string, turnId = crypto.randomUUID()) =>
    store.begin({ turnId, sessionId, paneId: "w1:p1", ownerId, ownerHost: ownerId.split(":")[0]! });

  beforeAll(async () => {
    mac = new TurnStore(DB!);
    vps = new TurnStore(DB!);
    admin = new SQL(DB!);
    await mac.migrate();
  });
  afterAll(async () => {
    await mac.close();
    await vps.close();
    await admin.close();
  });

  test("mid-turn crash: a second machine resumes once, in the same session, without a new user instruction", async () => {
    const s = sid();
    const f = await start(mac, s, "mac:1");
    await mac.heartbeat(f, [{ toolCallId: "c1", toolName: "bash", startedAtMs: 1, idempotent: false }]);
    await crash(s);
    const h = harness();
    const out = await reconcile(h.pi, ctxFor(s, [{ type: "message", message: { role: "user", content: "task", timestamp: Date.now() } }]), deps(vps, "vps:2"));
    expect(out.decision).toBe("recovered");
    expect(h.sent).toHaveLength(1);
    const { payload, options } = h.sent[0]!;
    expect(payload.attribution).toBe("agent");
    expect(payload.customType).toBe(RECOVERY_CUSTOM_TYPE);
    expect(String(payload.content)).toContain("not a new user instruction");
    expect(String(payload.content)).toContain("bash (c1) [may have side effects]");
    expect(options).toEqual({ triggerTurn: true, deliverAs: "nextTurn" });
    expect((await row(s)).state).toBe("recovered");
  });

  test.each([
    ["completed", "completed"],
    ["cancelled", "cancelled"],
    ["stopped", "stopped"],
    ["failed", "failed"],
    ["awaiting_input", "awaiting-input"],
  ] as const)("a %s turn is never resumed", async (state, reason) => {
    const s = sid();
    const f = await start(mac, s, "mac:1");
    await mac.transition(f, state, 1);
    await crash(s);
    const h = harness();
    const out = await reconcile(h.pi, ctxFor(s), deps(vps, "vps:2"));
    expect(out).toMatchObject({ decision: "skip", reason });
    expect(h.sent).toHaveLength(0);
  });

  test("idle pane with no record is left alone", async () => {
    const h = harness();
    const out = await reconcile(h.pi, ctxFor(sid()), deps(vps, "vps:2"));
    expect(out).toMatchObject({ decision: "skip", reason: "no-record" });
    expect(h.sent).toHaveLength(0);
  });

  test("live original owner: a fresh lease on another machine starts no competing turn", async () => {
    const s = sid();
    const f = await start(mac, s, "mac:1");
    await mac.heartbeat(f, []);
    const h = harness();
    const out = await reconcile(h.pi, ctxFor(s), deps(vps, "vps:2"));
    expect(out).toMatchObject({ decision: "wait", reason: "owner-live" });
    expect(h.sent).toHaveLength(0);
    expect((await row(s)).state).toBe("running");
  });

  test("an owner that was only briefly cut off from Neon is not mistaken for dead", async () => {
    const s = sid();
    const f = await start(mac, s, "mac:1");
    await crash(s);
    // The owner's heartbeat lands inside the confirm window, exactly when a recoverer would act.
    const ownerHeartbeats = async () => {
      await mac.heartbeat(f, []);
    };
    const h = harness();
    const out = await reconcile(h.pi, ctxFor(s), { ...deps(vps, "vps:2"), confirm: ownerHeartbeats });
    expect(out).toMatchObject({ decision: "wait", reason: "owner-live" });
    expect(h.sent).toHaveLength(0);
    expect((await row(s)).owner_id).toBe("mac:1");
  });

  test("simultaneous reconnects from two systems enqueue exactly one recovery", async () => {
    const s = sid();
    await start(mac, s, "mac:1");
    await crash(s);
    const [a, b, c] = [harness(), harness(), harness()];
    const outs = await Promise.all([
      reconcile(a.pi, ctxFor(s), deps(mac, "mac:9")),
      reconcile(b.pi, ctxFor(s), deps(vps, "vps:2")),
      reconcile(c.pi, ctxFor(s), deps(vps, "vps:3")),
    ]);
    expect(a.sent.length + b.sent.length + c.sent.length).toBe(1);
    expect(outs.filter((o) => o.decision === "recovered")).toHaveLength(1);
  });

  test("repeated attach after recovery sends nothing more", async () => {
    const s = sid();
    await start(mac, s, "mac:1");
    await crash(s);
    const first = harness();
    await reconcile(first.pi, ctxFor(s), deps(vps, "vps:2"));
    const again = harness();
    for (const who of ["vps:2", "mac:9", "vps:4"]) await reconcile(again.pi, ctxFor(s), deps(vps, who));
    expect(first.sent).toHaveLength(1);
    expect(again.sent).toHaveLength(0);
  });

  test("delayed and out-of-order hooks cannot overwrite a newer turn or a terminal state", async () => {
    const s = sid();
    const old = await start(mac, s, "mac:1");
    const next = await start(mac, s, "mac:1");
    expect(next.generation).toBe(old.generation + 1);
    expect(await mac.transition(old, "completed", 5)).toBe(false);
    expect(await mac.heartbeat(old, [])).toBe(false);
    expect(await mac.transition(next, "awaiting_input", 2)).toBe(true);
    expect(await mac.transition(next, "running", 1)).toBe(false);
    expect(await mac.transition(next, "completed", 3)).toBe(true);
    expect(await mac.transition(next, "running", 9)).toBe(false);
    expect((await row(s)).state).toBe("completed");
  });

  test("a stale owner cannot touch a turn another machine took over", async () => {
    const s = sid();
    const f = await start(mac, s, "mac:1");
    await crash(s);
    const taken = (await vps.claimRecovery((await vps.latest(s))!, "vps:2"))!;
    expect(await mac.transition(f, "completed", 9)).toBe(false);
    expect(await mac.heartbeat(f, [])).toBe(false);
    expect(taken.generation).toBe(f.generation + 1);
  });

  test("a stale read cannot claim a turn another machine already took, even after that lease lapsed again", async () => {
    const s = sid();
    await start(mac, s, "mac:1");
    await crash(s);
    const staleRead = (await vps.latest(s))!;
    await mac.claimRecovery((await mac.latest(s))!, "mac:9");
    await crash(s); // the first claimer dies before acking; its lease is already stale again
    expect(await vps.claimRecovery(staleRead, "vps:2")).toBeUndefined();
    expect((await row(s)).owner_id).toBe("mac:9");
  });

  test("completion before the stop record: the transcript closes the turn without restarting it", async () => {
    const s = sid();
    await start(mac, s, "mac:1");
    await crash(s);
    const h = harness();
    const out = await reconcile(h.pi, ctxFor(s, [finalAnswer(Date.now() + 1000)]), deps(vps, "vps:2"));
    expect(out).toMatchObject({ decision: "close", reason: "transcript-shows-completion" });
    expect(h.sent).toHaveLength(0);
    expect((await row(s)).state).toBe("completed");
  });

  test("crash after send, before ack: the transcript proves delivery, so nothing is re-sent", async () => {
    const s = sid();
    const f = await start(mac, s, "mac:1");
    await crash(s);
    await vps.claimRecovery((await vps.latest(s))!, "vps:2"); // intent durable, then the process dies before ackRecovery
    await crash(s);
    const delivered = [{ type: "custom_message", customType: RECOVERY_CUSTOM_TYPE, details: { turnId: f.turnId } }];
    const h = harness();
    const out = await reconcile(h.pi, ctxFor(s, delivered), deps(mac, "mac:9"));
    expect(out).toMatchObject({ decision: "ack", reason: "recovery-message-in-transcript" });
    expect(h.sent).toHaveLength(0);
    expect((await row(s)).state).toBe("recovered");
  });

  test("a send that throws is surfaced and never acked; the next pass re-checks the transcript before any re-send", async () => {
    const s = sid();
    await start(mac, s, "mac:1");
    await crash(s);
    let published = "";
    const failing = { sendMessage: () => { throw new Error("harness refused"); } };
    const out = await reconcile(failing, ctxFor(s), deps(vps, "vps:2", (_state, message) => (published = message)));
    expect(out).toMatchObject({ decision: "unknown", reason: "send-failed" });
    expect(published).toContain("not delivered");
    const stuck = await row(s);
    expect(stuck.state).toBe("recovering");
    expect(stuck.recovery_acked_at).toBeNull();
    await crash(s);
    const h = harness();
    expect((await reconcile(h.pi, ctxFor(s), deps(mac, "mac:9"))).decision).toBe("recovered");
    expect(h.sent).toHaveLength(1);
  });

  test("tools in flight at the crash are named in the notice with their side-effect risk, and nothing is replayed", async () => {
    const s = sid();
    const f = await start(mac, s, "mac:1");
    await mac.heartbeat(f, [
      { toolCallId: "r1", toolName: "read", startedAtMs: 1, idempotent: true },
      { toolCallId: "b1", toolName: "bash", startedAtMs: 2, idempotent: false },
    ]);
    await crash(s);
    const h = harness();
    await reconcile(h.pi, ctxFor(s), deps(vps, "vps:2"));
    const text = String(h.sent[0]!.payload.content);
    expect(text).toContain("- read (r1)\n");
    expect(text).toContain("- bash (b1) [may have side effects]");
    expect(h.sent[0]!.options).toEqual({ triggerTurn: true, deliverAs: "nextTurn" });
    expect(h.sent).toHaveLength(1);
  });

  test("crash after send, message never landed: one more attempt, marked as a re-send", async () => {
    const s = sid();
    await start(mac, s, "mac:1");
    await crash(s);
    await vps.claimRecovery((await vps.latest(s))!, "vps:2");
    await crash(s);
    const h = harness();
    const out = await reconcile(h.pi, ctxFor(s), deps(mac, "mac:9"));
    expect(out.decision).toBe("recovered");
    expect(String(h.sent[0]!.payload.content)).toContain("An earlier notice for it may not have arrived");
  });

  test("recovery that keeps failing stops at the attempt cap and asks for a person", async () => {
    const s = sid();
    await start(mac, s, "mac:1");
    for (let i = 0; i < 2; i++) {
      await crash(s);
      await vps.claimRecovery((await vps.latest(s))!, `vps:${i}`);
    }
    await crash(s);
    let published = "";
    const h = harness();
    const out = await reconcile(h.pi, ctxFor(s), deps(mac, "mac:9", (_state, message) => (published = message)));
    expect(out).toMatchObject({ decision: "attention", reason: "recovery-attempts-exhausted" });
    expect(h.sent).toHaveLength(0);
    expect(published).toContain("needs attention");
    expect((await row(s)).state).toBe("needs_attention");
  });

  test("neon outage: an explicit unknown, no message, no fabricated success; recovery works once it is back", async () => {
    const s = sid();
    await start(mac, s, "mac:1");
    await crash(s);
    const dead = new TurnStore("postgres://postgres@127.0.0.1:1/none");
    let published = "";
    const h = harness();
    const out = await reconcile(h.pi, ctxFor(s), deps(dead, "vps:2", (_state, message) => (published = message)));
    expect(out.decision).toBe("unknown");
    expect(published).toContain("Neon unreachable");
    expect(h.sent).toHaveLength(0);
    expect((await row(s)).state).toBe("running");
    const after = harness();
    expect((await reconcile(after.pi, ctxFor(s), deps(vps, "vps:2"))).decision).toBe("recovered");
    expect(after.sent).toHaveLength(1);
  });

  test("a transcript that cannot be read is surfaced, never guessed", async () => {
    const s = sid();
    await start(mac, s, "mac:1");
    await crash(s);
    const h = harness();
    const out = await reconcile(h.pi, { hasUI: true, sessionManager: { getSessionId: () => s } }, deps(vps, "vps:2"));
    expect(out).toMatchObject({ decision: "attention", reason: "transcript-unreadable" });
    expect(h.sent).toHaveLength(0);
  });

  test("every decision lands in the audit trail", async () => {
    const s = sid();
    await start(mac, s, "mac:1");
    await crash(s);
    await reconcile(harness().pi, ctxFor(s), deps(vps, "vps:2"));
    const events = await vps.events(s);
    expect(events.map((e) => e.decision)).toContain("recovered");
    expect(events[0]!.actor).toBe("vps:2");
  });
});

describe("pure rules", () => {
  const base = { turnId: "t", sessionId: "s", paneId: null, ownerId: "mac:1", ownerHost: "mac", generation: 1, state: "running" as const, heartbeatMs: 0, nowMs: LEASE_MS * 2, recoveryAttempts: 0, recoverySentMs: null, recoveryAckedMs: null, pendingTools: [] };
  const unfinished = { transcript: "unfinished" as const, recoveryMessageInTranscript: false };

  test("a process never recovers its own live turn", () => {
    expect(decide(base, unfinished, "mac:1")).toMatchObject({ kind: "skip", reason: "own-turn" });
  });
  test("the lease boundary is exclusive of live", () => {
    expect(decide({ ...base, nowMs: LEASE_MS - 1 }, unfinished, "vps:2").kind).toBe("wait");
    expect(decide({ ...base, nowMs: LEASE_MS }, unfinished, "vps:2").kind).toBe("recover");
  });
  test("unknown tools fail closed as non-idempotent; only observers replay", () => {
    expect(isIdempotentTool("read")).toBe(true);
    expect(isIdempotentTool("bash")).toBe(false);
    expect(isIdempotentTool("mcp_deploy_prod")).toBe(false);
    expect(isIdempotentTool("constructor")).toBe(false);
  });
  test("stop reasons map to terminal states", () => {
    expect(terminalStateForStop("stop")).toBe("completed");
    expect(terminalStateForStop("aborted")).toBe("cancelled");
    expect(terminalStateForStop("error")).toBe("failed");
    expect(terminalStateForStop(undefined)).toBe("failed");
  });
  test("a final answer older than the turn start does not count as completion", () => {
    expect(readEvidence([finalAnswer(100)], "t", 5000).transcript).toBe("unfinished");
    expect(readEvidence([finalAnswer(9000)], "t", 5000).transcript).toBe("completed");
  });
  test("the notice discloses unknown outcomes and grants no authority", () => {
    const text = recoveryMessage({ turnId: "t", ownerHost: "mac", pendingTools: [{ toolCallId: "c", toolName: "bash", startedAtMs: 1, idempotent: false }] }, false);
    expect(text).toContain("adds no authority");
    expect(text).toContain("UNKNOWN outcomes");
    expect(text).toContain("Do not repeat a write, push, deploy");
  });
});
