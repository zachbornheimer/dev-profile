// Drives wire() with a fake omp event source against real Postgres: the hook -> registry path that
// recovery.test.ts does not cover. TURN_RECOVERY_TEST_DB selects the scratch database; without it
// every case skips.
import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { SQL } from "bun";
import register, { wire, type Ctx, type OmpApi, type WireOptions } from "./index.ts";
import { RECOVERY_CUSTOM_TYPE } from "./recovery.ts";
import { TurnStore } from "./store.ts";

const DB = process.env.TURN_RECOVERY_TEST_DB;
const run = DB ? describe : describe.skip;

type Listener = (event: Record<string, unknown>, ctx: Ctx) => unknown;

/** A stand-in for omp's extension API: records registrations and lets the test raise lifecycle events. */
function fakeOmp() {
  const listeners = new Map<string, Listener[]>();
  const sent: { payload: Record<string, unknown>; options: unknown }[] = [];
  const bus: { channel: string; data: unknown }[] = [];
  const pi: OmpApi = {
    on: (name, handler) => void listeners.set(name, [...(listeners.get(name) ?? []), handler]),
    sendMessage: (payload, options) => void sent.push({ payload, options }),
    events: { emit: (channel, data) => void bus.push({ channel, data }) },
  };
  const raise = async (name: string, event: Record<string, unknown>, ctx: Ctx) => {
    for (const handler of listeners.get(name) ?? []) await handler(event, ctx);
  };
  return { pi, sent, bus, raise, registered: () => [...listeners.values()].flat().length };
}

const ctxFor = (sessionId: string, entries: unknown[] = []): Ctx => ({ hasUI: true, sessionManager: { getSessionId: () => sessionId, getEntries: () => entries } });

run("wire(): omp hooks to the registry", () => {
  let store: TurnStore;
  let other: TurnStore;
  let admin: SQL;
  let n = 0;
  const sid = () => `wire-${Date.now()}-${n++}`;
  const opts = (ownerId: string, extra: Partial<WireOptions> = {}): WireOptions => ({ ownerId, host: ownerId.split(":")[0]!, paneId: "w1:p1", confirm: async () => {}, ...extra });
  const row = async (sessionId: string) => (await admin.unsafe(`SELECT * FROM herder_turns WHERE session_id = $1 ORDER BY generation DESC LIMIT 1`, [sessionId]))[0];
  const expire = (sessionId: string) => admin.unsafe(`UPDATE herder_turns SET heartbeat_at = now() - interval '5 minutes' WHERE session_id = $1`, [sessionId]);
  const agentEnd = (stopReason: string, extra: Record<string, unknown> = {}) => ({ type: "agent_end", messages: [{ role: "assistant", stopReason }], ...extra });

  beforeAll(async () => {
    store = new TurnStore(DB!);
    other = new TurnStore(DB!);
    admin = new SQL(DB!);
    await store.migrate();
  });
  afterAll(async () => {
    await store.close();
    await other.close();
    await admin.close();
  });

  test("a normal turn is recorded start to finish and never looks interrupted", async () => {
    const s = sid();
    const omp = fakeOmp();
    const w = wire(omp.pi, store, opts("mac:1"));
    await omp.raise("agent_start", {}, ctxFor(s));
    await omp.raise("tool_execution_start", { toolCallId: "t1", toolName: "bash" }, ctxFor(s));
    await w.idle(); // no heartbeat tick: the side-effecting tool was flushed when it started
    expect((await row(s)).state).toBe("running");
    expect((await row(s)).pending_tools).toEqual([expect.objectContaining({ toolCallId: "t1", toolName: "bash", idempotent: false })]);
    await omp.raise("tool_execution_end", { toolCallId: "t1", toolName: "bash" }, ctxFor(s));
    await omp.raise("agent_end", agentEnd("stop"), ctxFor(s));
    await w.idle();
    expect((await row(s)).state).toBe("completed");
  });

  test("agent_end raised the instant after agent_start still closes the turn (write order is preserved)", async () => {
    const s = sid();
    const omp = fakeOmp();
    const w = wire(omp.pi, store, opts("mac:1"));
    await omp.raise("agent_start", {}, ctxFor(s));
    await omp.raise("agent_end", agentEnd("stop"), ctxFor(s));
    await w.idle();
    expect((await row(s)).state).toBe("completed");
  });

  test("terminal reasons map to completed, cancelled and failed", async () => {
    for (const [reason, state] of [["stop", "completed"], ["aborted", "cancelled"], ["error", "failed"]] as const) {
      const s = sid();
      const omp = fakeOmp();
      const w = wire(omp.pi, store, opts("mac:1"));
      await omp.raise("agent_start", {}, ctxFor(s));
      await omp.raise("agent_end", agentEnd(reason), ctxFor(s));
      await w.idle();
      expect((await row(s)).state).toBe(state);
    }
  });

  test("an agent_end that is not a settle leaves the turn running", async () => {
    const s = sid();
    const omp = fakeOmp();
    const w = wire(omp.pi, store, opts("mac:1"));
    await omp.raise("agent_start", {}, ctxFor(s));
    await omp.raise("agent_end", agentEnd("stop", { willContinue: true }), ctxFor(s));
    await omp.raise("agent_end", agentEnd("stop", { awaitingAsyncWork: true }), ctxFor(s));
    await w.idle();
    expect((await row(s)).state).toBe("running");
  });

  test("waiting on the ask tool marks the turn awaiting_input, and a crash there is not resumed", async () => {
    const s = sid();
    const omp = fakeOmp();
    const w = wire(omp.pi, store, opts("mac:1"));
    await omp.raise("agent_start", {}, ctxFor(s));
    await omp.raise("tool_execution_start", { toolCallId: "q1", toolName: "ask" }, ctxFor(s));
    await w.idle();
    expect((await row(s)).state).toBe("awaiting_input");
    await expire(s);
    const next = fakeOmp();
    const w2 = wire(next.pi, other, opts("vps:2"));
    await next.raise("session_start", {}, ctxFor(s));
    await w2.idle();
    expect(next.sent).toHaveLength(0);
    expect((await row(s)).state).toBe("awaiting_input");
  });

  test("Ctrl-C or /quit mid-turn records stopped, so the next start does not resume it", async () => {
    const s = sid();
    const omp = fakeOmp();
    wire(omp.pi, store, opts("mac:1"));
    await omp.raise("agent_start", {}, ctxFor(s));
    await omp.raise("session_shutdown", { type: "session_shutdown" }, ctxFor(s));
    expect((await row(s)).state).toBe("stopped");
    await expire(s);
    const next = fakeOmp();
    const w2 = wire(next.pi, other, opts("vps:2"));
    await next.raise("session_start", {}, ctxFor(s));
    await w2.idle();
    expect(next.sent).toHaveLength(0);
  });

  test("end to end: a crashed turn is resumed by the next session on another system, exactly once", async () => {
    const s = sid();
    const crashed = fakeOmp();
    const wc = wire(crashed.pi, store, opts("mac:1"));
    await crashed.raise("agent_start", {}, ctxFor(s));
    await crashed.raise("tool_execution_start", { toolCallId: "w1", toolName: "write" }, ctxFor(s));
    // No agent_end, no session_shutdown: the process is gone. The write was flushed at tool start,
    // with no heartbeat tick, and its lease then lapses.
    await wc.idle();
    await expire(s);
    const results = [];
    for (const who of ["vps:2", "mac:9", "vps:3"]) {
      const next = fakeOmp();
      const w = wire(next.pi, other, opts(who));
      await next.raise("session_start", {}, ctxFor(s));
      await w.idle();
      results.push(next.sent);
    }
    expect(results.flat()).toHaveLength(1);
    const { payload, options } = results.flat()[0]!;
    expect(payload.customType).toBe(RECOVERY_CUSTOM_TYPE);
    expect(payload.attribution).toBe("agent");
    expect(String(payload.content)).toContain("write (w1) [may have side effects]");
    expect(options).toEqual({ triggerTurn: true, deliverAs: "nextTurn" });
    expect((await row(s)).state).toBe("recovered");
  });

  test("a recovery turn that starts straight after the notice is recorded after the recovery, not before", async () => {
    const s = sid();
    const crashed = fakeOmp();
    const wc = wire(crashed.pi, store, opts("mac:1"));
    await crashed.raise("agent_start", {}, ctxFor(s));
    await wc.idle();
    await expire(s);
    const next = fakeOmp();
    const w = wire(next.pi, other, opts("vps:2"));
    await next.raise("session_start", {}, ctxFor(s));
    await w.idle();
    await next.raise("agent_start", {}, ctxFor(s)); // the triggered recovery turn
    await next.raise("agent_end", agentEnd("stop"), ctxFor(s));
    await w.idle();
    const rows = await admin.unsafe(`SELECT state FROM herder_turns WHERE session_id = $1 ORDER BY generation`, [s]);
    expect(rows.map((r: { state: string }) => r.state)).toEqual(["recovered", "completed"]);
  });

  test("a turn another system took over learns it at its next heartbeat and stops writing", async () => {
    const s = sid();
    const omp = fakeOmp();
    const w = wire(omp.pi, store, opts("mac:1"));
    await omp.raise("agent_start", {}, ctxFor(s));
    await w.idle();
    await expire(s);
    await other.claimRecovery((await other.latest(s))!, "vps:2");
    await w.heartbeatNow();
    await w.idle();
    expect(omp.bus).toContainEqual({ channel: "herdr:blocked", data: { active: true, label: "this turn was taken over by another system" } });
    await omp.raise("agent_end", agentEnd("stop"), ctxFor(s));
    await w.idle();
    expect((await row(s)).state).toBe("recovering"); // the stale owner's late stop did not land
  });

  test("once a turn is taken over, the old process stops writing for it altogether", async () => {
    const s = sid();
    const omp = fakeOmp();
    let heartbeats = 0;
    let transitions = 0;
    const counted = new Proxy(store, {
      get(target, prop, receiver) {
        const value = Reflect.get(target, prop, receiver);
        if (prop === "heartbeat") return (...args: unknown[]) => (heartbeats++, (value as (...a: unknown[]) => unknown).apply(target, args));
        if (prop === "transition") return (...args: unknown[]) => (transitions++, (value as (...a: unknown[]) => unknown).apply(target, args));
        return typeof value === "function" ? value.bind(target) : value;
      },
    });
    const w = wire(omp.pi, counted, opts("mac:1"));
    await omp.raise("agent_start", {}, ctxFor(s));
    await w.idle();
    await expire(s);
    await other.claimRecovery((await other.latest(s))!, "vps:2");
    await w.heartbeatNow(); // refused: the fence is gone
    await w.idle();
    const beatsAfterTakeover = heartbeats;
    await w.heartbeatNow();
    await omp.raise("tool_execution_start", { toolCallId: "x1", toolName: "bash" }, ctxFor(s));
    await omp.raise("agent_end", agentEnd("stop"), ctxFor(s));
    await w.idle();
    expect(heartbeats).toBe(beatsAfterTakeover);
    expect(transitions).toBe(0);
  });

  test("a hung registry never blocks the turn, and the queue recovers when it answers again", async () => {
    const s = sid();
    const omp = fakeOmp();
    const hung = new Proxy(store, {
      get(target, prop, receiver) {
        if (prop === "begin") return () => new Promise(() => {});
        return Reflect.get(target, prop, receiver);
      },
    });
    const w = wire(omp.pi, hung, opts("mac:1", { opTimeoutMs: 50 }));
    await omp.raise("agent_start", {}, ctxFor(s)); // returns at once; the write is queued
    await w.idle(); // the stuck write times out instead of wedging the lane
    await omp.raise("agent_end", agentEnd("stop"), ctxFor(s));
    await w.idle();
    expect(await row(s)).toBeUndefined();
  });

  test("with Neon down at start, the pane shows unknown and recovery runs once Neon returns", async () => {
    const s = sid();
    const crashed = fakeOmp();
    const wc = wire(crashed.pi, store, opts("mac:1"));
    await crashed.raise("agent_start", {}, ctxFor(s));
    await wc.idle(); // the begin must land before the lease is expired, or the row is born fresh
    await expire(s);
    const next = fakeOmp();
    const dead = new TurnStore("postgres://postgres@127.0.0.1:1/none");
    const w = wire(next.pi, dead, opts("vps:2"));
    await next.raise("session_start", {}, ctxFor(s));
    await w.idle();
    expect(next.sent).toHaveLength(0);
    expect(next.bus.at(-1)).toEqual({ channel: "herdr:blocked", data: { active: true, label: "turn state unknown: Neon unreachable" } });
    const back = fakeOmp();
    const w2 = wire(back.pi, other, opts("vps:2"));
    await back.raise("session_start", {}, ctxFor(s));
    await w2.idle();
    expect(back.sent).toHaveLength(1);
  });

  test("without a database URL the extension registers nothing and touches nothing", () => {
    const omp = fakeOmp();
    const saved = process.env.SESSIONS_DB_URL;
    delete process.env.SESSIONS_DB_URL;
    try {
      register(omp.pi);
    } finally {
      if (saved !== undefined) process.env.SESSIONS_DB_URL = saved;
    }
    expect(omp.registered()).toBe(0);
    expect(omp.sent).toHaveLength(0);
  });
});
