// When omp kills an extension handler for exceeding its time limit, warn in the TUI and start one detached
// `omp -p` repair session that finds the cause and fixes it. omp reports the kill through
// `extension_handler_settled` (outcome "timeout"); nothing else carries it to an extension.
//
// Guards against repair loops: the repair session itself runs with OMP_NESTED_RUN=1 and this extension does
// nothing under it; one repair per (extension, handled event) per cooldown, remembered on disk so a timeout
// that recurs in every session does not start a session each time.
import { type ChildProcess, spawn } from "node:child_process";
import { mkdirSync, openSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export const COOLDOWN_MS = 6 * 60 * 60 * 1000;

export type Settled = {
  extensionPath: string;
  handledEvent: string;
  durationMs: number;
  outcome: "ok" | "error" | "timeout";
  timeoutMs: number;
  error?: string;
};
type Context = { cwd?: string; ui?: { notify?(text: string, level: string): void } };
export type Spawner = (prompt: string, logPath: string, cwd: string) => ChildProcess;
export type Outcome =
  | { started: true; logPath: string }
  | { started: false; reason: "not-timeout" | "nested" | "cooldown" | "spawn-failed" };

export function repairPrompt(s: Settled, logPath: string): string {
  return [
    `An omp extension handler was killed for exceeding its time limit. Find the root cause and fix it.`,
    ``,
    `- extension: ${s.extensionPath}`,
    `- handled event: ${s.handledEvent}`,
    `- ran ${s.durationMs}ms against a ${s.timeoutMs}ms limit`,
    `- omp error text: ${s.error ?? "(none)"}`,
    ``,
    `Do this, in order:`,
    `1. Read the extension (resolve the symlink: the real file is the one to edit) and the code the handler calls.`,
    `2. Look for evidence of what was slow: ~/.local/state/omp-hooks/*.jsonl and the newest ~/.omp/logs/omp.*.log lines naming the extension.`,
    `3. Fix the cause so the handler finishes inside the limit (do the slow work detached or in the background and report it on a later turn). Do not raise the limit and do not swallow the timeout.`,
    `4. Add or update a test that fails on the old behavior, run it, and commit through a worktrunk worktree (wt switch -c, wt step commit, wt merge -y main).`,
    `5. Report what the cause was and what you changed. If you cannot fix it, say what blocked you.`,
    ``,
    `Run every command through the bash tool. Your own output is also written to ${logPath}.`,
  ].join("\n");
}

export const spawnRepair: Spawner = (prompt, logPath, cwd) => {
  const out = openSync(logPath, "a");
  // OMP_NESTED_RUN: this extension and the Stop reviewers stay quiet inside the repair session.
  const env = { ...process.env, OMP_NESTED_RUN: "1", OMP_SESSION_REVIEW: "0", OMP_TURN_WASTE: "0" };
  // A literal binary path: the spawn seam tests need is `Spawner`, so no env var selects what runs.
  return spawn("omp", ["-p", prompt], { cwd, stdio: ["ignore", out, out], env, detached: true });
};

export function handleSettled(
  s: Settled,
  ctx: Context,
  spawner: Spawner = spawnRepair,
  now: () => number = Date.now,
): Outcome {
  if (s.outcome !== "timeout") return { started: false, reason: "not-timeout" };
  if (process.env.OMP_NESTED_RUN === "1") return { started: false, reason: "nested" };
  const dir = process.env.OMP_EXTENSION_TIMEOUT_REPAIR_DIR
    ?? join(process.env.HOME ?? homedir(), ".local/state/omp-extension-timeout-repair");
  mkdirSync(dir, { recursive: true });
  const key = `${s.extensionPath}::${s.handledEvent}`.replace(/[^A-Za-z0-9_.-]/g, "_").slice(-160);
  const marker = join(dir, `${key}.marker`);
  let lastStart = Number.NEGATIVE_INFINITY;
  try {
    lastStart = Number(readFileSync(marker, "utf8"));
  } catch {
    // no marker: first timeout for this handler
  }
  if (now() - lastStart < COOLDOWN_MS) return { started: false, reason: "cooldown" };
  const logPath = join(dir, `${key}-${now()}.out`);
  writeFileSync(marker, String(now()));
  try {
    const child = spawner(repairPrompt(s, logPath), logPath, ctx.cwd ?? process.cwd());
    child.once("error", () => undefined);
    child.unref();
  } catch (e) {
    ctx.ui?.notify?.(
      `extension-timeout: ${s.extensionPath} ${s.handledEvent} exceeded ${s.timeoutMs}ms; repair session failed to start: ${
        e instanceof Error ? e.message : e
      }`,
      "warning",
    );
    return { started: false, reason: "spawn-failed" };
  }
  ctx.ui?.notify?.(
    `extension-timeout: ${s.extensionPath} ${s.handledEvent} exceeded ${s.timeoutMs}ms; starting an automatic repair session in the background (log: ${logPath})`,
    "warning",
  );
  return { started: true, logPath };
}

export default function install(pi: {
  on(name: "extension_handler_settled", handler: (event: Settled, ctx: Context) => void): void;
}) {
  pi.on("extension_handler_settled", (event, ctx) => {
    handleSettled(event, ctx);
  });
}
