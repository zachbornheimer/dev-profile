import { appendFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

// Throwaway probe: wall time of the real triage question on a state shaped like session B (one existing memory to supersede).
// Each question takes ~20 s, so three runs outlive omp's 30 s `session_stop` limit. The runs start detached and report
// into the log file on their own schedule; the handler returns at once.
type Handler = (event: unknown, ctx: unknown) => unknown;
type Inquiry = {
  inquiry: <T>(options: { input: unknown; questions: unknown; attempts: number; timeoutMs: number }) => Promise<T>;
};
export type Loaded = { questions: unknown; withInquiry: (ctx: never) => Inquiry };

const RUNS = 3;

const STATE = {
  repository: "dev-profile",
  user_requests:
    "Update for this repository (ref probe): gendoc-x was replaced by gendoc-y; regenerate docs/design with gendoc-y from now on, and gendoc-x is no longer used. Reply with exactly: noted probe",
  assistant_reply: "noted probe",
  existing_memories: [{
    id: "m-1",
    kind: "directive",
    text:
      "In the dev-profile repository, the generated files under docs/design are produced by gendoc-x; never edit docs/design by hand and always regenerate them with gendoc-x.",
  }],
};

// Dynamic on purpose: `@oh-my-pi/pi-ai` resolves only for modules loaded through omp's own runtime, so a static import fails outside it.
async function loadFromHost(): Promise<Loaded> {
  const { EXTRACT_QUESTIONS } = await import(join(homedir(), ".omp/agent/extensions/hooks/memory_extract.ts"));
  const { withInquiry } = await import(join(homedir(), ".omp/agent/extensions/prompts/inquiry.ts"));
  return { questions: EXTRACT_QUESTIONS, withInquiry };
}

export default function install(
  pi: { on: (event: string, handler: Handler) => void },
  load: () => Promise<Loaded> = loadFromHost,
): void {
  const logPath = process.env.FED_TRIAGE_LOG ?? "/tmp/fed-triage.log";
  const log = (line: object): void => appendFileSync(logPath, `${JSON.stringify(line)}\n`);

  async function runTriage(ctx: unknown): Promise<void> {
    const { questions, withInquiry } = await load();
    const inquiry = withInquiry(ctx as never);
    for (let run = 1; run <= RUNS; run++) {
      const started = Date.now();
      try {
        const answer = await inquiry.inquiry<unknown>({ input: STATE, questions, attempts: 1, timeoutMs: 90_000 });
        log({ run, ms: Date.now() - started, answer: JSON.stringify(answer).slice(0, 160) });
      } catch (error) {
        log({ run, ms: Date.now() - started, error: error instanceof Error ? error.message : String(error) });
      }
    }
  }

  pi.on("session_stop", (_event, ctx) => {
    // A failure to start the runs is logged so it cannot reach the host as an unhandled rejection.
    void runTriage(ctx).catch((error) => log({ error: error instanceof Error ? error.message : String(error) }));
    return undefined;
  });
}
