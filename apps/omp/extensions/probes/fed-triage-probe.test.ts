// The triage probe's session_stop handler must return while its inquiries are still pending: they run for minutes,
// omp's session_stop limit is 30 s. Gates stand in for the slow model calls, so no wall-clock time is involved.
import { expect, test } from "bun:test";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import install, { type Loaded } from "./fed-triage-probe.ts";

type Handler = (event: unknown, ctx: unknown) => unknown;

async function flushMicrotasks(): Promise<void> {
  for (let i = 0; i < 50; i++) await Promise.resolve();
}

function withLog(fn: (logPath: string) => Promise<void>): Promise<void> {
  const dir = mkdtempSync(path.join(tmpdir(), "fed-triage-"));
  process.env.FED_TRIAGE_LOG = path.join(dir, "triage.log");
  return fn(process.env.FED_TRIAGE_LOG).finally(() => {
    delete process.env.FED_TRIAGE_LOG;
    rmSync(dir, { recursive: true, force: true });
  });
}

function sessionStopHandler(load: () => Promise<Loaded>): Handler {
  let handler: Handler | undefined;
  install({
    on: (event, h) => {
      if (event === "session_stop") handler = h;
    },
  }, load);
  if (!handler) throw new Error("probe registered no session_stop handler");
  return handler;
}

test("session_stop returns while the inquiries are pending and each run logs when it finishes", () =>
  withLog(async (logPath) => {
    const gates = [1, 2, 3].map(() => Promise.withResolvers<void>());
    let call = 0;
    const loaded: Loaded = {
      questions: [],
      withInquiry: () => ({
        inquiry: async <T>() => {
          await gates[call++]!.promise;
          return { verdict: "supersedes" } as T;
        },
      }),
    };
    const handler = sessionStopHandler(async () => loaded);

    const outcome = await Promise.race([
      Promise.resolve(handler({}, {})).then(() => "returned"),
      flushMicrotasks().then(() => "held the host"),
    ]);
    expect(outcome).toBe("returned");
    await flushMicrotasks();
    expect(call).toBe(1);

    for (const gate of gates) {
      gate.resolve();
      await flushMicrotasks();
    }
    const lines = readFileSync(logPath, "utf8").trim().split("\n").map((l) => JSON.parse(l));
    expect(lines.map((l) => l.run)).toEqual([1, 2, 3]);
  }));

test("a failing load is logged and does not reject the handler", () =>
  withLog(async (logPath) => {
    const handler = sessionStopHandler(async () => {
      throw new Error("no host runtime");
    });
    await handler({}, {});
    await flushMicrotasks();
    expect(readFileSync(logPath, "utf8")).toContain("no host runtime");
  }));
