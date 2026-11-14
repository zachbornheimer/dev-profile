import { afterEach, beforeEach, describe, expect, it } from "bun:test";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { watchFleet } from "./watch.js";

let dir: string;
beforeEach(async () => {
  dir = await mkdtemp(join(tmpdir(), "fleet-watch-"));
});
afterEach(async () => {
  await rm(dir, { recursive: true, force: true });
});

async function child(id: string, name: string, state: string, exit?: number) {
  const d = join(dir, id);
  await mkdir(d, { recursive: true });
  await writeFile(join(d, "meta.json"), JSON.stringify({ id, name, agent: "task", spawned_at: "2026-01-01T00:00:00Z" }));
  await writeFile(join(d, "state"), state);
  await writeFile(join(d, "inbox.md"), "");
  if (exit !== undefined) await writeFile(join(d, "exit_code"), String(exit));
}

describe("watchFleet", () => {
  it("wakes the parent once, only after every child settled", async () => {
    await child("a", "Alpha", "exited", 0);
    await child("b", "Beta", "running");
    const sent: { content: string; triggerTurn?: boolean }[] = [];
    let polls = 0;
    const woke = await watchFleet(dir, "s", ["a", "b"], {
      send: (m, o) => sent.push({ content: m.content, triggerTurn: o?.triggerTurn }),
      sleep: async () => {
        if (++polls === 2) await child("b", "Beta", "exited", 1);
      },
    });
    expect(woke).toBe(true);
    expect(polls).toBe(2);
    expect(sent).toHaveLength(1);
    expect(sent[0]?.triggerTurn).toBe(true);
    expect(sent[0]?.content).toContain("1 failed or killed");
    expect(sent[0]?.content).toContain("Beta exited exit 1");
  });

  it("gives up silently at the deadline without waking", async () => {
    await child("a", "Alpha", "running");
    let t = 0;
    const sent: unknown[] = [];
    const woke = await watchFleet(dir, "s", ["a"], {
      send: (m) => sent.push(m),
      maxMs: 10,
      now: () => t,
      sleep: async () => {
        t += 20;
      },
    });
    expect(woke).toBe(false);
    expect(sent).toHaveLength(0);
  });
});
