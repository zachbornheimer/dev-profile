import { appendFileSync } from "node:fs";

// Throwaway probe: wall time of the real triage prompt on the @smol model at different reasoning efforts.
// The sweep is four sequential model calls (up to 80 s each), far past omp's 30 s `session_stop` limit, so the
// handler starts it detached and returns at once; results land in the log file.
type Handler = (event: unknown, ctx: ProbeContext) => unknown;
type Log = (line: object) => void;

interface ProbeModel {
  id: string;
  provider: string;
  thinking?: { efforts?: unknown };
}

interface ProbeContext {
  models: { resolve(alias: string): ProbeModel };
  modelRegistry: { getApiKeyForProvider(provider: string): Promise<string | undefined> };
}

interface ProbeResponse {
  content?: { type?: string; text?: string }[];
  usage?: { output?: number; outputTokens?: number };
  stopReason?: string;
}

export interface ProbeModules {
  languagePrompt(question: unknown, state: string): string;
  loadNamedQuestionFile(name: string): { language: Record<string, unknown> };
  completeSimple(model: ProbeModel, context: unknown, options: object): Promise<ProbeResponse | undefined>;
}

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

// Runtime-selected on purpose: `@oh-my-pi/pi-ai` resolves only for modules loaded through omp's own runtime, and the
// two prompt modules live in the user's omp config, outside this repository.
export async function loadProbeModules(): Promise<ProbeModules> {
  const models = await import("/home/zbornheimer/.omp/agent/extensions/prompts/models.ts");
  const questions = await import("/home/zbornheimer/.omp/agent/extensions/prompts/questions.ts");
  const ai = await import("@oh-my-pi/pi-ai");
  return {
    languagePrompt: models.languagePrompt,
    loadNamedQuestionFile: questions.loadNamedQuestionFile,
    completeSimple: ai.completeSimple,
  } as unknown as ProbeModules; // the three modules are untyped from this repository
}

async function sweep(ctx: ProbeContext, log: Log, load: () => Promise<ProbeModules>): Promise<void> {
  const mods = await load();
  const model = ctx.models.resolve("@smol");
  const apiKey = await ctx.modelRegistry.getApiKeyForProvider(model.provider);
  const question = Object.values(mods.loadNamedQuestionFile("prompts/memory_extract.yaml").language)[0];
  const prompt = mods.languagePrompt(question, JSON.stringify(STATE));
  log({
    model: model.id,
    supportsThinking: Boolean(model.thinking),
    efforts: model.thinking?.efforts,
    promptChars: prompt.length,
  });
  for (const reasoning of [undefined, "minimal", "low", "none"]) {
    const started = Date.now();
    try {
      const response = await mods.completeSimple(
        model,
        { messages: [{ role: "user", content: [{ type: "text", text: prompt }], timestamp: Date.now() }] },
        { apiKey, maxTokens: 2048, ...(reasoning ? { reasoning } : {}), signal: AbortSignal.timeout(80_000) },
      );
      const blocks = response?.content ?? [];
      const text = blocks.filter((c) => c.type === "text").map((c) => c.text).join("");
      log({
        reasoning: reasoning ?? "default",
        ms: Date.now() - started,
        chars: text.length,
        blocks: blocks.map((c) => c.type).join(","),
        usage: response?.usage?.output ?? response?.usage?.outputTokens,
        stop: response?.stopReason,
        head: text.slice(0, 90),
      });
    } catch (error) {
      log({
        reasoning: reasoning ?? "default",
        ms: Date.now() - started,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }
}

export default function install(
  pi: { on: (event: string, handler: Handler) => void },
  load: () => Promise<ProbeModules> = loadProbeModules,
): void {
  const logPath = process.env.FED_EFFORT_LOG ?? "/tmp/fed-effort.log";
  const log: Log = (line) => appendFileSync(logPath, `${JSON.stringify(line)}\n`);
  pi.on("session_stop", (_event, ctx) => {
    // Detached: a setup failure is logged because nothing awaits the promise.
    void sweep(ctx, log, load).catch((error: unknown) =>
      log({ setup_error: error instanceof Error ? error.message : String(error) })
    );
    return undefined;
  });
}
