import { describe, expect, it } from "bun:test";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import install, {
  admit,
  failureMessage,
  type HandlerSettled,
  LEARN_COOLDOWN_MS,
  mayLearn,
  spawnLearner,
  timingRecord,
} from "./handler-timing.ts";

const SESSION = "01a1e5c6-e2d3-74a7-b171-a8361201dfb4";
const timeout: HandlerSettled = {
  extensionPath: "/home/z/.omp/agent/extensions/agent-checkpoint-publish.ts",
  handledEvent: "agent_end",
  durationMs: 30_002,
  outcome: "timeout",
  timeoutMs: 30_000,
  error: "handler timed out after 30000ms",
};
const ctx = { sessionManager: { getSessionFile: () => `/s/2026_${SESSION}.jsonl`, getSessionId: () => SESSION } };

function fakeLaunch() {
  const calls: { command: string; args: string[]; options: Record<string, unknown> }[] = [];
  const launch = (command: string, args: string[], options: Record<string, unknown>) => {
    calls.push({ command, args, options });
    return { on: () => undefined, unref: () => undefined };
  };
  return { calls, launch };
}

describe("handler-timing", () => {
  it("hands /learn the failure text omp shows, for the current session", () => {
    const { calls, launch } = fakeLaunch();
    const result = spawnLearner(timeout, ctx, {}, launch);
    expect(result).toEqual({ started: true, source: `omp:${SESSION}` });
    expect(calls).toHaveLength(1);
    expect(calls[0].command).toBe("omp");
    const prompt = calls[0].args[1];
    expect(prompt).toContain(`omp:${SESSION}`);
    expect(prompt).toContain(
      "Extension \\\"/home/z/.omp/agent/extensions/agent-checkpoint-publish.ts\\\" error: handler timed out after 30000ms",
    );
    expect(failureMessage(timeout)).toContain("handler timed out after 30000ms");
  });

  it("refuses without a session instead of guessing one", () => {
    const { calls, launch } = fakeLaunch();
    const result = spawnLearner(timeout, { sessionManager: { getSessionFile: () => undefined } }, {}, launch);
    expect(result.started).toBe(false);
    expect(calls).toHaveLength(0);
  });

  it("starts one learner per extension+event per cooldown window", () => {
    const last = new Map<string, number>();
    expect(admit(last, timeout, 1_000)).toBe(true);
    expect(admit(last, timeout, 1_000 + LEARN_COOLDOWN_MS - 1)).toBe(false);
    expect(admit(last, { ...timeout, handledEvent: "session_stop" }, 2_000)).toBe(true);
    expect(admit(last, timeout, 1_000 + LEARN_COOLDOWN_MS)).toBe(true);
  });

  it("never learns from inside a learner or when switched off", () => {
    expect(mayLearn({})).toBe(true);
    expect(mayLearn({ LEARNER: "1" })).toBe(false);
    expect(mayLearn({ OMP_NESTED_RUN: "1" })).toBe(false);
    expect(mayLearn({ OMP_HANDLER_TIMEOUT_LEARN: "0" })).toBe(false);
  });

  it("flags slow and failed handlers in the timing record, not fast ok ones", () => {
    expect(timingRecord({ ...timeout, outcome: "ok", durationMs: 40 }, SESSION).slow).toBeUndefined();
    expect(timingRecord({ ...timeout, outcome: "ok", durationMs: 1_500 }, SESSION).slow).toBe(true);
    expect(timingRecord(timeout, SESSION)).toMatchObject({
      slow: true,
      outcome: "timeout",
      duration_ms: 30_002,
      session_id: SESSION,
    });
  });

  it("logs every settled handler", () => {
    const dir = mkdtempSync(join(tmpdir(), "handler-timing-"));
    process.env.OMP_HOOKS_LOG_DIR = dir;
    process.env.OMP_HANDLER_TIMEOUT_LEARN = "0";
    try {
      let handler: ((e: HandlerSettled, c: typeof ctx) => unknown) | undefined;
      install({ on: (_name, h) => void (handler = h as typeof handler) });
      handler?.({ ...timeout, outcome: "ok", durationMs: 12 }, ctx);
      handler?.(timeout, ctx);
    } finally {
      delete process.env.OMP_HOOKS_LOG_DIR;
      delete process.env.OMP_HANDLER_TIMEOUT_LEARN;
    }
    const lines = Bun.JSONL.parse(readFileSync(join(dir, "handler-timings.jsonl"), "utf8")) as Array<
      Record<string, unknown>
    >;
    expect(lines.map(l => [l.event, l.outcome, l.duration_ms])).toEqual([
      ["agent_end", "ok", 12],
      ["agent_end", "timeout", 30_002],
    ]);
  });
});
