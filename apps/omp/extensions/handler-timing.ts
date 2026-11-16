// Logs how long every extension handler takes and, when one hits omp's handler time limit, spawns
// `/learn <error message>` at once.
//
// Needs the omp fork's `extension_handler_settled` event (branch feat/extension-handler-settled). On a build
// without it the handler below never fires and this extension does nothing.
//
// - Timing log: one JSON line per settled handler in `~/.local/state/omp-hooks/handler-timings.jsonl`
//   (`OMP_HOOKS_LOG_DIR` redirects it). `slow` marks handlers past SLOW_MS or that did not end `ok`.
// - Timeout: the learner is the same detached `omp -p` run `/learn` starts (see `learn-command.ts`; the launch is
//   repeated here because a symlinked extension cannot import its sibling from the live directory), given the
//   text omp shows for the failure, e.g. `Extension "<path>" error: handler timed out after 30000ms`.
//   One learner per extension+event per LEARN_COOLDOWN_MS, and never from inside a learner run, so a
//   handler that always times out cannot start a chain of learners.
import { spawn } from "node:child_process";
import { appendFileSync, mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export interface HandlerSettled {
  extensionPath: string;
  handledEvent: string;
  durationMs: number;
  outcome: "ok" | "error" | "timeout";
  timeoutMs: number;
  error?: string;
}

interface Ctx {
  cwd?: string;
  ui?: { notify(message: string, type?: "info" | "warning" | "error"): void };
  sessionManager?: { getSessionFile?(): string | undefined; getSessionId?(): string | undefined };
}

interface Pi {
  on(event: "extension_handler_settled", handler: (event: HandlerSettled, ctx: Ctx) => unknown): void;
}

export const SLOW_MS = 1_000;
export const LEARN_COOLDOWN_MS = 10 * 60_000;

/** `omp -p` bare completion flags (auto-goal/assess/omp_model.ts) plus the one tool the learner may call. */
const LEARN_FLAGS = [
  "--no-session",
  "--no-extensions",
  "--no-skills",
  "--no-rules",
  "--no-context-files",
  "--no-title",
  "--no-lsp",
  "--no-pty",
  "--tools",
  "learn_from_transcript",
  "--auto-approve",
];

const OMP_SESSION_NAME = /_([0-9a-f]{8}-[0-9a-f-]{27})\.jsonl$/;

export const logDir = () =>
  process.env.OMP_HOOKS_LOG_DIR ?? join(process.env.HOME ?? homedir(), ".local/state/omp-hooks");
export const timingLogPath = () => join(logDir(), "handler-timings.jsonl");

/** The text omp's UI shows for a failed handler, which is what `/learn` is given. */
export function failureMessage(event: HandlerSettled): string {
  return `Extension "${event.extensionPath}" error: ${
    event.error ?? `handler ${event.outcome}`
  } (event ${event.handledEvent})`;
}

/** Inside a learner (or any nested omp run) a timeout is logged but never starts another learner. */
export function mayLearn(env: Record<string, string | undefined>): boolean {
  return env.LEARNER !== "1" && env.OMP_NESTED_RUN !== "1" && env.OMP_HANDLER_TIMEOUT_LEARN !== "0";
}

/** Cooldown keyed by extension+event; returns true (and records `now`) when a learner may start. */
export function admit(last: Map<string, number>, event: HandlerSettled, now: number): boolean {
  const key = `${event.extensionPath}\0${event.handledEvent}`;
  const previous = last.get(key);
  if (previous !== undefined && now - previous < LEARN_COOLDOWN_MS) return false;
  last.set(key, now);
  return true;
}

export function timingRecord(
  event: HandlerSettled,
  sessionId: string | undefined,
  at = new Date(),
): Record<string, unknown> {
  return {
    at: at.toISOString(),
    ...(sessionId ? { session_id: sessionId } : {}),
    extension: event.extensionPath,
    event: event.handledEvent,
    duration_ms: event.durationMs,
    outcome: event.outcome,
    timeout_ms: event.timeoutMs,
    ...(event.outcome !== "ok" || event.durationMs >= SLOW_MS ? { slow: true } : {}),
    ...(event.error ? { error: event.error.slice(0, 500) } : {}),
  };
}

/** Appends one line; a log that cannot be written never breaks the turn. */
export function logTiming(record: Record<string, unknown>, path = timingLogPath()): void {
  try {
    mkdirSync(logDir(), { recursive: true });
    appendFileSync(path, `${JSON.stringify(record)}\n`);
  } catch {
    /* observability only */
  }
}

function sessionFileOf(ctx: Ctx): string | undefined {
  try {
    return ctx.sessionManager?.getSessionFile?.();
  } catch {
    return undefined;
  }
}

function sessionIdOf(ctx: Ctx): string | undefined {
  try {
    return ctx.sessionManager?.getSessionId?.() ?? OMP_SESSION_NAME.exec(sessionFileOf(ctx) ?? "")?.[1];
  } catch {
    return undefined;
  }
}

type Launch = (
  command: string,
  args: string[],
  options: Record<string, unknown>,
) => { on(event: "error", listener: () => void): unknown; unref(): void };

/** Starts the detached learner for this session; returns what it launched, or why it did not. */
export function spawnLearner(
  event: HandlerSettled,
  ctx: Ctx,
  env: Record<string, string | undefined> = process.env,
  launch: Launch = spawn as unknown as Launch,
): { started: true; source: string } | { started: false; reason: string } {
  const file = sessionFileOf(ctx) ?? env.PI_SESSION_FILE;
  const id = file ? OMP_SESSION_NAME.exec(file)?.[1] : undefined;
  if (!id) return { started: false, reason: "no saved session to learn from" };
  const source = `omp:${id}`;
  const payload = { source, focus: failureMessage(event).slice(0, 2000), implement: false };
  const prompt = `Call the learn_from_transcript tool exactly once with ${
    JSON.stringify(payload)
  }. Do not call any other tool. Then reply with one line: the first line of what the tool returned, or the error it raised.`;
  try {
    const child = launch("omp", ["-p", prompt, ...LEARN_FLAGS], {
      detached: true,
      shell: false,
      stdio: "ignore",
      env: {
        ...env,
        OMP_NESTED_RUN: "1",
        LEARNER: "1",
        OMP_TURN_WASTE: "0",
        OMP_AUTO_LEARN: "0",
        OMP_SESSION_REVIEW: "0",
      },
    });
    child.on("error", () => {});
    child.unref();
    return { started: true, source };
  } catch (error) {
    return { started: false, reason: error instanceof Error ? error.message : String(error) };
  }
}

export default function(pi: Pi) {
  const lastLearn = new Map<string, number>();
  pi.on("extension_handler_settled", (event, ctx) => {
    logTiming(timingRecord(event, sessionIdOf(ctx)));
    if (event.outcome !== "timeout" || !mayLearn(process.env)) return;
    if (!admit(lastLearn, event, Date.now())) return;
    const result = spawnLearner(event, ctx);
    logTiming({
      at: new Date().toISOString(),
      kind: "timeout-learn",
      extension: event.extensionPath,
      event: event.handledEvent,
      ...result,
    });
    ctx.ui?.notify?.(
      result.started
        ? `Handler timeout: /learn started on ${result.source} for ${event.extensionPath}`
        : `Handler timeout: /learn not started (${result.reason})`,
      result.started ? "info" : "warning",
    );
  });
}
