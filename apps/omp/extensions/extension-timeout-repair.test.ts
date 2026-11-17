// A handler timeout must warn the user and start exactly one repair `omp -p` session; nothing else may.
// The spawn-failure and nested-run cases are the faults: both must stay quiet about a session that never started.
import { afterAll, expect, test } from "bun:test";
import type { ChildProcess } from "node:child_process";
import { EventEmitter } from "node:events";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import install, { COOLDOWN_MS, handleSettled, repairPrompt } from "./extension-timeout-repair.ts";

const dir = await mkdtemp(path.join(tmpdir(), "timeout-repair-"));
process.env.OMP_EXTENSION_TIMEOUT_REPAIR_DIR = dir;
delete process.env.OMP_NESTED_RUN;
afterAll(() => rm(dir, { recursive: true, force: true }));

const timeout = {
  extensionPath: "/x/onStop.ts",
  handledEvent: "session_stop",
  durationMs: 30_000,
  outcome: "timeout" as const,
  timeoutMs: 30_000,
  error: "handler timed out after 30000ms",
};

function harness() {
  const spawned: { prompt: string; log: string; cwd: string }[] = [];
  const notices: { text: string; level: string }[] = [];
  const spawner = (prompt: string, log: string, cwd: string) => {
    spawned.push({ prompt, log, cwd });
    return Object.assign(new EventEmitter(), { unref() {} }) as unknown as ChildProcess;
  };
  const ctx = { cwd: "/work", ui: { notify: (text: string, level: string) => notices.push({ text, level }) } };
  return { spawned, notices, spawner, ctx };
}

test("a timeout warns the user and starts one repair session carrying the cause", () => {
  const h = harness();
  const r = handleSettled(timeout, h.ctx, h.spawner, () => 1_000);
  expect(r.started).toBe(true);
  expect(h.spawned).toHaveLength(1);
  expect(h.spawned[0].cwd).toBe("/work");
  expect(h.spawned[0].prompt).toContain("/x/onStop.ts");
  expect(h.spawned[0].prompt).toContain("session_stop");
  expect(h.notices).toHaveLength(1);
  expect(h.notices[0].level).toBe("warning");
  expect(h.notices[0].text).toContain("starting an automatic repair session in the background");
});

test("the same handler timing out again within the cooldown does not start a second session", () => {
  const h = harness();
  const t0 = 5_000_000;
  const ev = { ...timeout, handledEvent: "agent_end" };
  handleSettled(ev, h.ctx, h.spawner, () => t0);
  expect(handleSettled(ev, h.ctx, h.spawner, () => t0 + COOLDOWN_MS - 1)).toEqual({
    started: false,
    reason: "cooldown",
  });
  expect(handleSettled(ev, h.ctx, h.spawner, () => t0 + COOLDOWN_MS).started).toBe(true);
  expect(h.spawned).toHaveLength(2);
});

test("ok and error outcomes start nothing", () => {
  const h = harness();
  for (const outcome of ["ok", "error"] as const) {
    expect(handleSettled({ ...timeout, handledEvent: "input", outcome }, h.ctx, h.spawner).started).toBe(false);
  }
  expect(h.spawned).toHaveLength(0);
  expect(h.notices).toHaveLength(0);
});

test("a timeout inside a repair session does not start another repair session", () => {
  const h = harness();
  process.env.OMP_NESTED_RUN = "1";
  try {
    expect(handleSettled({ ...timeout, handledEvent: "nested_case" }, h.ctx, h.spawner)).toEqual({
      started: false,
      reason: "nested",
    });
  } finally {
    delete process.env.OMP_NESTED_RUN;
  }
  expect(h.spawned).toHaveLength(0);
  expect(h.notices).toHaveLength(0);
});

test("a failed spawn says the session failed to start and never claims one started", () => {
  const h = harness();
  const r = handleSettled({ ...timeout, handledEvent: "spawn_fail" }, h.ctx, () => {
    throw new Error("ENOENT omp");
  });
  expect(r).toEqual({ started: false, reason: "spawn-failed" });
  expect(h.notices).toHaveLength(1);
  expect(h.notices[0].text).toContain("failed to start");
  expect(h.notices[0].text).not.toContain("starting an automatic repair session");
});

test("the extension subscribes to extension_handler_settled and the prompt forbids raising the limit", () => {
  const names: string[] = [];
  install({ on: name => names.push(name) });
  expect(names).toEqual(["extension_handler_settled"]);
  expect(repairPrompt(timeout, "/log")).toContain("Do not raise the limit");
});
