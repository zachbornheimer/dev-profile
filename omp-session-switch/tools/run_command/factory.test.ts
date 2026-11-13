// The factory over omp's own zod: the advertised schema, the description, and the real host ports end to end
// (blocking exit 0 and 3, timeout, a background process job and its collect, a `when` refusal, a refusal
// before spawn, the sleep transform). State goes to a temp directory; no launchd job is emitted.
import { afterAll, beforeAll, describe, expect, it } from "bun:test";
import { existsSync } from "node:fs";
import { mkdtemp, rm } from "node:fs/promises";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";
import factory from "./index.ts";
import { listJobs } from "./jobs.ts";

/** omp's own `pi.zod` (omptype): chosen at run time, as the sibling tools' `zod_for_tests.ts` does. */
async function loadZod(): Promise<unknown> {
  const candidates = [
    join(homedir(), ".omp/packages/omptype/src/zod.ts"),
    join(homedir(), "Developer/Personal/.worktrees/oh-my-pi-assembled/packages/omptype/src/zod.ts"),
    join(homedir(), "Developer/Personal/oh-my-pi/packages/omptype/src/zod.ts"),
  ];
  const found = candidates.find((path) => existsSync(path));
  if (found === undefined) throw new Error(`omptype zod.ts not found in: ${candidates.join(", ")}`);
  return ((await import(found)) as { z: unknown }).z;
}
const z = await loadZod();

const home = await mkdtemp(join(tmpdir(), "run-command-factory-"));
const saved = {
  waits: process.env.CAPABILITY_WAITS_DIR,
  channels: process.env.CAPABILITY_CHANNELS_DIR,
  gateway: process.env.CAPABILITY_GATEWAY_HOME,
};

beforeAll(() => {
  process.env.CAPABILITY_WAITS_DIR = join(home, "waits");
  process.env.CAPABILITY_CHANNELS_DIR = join(home, "channels");
  process.env.CAPABILITY_GATEWAY_HOME = home;
});

afterAll(async () => {
  for (const [name, value] of [
    ["CAPABILITY_WAITS_DIR", saved.waits],
    ["CAPABILITY_CHANNELS_DIR", saved.channels],
    ["CAPABILITY_GATEWAY_HOME", saved.gateway],
  ] as const) {
    if (value === undefined) delete process.env[name];
    else process.env[name] = value;
  }
  await rm(home, { force: true, recursive: true });
});

const tool = (factory as (pi: unknown) => any)({ zod: z, cwd: process.cwd(), exec: async () => ({}) });
const ctx = { sessionManager: { getSessionId: () => "factory-test" } };

async function call(params: Record<string, unknown>): Promise<Record<string, any>> {
  const answer = await tool.execute("id", params, undefined, ctx, undefined);
  return answer.details;
}

describe("run_command factory", () => {
  it("is named run_command and advertises a compact schema", () => {
    expect(tool.name).toBe("run_command");
    const schema = JSON.stringify(tool.parameters.toJsonSchema());
    expect(schema.length).toBeLessThan(2500);
    for (const field of ["command", "cwd", "timeout_seconds", "purpose", "session", "background", "when", "notify", "block", "jobId", "onComplete", "log", "until"]) {
      expect(schema).toContain(`"${field}"`);
    }
    expect(schema).not.toContain("minLength");
  });

  it("runs a blocking command to exit 0 and exit 3", async () => {
    expect(await call({ command: "echo hi" })).toMatchObject({ status: "ok", exit_code: 0, body: "hi\n" });
    expect(await call({ command: "echo no; exit 3" })).toMatchObject({ status: "ok", exit_code: 3, body: "no\n" });
  });

  it("reports the deadline as status timeout, exit 124", async () => {
    expect(await call({ command: "while :; do :; done", timeout_seconds: 1 })).toMatchObject({
      status: "timeout",
      exit_code: 124,
    });
  });

  it("starts a background process job and collects it by handle", async () => {
    const started = await call({ command: "echo bg", background: { on_complete: "wait" } });
    expect(started).toMatchObject({ status: "ok", where: "process" });
    expect(started.job_id).toBeTypeOf("string");
    expect(started.log_path).toBeTypeOf("string");
    for (let attempt = 0; attempt < 100; attempt++) {
      const collected = await call({ jobId: started.job_id });
      if (collected.body === "bg\n") {
        expect(collected).toMatchObject({ status: "ok", exit_code: 0, jobId: started.job_id });
        return;
      }
      await Bun.sleep(50);
    }
    throw new Error("the background job never settled");
  });

  it("refuses an incomplete when event and a refused command before spawn", async () => {
    expect(await call({ command: "echo x", when: { type: "path_changed" } })).toMatchObject({
      status: "denied",
      reason: "when path_changed needs `path`.",
    });
    expect(await call({ command: "sed -i s/a/b/ f.txt" })).toMatchObject({ status: "denied", exit_code: 1 });
    expect(await call({ command: "" })).toMatchObject({ status: "denied", reason: "command must not be empty." });
  });

  it("turns a bare sleep into a wait, warning that it did", async () => {
    const output = await call({ command: "sleep 1" });
    expect(output.status).toBe("ok");
    expect(output.body).toContain("`sleep 1` was not executed; it became a `wait`");
  });
});
