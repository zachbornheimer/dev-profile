import assert from "node:assert/strict";
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { type LeaseContext, registerLease } from "./index";

const binary = process.env.ATASK_LEASE_CLI;
assert.ok(binary, "run through the ai-task TestInteractiveLeaseHost helper");
let timerRenewals = 0;
const observations: string[] = [];

async function cli(args: string[], session: string, root: string, allowed = true) {
  const child = Bun.spawn([binary!, "-test.run=^TestLeaseCLIHelper$", "--", "--json", ...args], {
    cwd: process.cwd(),
    env: { ...process.env, ATASK_RUNTIME_ROOT: root, PI_SESSION_ID: session },
    stdin: "ignore",
    stdout: "pipe",
    stderr: "pipe",
  });
  const timeout = setTimeout(() => child.kill(), 8000);
  try {
    const [out, err, code] = await Promise.all([
      new Response(child.stdout).text(),
      new Response(child.stderr).text(),
      child.exited,
    ]);
    if (!allowed) {
      assert.notEqual(code, 0, "unrelated command authorized");
      return;
    }
    assert.equal(code, 0, `${args[0]} failed: ${out} ${err}`);
    return JSON.parse(out).result;
  } finally {
    clearTimeout(timeout);
  }
}

function start(session: string) {
  const handlers = new Map<string, (event: unknown, context: LeaseContext) => void>();
  const timers = new Set<Timer>();
  const stop = registerLease({
    on: (name, handler) => {
      handlers.set(name, handler);
    },
  }, {
    intervalMs: 100,
    report: event => {
      observations.push(event.kind);
      if (event.kind === "renewed") timerRenewals++;
    },
  });
  handlers.get("session_start")!({}, {
    cwd: process.cwd(),
    hasUI: true,
    agent: { kind: "main" },
    sessionManager: { getSessionId: () => session },
    setInterval: (fn: () => void, ms: number) => {
      const timer = setInterval(fn, ms);
      timers.add(timer);
      return timer;
    },
    clearTimer: (timer: Timer) => {
      clearInterval(timer);
      timers.delete(timer);
    },
  });
  const root = process.env.ATASK_RUNTIME_ROOT!;
  return {
    session,
    root,
    stop: () => {
      stop();
      for (const timer of timers) clearInterval(timer);
    },
  };
}

const first = start("interactive-first");
const second = start("interactive-second");
try {
  await cli(["project", "add", "Lease"], first.session, first.root);
  writeFileSync("proof-artifact", "interactive lease proof\n");
  const add = (title: string) =>
    cli(
      [
        "--project",
        "Lease",
        "add",
        title,
        "--proof",
        "run: test -f proof-artifact",
        "--regression",
        "run: test -s proof-artifact",
      ],
      first.session,
      first.root,
    );
  const a = await add("first owner"), b = await add("second owner");
  const claimA = await cli(["claim", a.task.id], first.session, first.root);
  const claimB = await cli(["claim", b.task.id], second.session, second.root);
  assert.equal(claimA.token, undefined);
  assert.equal(claimB.token, undefined);
  const before = timerRenewals;
  // No agent turn/tool-completion events and no model log/renew/reclaim. A real
  // long-running child overlaps more than three one-second engine leases.
  const tool = Bun.spawn([process.execPath, "-e", "setTimeout(() => process.exit(0), 3500)"], {
    stdout: "ignore",
    stderr: "pipe",
  });
  const toolDeadline = setTimeout(() => tool.kill(), 6000);
  try {
    assert.equal(await tool.exited, 0);
  } finally {
    clearTimeout(toolDeadline);
  }
  assert.ok(timerRenewals > before + 6, "lifecycle did not renew while the long tool ran");
  const currentA = await cli(["show", a.task.id, "--full"], first.session, first.root);
  const currentB = await cli(["show", b.task.id, "--full"], second.session, second.root);
  assert.equal(currentA.attempt.seq, claimA.attempt);
  assert.equal(currentB.attempt.seq, claimB.attempt);
  assert.ok(Date.parse(currentA.attempt.lease_expires_at) > Date.now(), "first lease expired");
  await cli(["log", "--done", "long tool survived"], first.session, first.root);
  await cli(["log", "--done", "concurrent owner survived"], second.session, second.root);
  await cli(["verify", "proof"], first.session, first.root);
  await cli(["verify", "proof"], second.session, second.root);
  await cli(["log", "--done", "unrelated"], "unrelated", first.root, false);
  await cli(["log", "--done", "session only"], first.session, "", false);
  await cli(["claim", "release"], first.session, first.root);
  assert.equal((await cli(["claim", "renew", "--runtime"], first.session, first.root)).renewed, 0);
  await cli(["verify", "complete"], second.session, second.root);
  assert.equal((await cli(["claim", "renew", "--runtime"], second.session, second.root)).renewed, 0);
  console.log(
    `PASS: same attempt across >3 leases during quiet/long tool; ${timerRenewals} lifecycle renewals; concurrent token-free log/verify; terminal and unrelated authority fenced`,
  );
} finally {
  first.stop();
  second.stop();
}
