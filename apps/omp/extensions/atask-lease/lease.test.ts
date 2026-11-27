import { afterEach, describe, expect, test } from "bun:test";
import { createHash } from "node:crypto";
import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { type LeaseContext, type LeaseReport, type LeaseTimer, registerLease, renewRuntime } from "./index";
import { Registry } from "./registry";

const stops: (() => void)[] = [];
const scratch: string[] = [];
const originalRoot = process.env.ATASK_RUNTIME_ROOT;
afterEach(() => {
  for (const stop of stops.splice(0)) stop();
  for (const path of scratch.splice(0)) rmSync(path, { recursive: true, force: true });
  if (originalRoot === undefined) delete process.env.ATASK_RUNTIME_ROOT;
  else process.env.ATASK_RUNTIME_ROOT = originalRoot;
});
const flush = async () => {
  await Promise.resolve();
  await Promise.resolve();
};
function registrationPath(root: string, session: string) {
  return join(root, `${createHash("sha256").update(session).digest("hex")}.json`);
}
function record(root: string, session: string) {
  return JSON.parse(readFileSync(registrationPath(root, session), "utf8"));
}
function harness(
  renew: (owner: { session: string; cwd: string }, root: string) => Promise<number> = async () => 1,
  registry = new Registry(),
) {
  const handlers = new Map<string, (event: unknown, ctx: LeaseContext) => void>();
  const timers = new Map<LeaseTimer, () => void>();
  const periods: number[] = [];
  const reports: LeaseReport[] = [];
  let next = 0;
  const context = (session = "first", hasUI = true, kind = "main"): LeaseContext => ({
    cwd: "/same-cwd",
    hasUI,
    agent: { kind },
    sessionManager: { getSessionId: () => session },
    setInterval(fn, ms) {
      const id = ++next as unknown as LeaseTimer;
      timers.set(id, fn);
      periods.push(ms);
      return id;
    },
    clearTimer(id) {
      timers.delete(id);
    },
  });
  const stop = registerLease({
    on: (event, handler) => {
      handlers.set(event, handler);
    },
  }, {
    registry,
    renew,
    report: event => reports.push(event),
  });
  stops.push(stop);
  const emit = (event: string, ctx = context()) => handlers.get(event)!({}, ctx);
  const tick = async () => {
    for (const fn of [...timers.values()]) fn();
    await flush();
  };
  return { handlers, timers, periods, reports, registry, context, emit, tick, stop };
}

describe("interactive lease lifecycle", () => {
  test("quiet sessions renew with no turn or tool events, including while a tool is unresolved", async () => {
    const calls: string[] = [];
    const tool = Promise.withResolvers<void>();
    const h = harness(async owner => {
      calls.push(owner.session);
      return 2;
    });
    h.emit("session_start");
    expect(h.periods).toEqual([60_000]);
    expect(calls).toEqual([]);
    for (let i = 0; i < 4; i++) await h.tick();
    expect(calls).toEqual(["first", "first", "first", "first"]);
    expect(h.reports).toEqual(Array.from({ length: 4 }, () => ({ kind: "renewed", count: 2 })));
    expect([...h.handlers.keys()]).toEqual(["session_start", "session_switch", "session_branch", "session_shutdown"]);
    tool.resolve();
    await tool.promise;
  });

  test("concurrent ticks are singleflight, then resume after the pending renewal", async () => {
    const pending = Promise.withResolvers<number>();
    let calls = 0;
    const h = harness(() => {
      calls++;
      return pending.promise;
    });
    h.emit("session_start");
    await h.tick();
    await h.tick();
    await h.tick();
    expect(calls).toBe(1);
    pending.resolve(1);
    await flush();
    await h.tick();
    expect(calls).toBe(2);
  });

  test("reconnect retains identity but switchback and branch issue fresh capabilities", () => {
    const h = harness();
    h.emit("session_start");
    const root = h.registry.root;
    const first = record(root, "first");
    h.emit("session_start");
    expect(record(root, "first")).toEqual(first);
    expect(h.periods).toHaveLength(1);
    h.emit("session_switch", h.context("second"));
    expect(existsSync(registrationPath(root, "first"))).toBe(false);
    expect(process.env.ATASK_RUNTIME_ROOT).toBe(root);
    h.emit("session_switch");
    expect(record(root, "first").capability).not.toBe(first.capability);
    const switched = record(root, "first");
    h.emit("session_branch");
    expect(record(root, "first").capability).not.toBe(switched.capability);
    expect(h.timers.size).toBe(1);
  });

  for (const outcome of ["success", "failure"] as const) {
    test(`stale ${outcome} after switch cannot affect a new activation`, async () => {
      const pending = Promise.withResolvers<number>();
      const h = harness(owner => owner.session === "first" ? pending.promise : Promise.resolve(1));
      h.emit("session_start");
      await h.tick();
      const staleTimer = [...h.timers.values()][0];
      h.emit("session_switch", h.context("second"));
      const current = record(h.registry.root, "second");
      if (outcome === "success") pending.resolve(4);
      else pending.reject(new Error("secret capability"));
      await flush();
      staleTimer();
      await flush();
      expect(h.reports).toEqual([]);
      expect(h.timers.size).toBe(1);
      expect(record(h.registry.root, "second")).toEqual(current);
      await h.tick();
      expect(h.reports).toEqual([{ kind: "renewed", count: 1 }]);
    });
  }

  test("failure stops and revokes without leaking error text or retrying on reconnect", async () => {
    const h = harness(async () => {
      throw new Error("stderr secret capability");
    });
    h.emit("session_start");
    await h.tick();
    expect(h.timers.size).toBe(0);
    expect(readdirSync(h.registry.root)).toEqual([]);
    expect(h.reports).toEqual([{ kind: "failed", reason: "renewal" }]);
    h.emit("session_start");
    await h.tick();
    expect(h.periods).toHaveLength(1);
    expect(h.reports).toHaveLength(1);
  });

  for (const count of [-1, NaN, Infinity, 0.5, Number.MAX_SAFE_INTEGER + 1]) {
    test(`invalid count ${count} fails closed`, async () => {
      const h = harness(async () => count);
      h.emit("session_start");
      await h.tick();
      expect(h.reports).toEqual([{ kind: "failed", reason: "renewal" }]);
      expect(h.timers.size).toBe(0);
      expect(readdirSync(h.registry.root)).toEqual([]);
    });
  }

  test("zero after release or complete is silent idle, not failure or a new claim", async () => {
    const h = harness(async () => 0);
    h.emit("session_start");
    const before = record(h.registry.root, "first");
    await h.tick();
    await h.tick();
    expect(h.reports).toEqual([]);
    expect(h.timers.size).toBe(1);
    expect(record(h.registry.root, "first")).toEqual(before);
  });

  test("shutdown fences pending results, clears timers and cannot reconnect", async () => {
    const pending = Promise.withResolvers<number>();
    const h = harness(() => pending.promise);
    h.emit("session_start");
    await h.tick();
    h.emit("session_shutdown");
    h.stop();
    pending.resolve(1);
    await flush();
    h.emit("session_start");
    expect(h.reports).toEqual([]);
    expect(h.timers.size).toBe(0);
    expect(readdirSync(h.registry.root)).toEqual([]);
    expect(existsSync(h.registry.root)).toBe(true);
  });

  for (const [hasUI, kind] of [[false, "main"], [true, "sub"], [false, "sub"]] as const) {
    test(`excludes UI=${hasUI} kind=${kind}`, async () => {
      let calls = 0;
      const h = harness(async () => {
        calls++;
        return 1;
      });
      h.emit("session_start", h.context("excluded", hasUI, kind));
      await h.tick();
      expect(h.timers.size).toBe(0);
      expect(calls).toBe(0);
      expect(h.reports).toEqual([]);
      expect(readdirSync(h.registry.root)).toEqual([]);
    });
  }

  test("same-cwd concurrent sessions retain independent registration and timer ownership", async () => {
    const registry = new Registry();
    const a = harness(async () => 1, registry), b = harness(async () => 1, registry);
    a.emit("session_start");
    b.emit("session_start", b.context("second"));
    const root = registry.root, first = record(root, "first"), second = record(root, "second");
    expect(first.incarnation).toBe(second.incarnation);
    expect(first.capability).not.toBe(second.capability);
    a.stop();
    expect(record(root, "second")).toEqual(second);
    await b.tick();
    expect(b.reports).toEqual([{ kind: "renewed", count: 1 }]);
    expect(existsSync(root)).toBe(true);
  });

  test("two extension registrations cannot own the same session", () => {
    const registry = new Registry();
    const a = harness(async () => 1, registry), b = harness(async () => 1, registry);
    a.emit("session_start");
    const before = record(registry.root, "first");
    b.emit("session_start");
    b.stop();
    expect(a.timers.size).toBe(1);
    expect(b.timers.size).toBe(0);
    expect(record(registry.root, "first")).toEqual(before);
  });
});

describe("private registry", () => {
  test("uses exact CLI record schema, hash path and private permissions", () => {
    const registry = new Registry();
    const activation = registry.activate("session/../unsafe")!;
    const entry = record(registry.root, activation.session);
    expect(Object.keys(entry).sort()).toEqual(["capability", "incarnation", "pid", "session"]);
    expect(entry.session).toBe(activation.session);
    expect(entry.pid).toBe(process.pid);
    expect(entry.incarnation).toMatch(/^[a-f0-9]{64}$/);
    expect(entry.capability).toMatch(/^[a-f0-9]{64}$/);
    expect(statSync(registry.root).mode & 0o777).toBe(0o700);
    expect(statSync(registrationPath(registry.root, activation.session)).mode & 0o777).toBe(0o600);
    registry.revoke(activation);
  });

  test("stale revocation cannot remove a newer capability", () => {
    const registry = new Registry(), old = registry.activate("first")!;
    registry.revoke(old);
    const current = registry.activate("first")!;
    const before = record(registry.root, "first");
    registry.revoke(old);
    expect(record(registry.root, "first")).toEqual(before);
    registry.revoke(current);
  });

  test("new process ignores inherited root and creates a different incarnation", async () => {
    const registry = new Registry(), activation = registry.activate("first")!;
    const first = record(registry.root, "first");
    const module = new URL("./registry.ts", import.meta.url).pathname;
    const child = Bun.spawn([
      process.execPath,
      "-e",
      `import { runtimeRegistry } from ${
        JSON.stringify(module)
      }; runtimeRegistry.activate('first'); console.log(JSON.stringify({root:runtimeRegistry.root}));`,
    ], {
      env: { ...process.env, ATASK_RUNTIME_ROOT: registry.root },
      stdout: "pipe",
      stderr: "pipe",
    });
    const output = JSON.parse(await new Response(child.stdout).text());
    expect(await child.exited).toBe(0);
    expect(output.root).not.toBe(registry.root);
    expect(record(registry.root, "first")).toEqual(first);
    expect(existsSync(output.root)).toBe(false);
    registry.revoke(activation);
  });
});

describe("bounded CLI adapter", () => {
  async function withCli(body: string, check: (cwd: string) => Promise<void>) {
    const cwd = mkdtempSync(join(tmpdir(), "atask-command-test-"));
    scratch.push(cwd);
    writeFileSync(join(cwd, "atask"), `#!${process.execPath}\n${body}\n`, { mode: 0o700 });
    const previous = process.env.PATH;
    process.env.PATH = `${cwd}:${previous ?? ""}`;
    try {
      await check(cwd);
    } finally {
      if (previous === undefined) delete process.env.PATH;
      else process.env.PATH = previous;
    }
  }
  test("passes exact invocation, isolated environment and cwd with no capability args", async () => {
    await withCli(
      `await Bun.write('invocation.json', JSON.stringify({args:process.argv.slice(2),root:process.env.ATASK_RUNTIME_ROOT,session:process.env.PI_SESSION_ID,legacy:process.env.ATASK_SESSION})); console.log(JSON.stringify({ok:true,result:{renewed:3}}));`,
      async cwd => {
        expect(await renewRuntime({ session: "owned-session", cwd }, "/private/root")).toBe(3);
        expect(JSON.parse(readFileSync(join(cwd, "invocation.json"), "utf8"))).toEqual({
          args: ["--json", "claim", "renew", "--runtime"],
          root: "/private/root",
          session: "owned-session",
          legacy: "",
        });
      },
    );
  });
  for (
    const output of [
      "not-json",
      "{\"ok\":false}",
      "{\"ok\":true}",
      "{\"ok\":true,\"result\":{\"renewed\":\"1\"}}",
      "{\"ok\":true,\"result\":{\"renewed\":-1}}",
    ]
  ) {
    test(`rejects malformed output ${output}`, async () => {
      await withCli(`console.log(${JSON.stringify(output)})`, async cwd => {
        await expect(renewRuntime({ session: "first", cwd }, "/private")).rejects.toThrow(
          "Invalid atask runtime renewal response",
        );
      });
    });
  }
  test("nonzero exit does not expose captured stderr", async () => {
    await withCli(`console.error('SECRET_CAPABILITY'); process.exit(7);`, async cwd => {
      await expect(renewRuntime({ session: "first", cwd }, "/private")).rejects.toThrow("atask runtime renewal failed");
    });
  });
});
