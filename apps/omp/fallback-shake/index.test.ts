import { describe, expect, mock, test } from "bun:test";

// Only selector parsing is a host import; the extension and decision rule run unchanged.
mock.module("@oh-my-pi/pi-tui/overlays/model-selector", () => ({
  MAX_THINKING_SUFFIX_OPTIONS: {},
  parseModelString: (selector: string) => {
    const slash = selector.indexOf("/");
    return { provider: selector.slice(0, slash), id: selector.slice(slash + 1) };
  },
  splitUpstreamRouting: () => undefined,
}));
// Test module-loading boundary: install the unavailable host-module mock before loading the extension.
const { default: fallbackShake } = await import("./index");

function fixture() {
  const handlers = new Map<string, Function>();
  const timers: Array<() => void> = [];
  const work = Promise.withResolvers<{ tokensFreed: number }>();
  const shake = mock(() => work.promise);
  const notify = mock(() => {});
  const ctx = {
    agent: { kind: "main" },
    model: { provider: "b", id: "model" },
    modelRegistry: { find: (provider: string, id: string) => ({ provider, id }) },
    models: { resolve: () => undefined },
    ui: { notify },
    shake,
    setTimeout: (callback: () => void) => {
      timers.push(callback);
      return 1;
    },
    clearTimer: () => {
      timers.length = 0;
    },
  };
  fallbackShake({ on: (event: string, handler: Function) => handlers.set(event, handler) } as never);
  const emit = (event: string, data = {}) => handlers.get(event)?.(data, ctx);
  const hop = () => emit("retry_fallback_applied", { from: "a/model", to: "b/model" });
  const tick = async () => {
    for (let i = 0; i < 8; i++) await Promise.resolve();
  };
  return { emit, hop, ctx, timers, work, shake, notify, tick };
}

describe("fallback shake event budget", () => {
  test("returns before an unresolved rewrite and coalesces duplicate fallbacks", async () => {
    const f = fixture();
    let returned = false;
    Promise.resolve(f.hop()).then(() => {
      returned = true;
    });
    await f.tick();
    expect(returned).toBe(true);
    expect(f.shake).not.toHaveBeenCalled();
    await f.hop();
    expect(f.timers).toHaveLength(1);
    f.timers.shift()!();
    await f.tick();
    expect(f.shake).toHaveBeenCalledTimes(1);
    await f.hop();
    expect(f.timers).toHaveLength(0);
    f.work.resolve({ tokensFreed: 42 });
    await f.tick();
    expect(f.notify.mock.calls.flat().join(" ")).not.toContain("42");
    await f.emit("agent_start");
    expect(f.notify.mock.calls.flat().join(" ")).toContain("42");
  });

  test("reports background failure on a later turn and allows another attempt", async () => {
    const f = fixture();
    await f.hop();
    f.timers.shift()!();
    f.work.reject(new Error("artifact disk full"));
    await f.tick();
    expect(f.notify.mock.calls.flat().join(" ")).not.toContain("artifact disk full");
    await f.emit("agent_start");
    expect(f.notify.mock.calls.flat().join(" ")).toContain("artifact disk full");
    await f.hop();
    expect(f.timers).toHaveLength(1);
  });

  test("does not shake a session whose model changed before detached work starts", async () => {
    const f = fixture();
    await f.hop();
    f.ctx.model = { provider: "c", id: "other" };
    f.timers.shift()!();
    await f.tick();
    expect(f.shake).not.toHaveBeenCalled();
  });

  test("keeps subagent and advisor fallbacks notification-only", async () => {
    const f = fixture();
    f.ctx.agent.kind = "sub";
    await f.hop();
    f.ctx.agent.kind = "main";
    await f.emit("retry_fallback_applied", { from: "a/model", to: "b/model", target: "advisor" });
    expect(f.timers).toHaveLength(0);
    expect(f.shake).not.toHaveBeenCalled();
  });

  test("cancels detached work on session shutdown", async () => {
    const f = fixture();
    await f.hop();
    await f.emit("session_shutdown");
    expect(f.timers).toHaveLength(0);
    expect(f.shake).not.toHaveBeenCalled();
  });
});
