// The sweep takes minutes; the session_stop handler must return inside omp's 30 s limit regardless.
import { expect, test } from "bun:test";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import install, { type ProbeModules } from "./fed-effort-probe.ts";

const HANDLER_BUDGET_MS = 500;

test("session_stop returns immediately while the model sweep is still running", async () => {
  const dir = mkdtempSync(path.join(tmpdir(), "fed-effort-"));
  process.env.FED_EFFORT_LOG = path.join(dir, "effort.log");
  try {
    let handler: ((event: unknown, ctx: never) => unknown) | undefined;
    install({ on: (_event, h) => void (handler = h) }, () => new Promise<ProbeModules>(() => {})); // loader never settles
    expect(handler).toBeDefined();
    const begun = Date.now();
    await handler?.({}, {} as never);
    expect(Date.now() - begun).toBeLessThan(HANDLER_BUDGET_MS);
  } finally {
    delete process.env.FED_EFFORT_LOG;
    rmSync(dir, { recursive: true, force: true });
  }
});

test("a sweep failure is logged by the detached task", async () => {
  const dir = mkdtempSync(path.join(tmpdir(), "fed-effort-"));
  const logPath = path.join(dir, "effort.log");
  process.env.FED_EFFORT_LOG = logPath;
  try {
    let handler: ((event: unknown, ctx: never) => unknown) | undefined;
    install({ on: (_event, h) => void (handler = h) }, () => Promise.reject(new Error("load boom")));
    await handler?.({}, {} as never);
    for (let turn = 0; turn < 50; turn++) await Promise.resolve(); // drain microtasks so the rejected loader's handler runs
    expect(readFileSync(logPath, "utf8")).toContain("load boom");
  } finally {
    delete process.env.FED_EFFORT_LOG;
    rmSync(dir, { recursive: true, force: true });
  }
});
