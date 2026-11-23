import { type FleetChild, listChildren } from "./fleet.js";

/** omp's `sendMessage` as a custom tool reaches it. */
export type SendMessage = (
  message: { customType: string; content: string; display: boolean; details?: unknown },
  options?: { triggerTurn?: boolean },
) => void;

export interface WatchDeps {
  readonly send: SendMessage;
  readonly pollMs?: number;
  /** Give up after this long; the parent can still `list`. Default 6 hours. */
  readonly maxMs?: number;
  readonly sleep?: (ms: number) => Promise<void>;
  readonly now?: () => number;
}

const settled = (child: FleetChild): boolean => child.state === "exited" || child.state === "killed";

/** The one message that wakes the parent: which children ended, how, and where their output is. */
export function settledMessage(session: string, children: readonly FleetChild[]): string {
  const failed = children.filter((c) => c.state === "killed" || (c.exit_code ?? 0) !== 0);
  const lines = children.map((c) =>
    `${c.name} ${c.state}${c.exit_code === undefined ? "" : ` exit ${c.exit_code}`} output ${c.output_path}`
  );
  const head = `task_fleet ${session}: all ${children.length} child(ren) finished`
    + (failed.length ? `, ${failed.length} failed or killed` : "");
  return [head, ...lines].join("\n");
}

/**
 * Polls the spawned children's state files and, once every one is exited or killed, injects one
 * "Task Fleet Finished" message that starts a turn. This is what lets the parent stop and wait instead
 * of polling `list`. Resolves true when it woke the parent, false when it gave up. Never throws.
 */
export async function watchFleet(
  stateDir: string,
  session: string,
  ids: readonly string[],
  deps: WatchDeps,
): Promise<boolean> {
  const pollMs = deps.pollMs ?? 3000;
  const maxMs = deps.maxMs ?? 6 * 60 * 60 * 1000;
  const sleep = deps.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  const now = deps.now ?? Date.now;
  const deadline = now() + maxMs;
  try {
    while (now() < deadline) {
      const mine = (await listChildren(stateDir)).filter((c) => ids.includes(c.id));
      if (mine.length === ids.length && mine.every(settled)) {
        deps.send(
          {
            customType: "Task Fleet Finished",
            content: settledMessage(session, mine),
            display: true,
            details: { session, ids },
          },
          { triggerTurn: true },
        );
        return true;
      }
      await sleep(pollMs);
    }
  } catch {
    // The fleet stays readable through `list`.
  }
  return false;
}
