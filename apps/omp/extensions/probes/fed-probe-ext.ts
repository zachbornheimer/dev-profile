import { appendFileSync } from "node:fs";

// Throwaway probe: in `omp -p`, which events does the host await before it exits? Each event logs when its handler
// starts and again 3 s later. The 3 s wait runs detached: a handler that awaits it outlives omp's 2 s limit on
// `session_shutdown` and is killed ("handler timed out after 2000ms"). Whether the host waited for the work is
// read from the log: an `after-3s` line that never appears means the host exited first.
type Handler = (event: unknown, ctx: unknown) => unknown;
const EVENTS = ["turn_end", "agent_end", "session_stop", "session_shutdown"] as const;
const WAIT_MS = 3000;

export default function install(pi: { on: (event: string, handler: Handler) => void }): void {
  const logPath = process.env.FED_PROBE_LOG ?? "/tmp/fed-probe.log";
  const log = (line: object): void => appendFileSync(logPath, `${JSON.stringify({ t: Date.now(), ...line })}\n`);
  for (const event of EVENTS) {
    pi.on(event, (_event, ctx) => {
      const mode = typeof ctx === "object" && ctx !== null && "mode" in ctx ? ctx.mode : undefined;
      log({ at: `${event}:start`, mode });
      // Detached and unref'd: never holds the handler, and never keeps the process alive past the host's exit.
      setTimeout(() => log({ at: `${event}:after-3s` }), WAIT_MS).unref();
      return undefined;
    });
  }
}
