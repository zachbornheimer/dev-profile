// The probe's handlers must return inside omp's 2 s session_shutdown limit even though the probe measures a 3 s wait.
import { expect, test } from "bun:test";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import install from "./fed-probe-ext.ts";

const OMP_SHUTDOWN_LIMIT_MS = 2000;

test("every probe handler settles well inside the shutdown limit and logs its start", async () => {
  const dir = mkdtempSync(path.join(tmpdir(), "fed-probe-"));
  const logPath = path.join(dir, "probe.log");
  process.env.FED_PROBE_LOG = logPath;
  try {
    const handlers = new Map<string, (event: unknown, ctx: unknown) => unknown>();
    install({ on: (event, handler) => void handlers.set(event, handler) });

    expect([...handlers.keys()]).toContain("session_shutdown");
    for (const [event, handler] of handlers) {
      const begun = Date.now();
      await handler({}, { mode: "print" });
      expect(Date.now() - begun, `${event} handler held the host`).toBeLessThan(OMP_SHUTDOWN_LIMIT_MS / 4);
    }
    const lines = readFileSync(logPath, "utf8").trim().split("\n").map((l) => JSON.parse(l));
    expect(lines.map((l) => l.at)).toContain("session_shutdown:start");
  } finally {
    delete process.env.FED_PROBE_LOG;
    rmSync(dir, { recursive: true, force: true });
  }
});
