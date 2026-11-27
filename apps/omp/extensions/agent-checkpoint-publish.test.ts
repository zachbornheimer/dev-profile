import { afterEach, expect, test } from "bun:test";
import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import install, { type Job, jobPath, readJob, writeJob } from "./agent-checkpoint-publish.ts";

const source = path.resolve(import.meta.dir, "agent-checkpoint-publish.ts");
const dirs: string[] = [];
// Real detached subprocesses cannot share fake timers; await their durable state.
const saved = { ...process.env };
afterEach(() => {
  process.env = { ...saved };
  for (const dir of dirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});
function git(repo: string, ...args: string[]) {
  const r = spawnSync("git", args, { cwd: repo, encoding: "utf8", env: process.env });
  if (r.error) throw r.error;
  if (r.status !== 0) throw new Error(`${args.join(" ")}: ${r.stderr}`);
  return r.stdout.toString().trim();
}
function fixture() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "checkpoint-"));
  dirs.push(root);
  const repo = path.join(root, "work"), remote = path.join(root, "remote.git");
  process.env.HOME = path.join(root, "home");
  fs.mkdirSync(process.env.HOME);
  delete process.env.GIT_CONFIG_COUNT;
  delete process.env.GIT_CONFIG_PARAMETERS;
  delete process.env.AGENT_CHECKPOINT_PUBLISH;
  process.env.AGENT_CHECKPOINT_STATE_DIR = path.join(root, "state");
  process.env.AGENT_CHECKPOINT_ENROLLMENT_FILE = path.join(root, "enrollment.toml");
  git(root, "init", "--bare", remote);
  git(root, "init", "-b", "main", repo);
  git(repo, "config", "user.name", "Checkpoint Test");
  git(repo, "config", "user.email", "checkpoint@example.test");
  const key = path.join(root, "signing");
  const gen = spawnSync("ssh-keygen", ["-q", "-t", "ed25519", "-N", "", "-f", key]);
  expect(gen.status).toBe(0);
  fs.writeFileSync(path.join(root, "allowed"), `checkpoint@example.test ${fs.readFileSync(`${key}.pub`, "utf8")}`);
  git(repo, "config", "gpg.format", "ssh");
  git(repo, "config", "user.signingkey", key);
  git(repo, "config", "gpg.ssh.allowedSignersFile", path.join(root, "allowed"));
  git(repo, "config", "commit.gpgsign", "true");
  git(repo, "commit", "--allow-empty", "-m", "baseline");
  git(repo, "remote", "add", "origin", remote);
  git(repo, "push", "origin", "HEAD:refs/heads/main");
  const base = git(repo, "rev-parse", "HEAD");
  const entry = {
    slug: "scratch",
    path: repo,
    canonical: remote,
    remote: "origin",
    visibility: "private",
    namespace: "refs/heads/agent-checkpoints/",
  };
  const enroll = () =>
    fs.writeFileSync(
      process.env.AGENT_CHECKPOINT_ENROLLMENT_FILE!,
      `schema_version = 1\n[repos.scratch]\nenabled = true\n${
        Object.entries(entry).filter(([k]) => k !== "slug").map(([k, v]) => `${k} = ${JSON.stringify(v)}`).join("\n")
      }\n`,
    );
  enroll();
  const handlers = new Map<string, Function>(), notices: string[] = [];
  install({
    on(n, fn) {
      handlers.set(n, fn);
    },
  });
  const ctx = {
    cwd: repo,
    ui: {
      notify(text: string) {
        notices.push(text);
      },
    },
  };
  const event = async (name: string, data = {}) => {
    const handler = handlers.get(name);
    if (!handler) throw new Error(`Missing lifecycle subscription: ${name}`);
    await handler(data, ctx);
  };
  const commit = (message = "checkpoint", signed = true) => {
    git(repo, "-c", `commit.gpgsign=${signed}`, "commit", "--allow-empty", "-m", message);
    return git(repo, "rev-parse", "HEAD");
  };
  const makeJob = (sha: string, provenance = [sha]): Job => ({
    key: "a".repeat(64),
    repo,
    identity: git(repo, "rev-parse", "--absolute-git-dir"),
    ref: `refs/heads/agent-checkpoints/scratch/main/t0001-${sha}`,
    sha,
    turn: "t0001",
    entry,
    provenance,
    dirty: false,
    attempts: 0,
    createdAt: Date.now(),
    heartbeatAt: Date.now(),
    state: "queued",
    outcome: "pending",
    detail: "",
  });
  const refs = () => git(root, "--git-dir", remote, "for-each-ref", "--format=%(refname) %(objectname)");
  return { root, repo, remote, base, entry, enroll, notices, event, commit, makeJob, refs };
}
async function worker(job: Job) {
  writeJob(job);
  const proc = spawn("bun", [source, "--worker", jobPath(job.key)], {
    env: process.env,
    stdio: "ignore",
    timeout: 30_000,
    killSignal: "SIGKILL",
  });
  const { promise, resolve, reject } = Promise.withResolvers<void>();
  proc.once("error", reject);
  proc.once(
    "close",
    (code, signal) => code === 0 ? resolve() : reject(new Error(`worker exit ${code}, signal ${signal}`)),
  );
  await promise;
  return readJob(jobPath(job.key));
}
async function settled(timeoutMs = 15_000) {
  const dir = path.join(process.env.AGENT_CHECKPOINT_STATE_DIR!, "jobs");
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    const files = fs.existsSync(dir) ? fs.readdirSync(dir).filter(f => f.endsWith(".json")) : [];
    if (files.length > 1) throw new Error(`Expected one checkpoint job, found ${files.length}`);
    if (files.length) {
      const job = readJob(path.join(dir, files[0]));
      if (["verified", "failed", "expired"].includes(job.state)) return job;
    }
    await Bun.sleep(20);
  }
  throw new Error("worker did not settle");
}

test("signed checkpoint publishes exactly one ref with remote read-back", async () => {
  const f = fixture(), before = f.refs();
  await f.event("agent_start");
  const sha = f.commit();
  await f.event("agent_end");
  expect(f.notices.join("\n")).toContain("pending");
  const job = await settled();
  expect(job.outcome).toBe("verified");
  expect(job.attempts).toBe(1);
  expect(f.refs().split("\n").filter(line => !before.split("\n").includes(line))).toEqual([`${job.ref} ${sha}`]);
  expect(git(f.repo, "ls-remote", f.remote, job.ref)).toBe(`${sha}\t${job.ref}`);
  await f.event("agent_start");
  expect(f.notices.join("\n")).toContain(`sha=${sha} attempts=1`);
  expect((await worker(job)).state).toBe("verified");
  expect(f.refs().split("\n").filter(line => !before.split("\n").includes(line))).toHaveLength(1);
}, 20000);

test("default enrollment and continuation/worker guards never publish", async () => {
  const f = fixture(), before = f.refs();
  fs.writeFileSync(process.env.AGENT_CHECKPOINT_ENROLLMENT_FILE!, "schema_version = 1\n");
  await f.event("agent_end");
  expect(f.notices.join("\n")).not.toContain("agent-checkpoint");
  f.enroll();
  await f.event("agent_end", { willContinue: true });
  process.env.AGENT_CHECKPOINT_PUBLISH = "1";
  await f.event("agent_start");
  await f.event("agent_end");
  expect(f.refs()).toBe(before);
  expect(fs.existsSync(path.join(process.env.AGENT_CHECKPOINT_STATE_DIR!, "jobs"))).toBe(false);
});

test("a turn ending outside any git repository is skipped quietly", async () => {
  const f = fixture(), plain = path.join(f.root, "plain");
  fs.mkdirSync(plain);
  // Isolate the checkpoint outcome from machine-global mise reconciliation.
  const gitOnly = path.join(f.root, "git-only");
  fs.mkdirSync(gitOnly);
  fs.symlinkSync(Bun.which("git")!, path.join(gitOnly, "git"));
  process.env.PATH = gitOnly;
  const handlers = new Map<string, Function>(), notices: string[] = [];
  install({
    on(n, fn) {
      handlers.set(n, fn);
    },
  });
  const ctx = { cwd: plain, ui: { notify: (text: string) => notices.push(text) } };
  await handlers.get("agent_start")?.({}, ctx);
  await handlers.get("agent_end")?.({}, ctx);
  expect(notices).toEqual([]);
  expect(fs.existsSync(path.join(process.env.AGENT_CHECKPOINT_STATE_DIR!, "jobs"))).toBe(false);
});

test("an enrollment entry with an invalid policy still warns and never publishes", async () => {
  const f = fixture(), before = f.refs();
  const text = fs.readFileSync(process.env.AGENT_CHECKPOINT_ENROLLMENT_FILE!, "utf8");
  fs.writeFileSync(
    process.env.AGENT_CHECKPOINT_ENROLLMENT_FILE!,
    text.replace(/visibility = "[a-z]+"/, "visibility = \"secret\""),
  );
  await f.event("agent_end");
  expect(f.notices.join("\n")).toContain("blocked-not-enrolled invalid enrollment policy");
  expect(f.refs()).toBe(before);
});

test("a warning notice is also emitted as a harness event of the session that saw it", async () => {
  const f = fixture();
  const text = fs.readFileSync(process.env.AGENT_CHECKPOINT_ENROLLMENT_FILE!, "utf8");
  fs.writeFileSync(
    process.env.AGENT_CHECKPOINT_ENROLLMENT_FILE!,
    text.replace(/visibility = "[a-z]+"/, "visibility = \"secret\""),
  );
  const handlers = new Map<string, Function>(), notices: string[] = [], emitted: { channel: string; data: any }[] = [];
  install({
    on: (n, fn) => void handlers.set(n, fn),
    events: { emit: (channel, data) => void emitted.push({ channel, data }) },
  });
  const ctx = {
    cwd: path.join(f.root, "work"),
    sessionManager: { getSessionId: () => "01a1-session" },
    ui: { notify: (t: string) => void notices.push(t) },
  };
  await handlers.get("agent_end")!({}, ctx);
  expect(notices).toHaveLength(1);
  expect(emitted).toEqual([
    {
      channel: "harness-event",
      data: {
        session_id: "01a1-session",
        layer: "checkpoint-publish",
        event: "checkpoint_blocked",
        text: notices[0],
        fields: { level: "warning" },
      },
    },
  ]);
});

test("ambiguous ownership never queues work", async () => {
  const f = fixture(), before = f.refs();
  const text = fs.readFileSync(process.env.AGENT_CHECKPOINT_ENROLLMENT_FILE!, "utf8");
  fs.writeFileSync(
    process.env.AGENT_CHECKPOINT_ENROLLMENT_FILE!,
    text + text.slice(text.indexOf("[repos.")).replace("repos.scratch", "repos.other"),
  );
  await f.event("agent_end");
  expect(f.notices.join("\n")).toContain("blocked-ambiguous-ownership");
  expect(f.refs()).toBe(before);
});

for (const kind of ["different-sha", "df-conflict", "verified-present"] as const) {
  test(`remote collision ${kind} is read back without mutation`, async () => {
    const f = fixture(), sha = f.commit(), job = f.makeJob(sha);
    const ref = kind === "df-conflict" ? job.ref.slice(0, job.ref.lastIndexOf("/")) : job.ref;
    git(f.repo, "push", f.remote, `${kind === "verified-present" ? sha : f.base}:${ref}`);
    const before = f.refs(), result = await worker(job);
    expect(result.outcome).toBe(kind === "verified-present" ? kind : "blocked-collision");
    if (kind !== "verified-present") expect(result.detail).toBe(kind);
    expect(f.refs()).toBe(before);
  });
}

for (const kind of ["blocked-unsigned", "blocked-provenance", "blocked-secrets", "blocked-hook-rejected"] as const) {
  test(`${kind} stops on attempt one and leaves local and remote state intact`, async () => {
    const f = fixture();
    if (kind === "blocked-secrets") {
      fs.writeFileSync(
        path.join(f.repo, "secret"),
        "github_token = ghp_" + "0123456789abcdefABCDEF9876543210abcdef" + "\n",
      );
      git(f.repo, "add", "secret");
    }
    const sha = f.commit("checkpoint", kind !== "blocked-unsigned"), job = f.makeJob(sha);
    if (kind === "blocked-provenance") job.provenance = [];
    if (kind === "blocked-hook-rejected") {
      const hook = path.join(f.repo, ".git/hooks/pre-push");
      fs.writeFileSync(hook, "#!/bin/sh\necho policy-rejected >&2\nexit 1\n", { mode: 0o755 });
    }
    const before = f.refs(), status = git(f.repo, "status", "--porcelain"), result = await worker(job);
    expect(result.outcome).toBe(kind);
    expect(result.attempts).toBe(1);
    expect(f.refs()).toBe(before);
    expect(git(f.repo, "rev-parse", "HEAD")).toBe(sha);
    expect(git(f.repo, "status", "--porcelain")).toBe(status);
    if (kind === "blocked-hook-rejected") expect(result.detail).toContain("local work intact");
  });
}

for (const rewrite of ["pushurl", "pushInsteadOf"] as const) {
  test(`${rewrite} destination drift is blocked before push`, async () => {
    const f = fixture(), sha = f.commit(), before = f.refs(), other = path.join(f.root, "other.git");
    git(f.root, "init", "--bare", other);
    if (rewrite === "pushurl") git(f.repo, "remote", "set-url", "--push", "origin", other);
    else git(f.repo, "config", `url.${other}.pushInsteadOf`, f.remote);
    expect((await worker(f.makeJob(sha))).outcome).toBe("blocked-destination-changed");
    expect(f.refs()).toBe(before);
    expect(git(f.root, "--git-dir", other, "for-each-ref")).toBe("");
  });
}

for (const present of [false, true]) {
  test(`disconnected advertised ancestry with local object=${present} is blocked`, async () => {
    const f = fixture(), sha = f.commit(), job = f.makeJob(sha);
    git(f.repo, "checkout", "--orphan", "other");
    git(f.repo, "commit", "--allow-empty", "-m", "unrelated");
    const orphan = git(f.repo, "rev-parse", "HEAD");
    git(f.root, "--git-dir", f.remote, "fetch", f.repo, `${orphan}:refs/heads/unrelated`);
    git(f.root, "--git-dir", f.remote, "update-ref", "-d", "refs/heads/main");
    git(f.repo, "checkout", "main");
    if (!present) {
      git(f.repo, "branch", "-D", "other");
      git(f.repo, "reflog", "expire", "--expire=now", "--all");
      git(f.repo, "gc", "--prune=now");
    }
    const before = f.refs(), result = await worker(job);
    expect(result.outcome).toBe(present ? "blocked-unrelated-ancestry" : "blocked-missing-baseline");
    expect(f.refs()).toBe(before);
  });
}

test("transient transport failure gets exactly three attempts", async () => {
  const f = fixture(), job = f.makeJob(f.commit()), before = f.refs();
  f.entry.canonical = path.join(f.root, "missing.git");
  f.enroll();
  git(f.repo, "remote", "set-url", "origin", f.entry.canonical);
  const result = await worker(job);
  expect(result.outcome).toBe("blocked-remote-unreachable");
  expect(result.attempts).toBe(3);
  expect(f.refs()).toBe(before);
});

test("expired queued jobs cannot publish", async () => {
  const f = fixture(), job = f.makeJob(f.commit()), before = f.refs();
  job.createdAt -= 86_400_001;
  expect((await worker(job)).state).toBe("expired");
  expect(f.refs()).toBe(before);
});

test("duplicate agent_end creates one job and preserves dirty files and stash", async () => {
  const f = fixture();
  await f.event("agent_start");
  f.commit();
  fs.writeFileSync(path.join(f.repo, "dirty"), "untouched\n");
  const status = git(f.repo, "status", "--porcelain"), stash = git(f.repo, "stash", "list");
  await f.event("agent_end");
  await f.event("agent_end");
  const job = await settled();
  expect(job.outcome).toBe("verified");
  expect(job.dirty).toBe(true);
  expect(fs.readdirSync(path.dirname(jobPath(job.key))).filter(n => n.endsWith(".json"))).toHaveLength(1);
  expect(git(f.repo, "status", "--porcelain")).toBe(status);
  expect(git(f.repo, "stash", "list")).toBe(stash);
}, 20000);

test("lost response is read back without another push", async () => {
  const f = fixture(), sha = f.commit(), job = f.makeJob(sha);
  git(f.repo, "push", f.remote, `${sha}:${job.ref}`);
  job.state = "pushed";
  job.attempts = 1;
  job.heartbeatAt -= 180_001;
  process.env.AGENT_CHECKPOINT_GIT_LOG = path.join(f.root, "argv");
  const before = f.refs(), result = await worker(job);
  expect(result.outcome).toBe("verified-present");
  expect(f.refs()).toBe(before);
  const calls = readCalls();
  expect(calls.filter(c => c.argv[0] === "push" && !c.argv.includes("--dry-run"))).toHaveLength(0);
});

test("worker argv never bypasses hooks or changes protected refs", async () => {
  const f = fixture(), job = f.makeJob(f.commit());
  process.env.AGENT_CHECKPOINT_GIT_LOG = path.join(f.root, "argv");
  expect((await worker(job)).outcome).toBe("verified");
  const calls = readCalls();
  for (const call of calls) {
    expect(call.HK).not.toBe("0");
    for (const flag of ["--no-verify", "--force", "--force-with-lease", "--delete", "commit.gpgsign=false"]) {
      expect(call.argv.join(" ")).not.toContain(flag);
    }
  }
  expect(fs.readFileSync(source, "utf8")).not.toMatch(/--no-verify|--force|force-with-lease|HK=0|gpgsign=false/);
});

function readCalls(): { argv: string[]; HK?: string }[] {
  const calls = [];
  for (const line of fs.readFileSync(process.env.AGENT_CHECKPOINT_GIT_LOG!, "utf8").trim().split("\n")) {
    const value = JSON.parse(line);
    calls.push(value);
  }
  return calls;
}

const hasOmp = !!Bun.which("omp"); // runners without omp skip it

// Real OMP lifecycle, no host config, credentials, or live provider.
function localModel(agentDir: string) {
  const children = new Set<ReturnType<typeof spawn>>();
  const server = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    fetch() {
      const chunk = (delta: object, finish_reason: string | null = null) =>
        `data: ${
          JSON.stringify({
            id: "fixture",
            object: "chat.completion.chunk",
            created: 0,
            model: "checkpoint-fixture",
            choices: [{ index: 0, delta, finish_reason }],
          })
        }\n\n`;
      return new Response(chunk({ role: "assistant", content: "OK" }) + chunk({}, "stop") + "data: [DONE]\n\n", {
        headers: { "Content-Type": "text/event-stream" },
      });
    },
  });
  fs.mkdirSync(agentDir, { recursive: true });
  fs.writeFileSync(
    path.join(agentDir, "models.yml"),
    Bun.YAML.stringify({
      providers: {
        fixture: {
          baseUrl: `http://127.0.0.1:${server.port}/v1`,
          api: "openai-completions",
          apiKey: "fixture",
          models: [{
            id: "checkpoint-fixture",
            name: "Checkpoint fixture",
            input: ["text"],
            contextWindow: 128000,
            maxTokens: 256,
          }],
        },
      },
    }),
  );
  fs.writeFileSync(
    path.join(agentDir, "config.yml"),
    Bun.YAML.stringify({
      modelRoles: { default: "fixture/checkpoint-fixture", smol: "fixture/checkpoint-fixture" },
    }),
  );
  const turn = (cwd: string, args: string[]) =>
    new Promise<{ status: number | null; stdout: string; stderr: string }>((resolve, reject) => {
      const child = spawn("omp", ["--offline", "--no-judge", "--no-spotlight", "--thinking", "off", ...args], {
        cwd,
        env: { ...process.env, PI_CODING_AGENT_DIR: agentDir },
        timeout: 60_000,
        killSignal: "SIGKILL",
        stdio: ["ignore", "pipe", "pipe"],
      });
      children.add(child);
      let stdout = "", stderr = "";
      child.stdout.on("data", data => stdout += data);
      child.stderr.on("data", data => stderr += data);
      child.on("error", reject);
      child.on("close", status => {
        children.delete(child);
        resolve({ status, stdout, stderr });
      });
    });
  return {
    turn,
    stop: () => {
      for (const child of children) child.kill("SIGKILL");
      server.stop(true);
    },
  };
}
test.skipIf(!hasOmp)("real omp session publishes one verified ref and reports it next turn", async () => {
  const f = fixture();
  f.commit();
  const model = localModel(path.join(f.root, "agent"));
  const turn = (text: string) =>
    model.turn(f.repo, ["--no-extensions", "--no-session", "--no-tools", "-e", source, "-p", text]);
  try {
    const before = f.refs();
    const first = await turn("Reply exactly OK.");
    expect(first.status).toBe(0);
    expect(first.stdout + first.stderr).not.toContain("Failed to load extension");
    const job = await settled();
    expect(job.outcome).toBe("verified");
    const delta = f.refs().split("\n").filter(l => !before.split("\n").includes(l));
    expect(delta).toEqual([`${job.ref} ${git(f.repo, "rev-parse", "HEAD")}`]);
    const second = await turn("Reply exactly OK.");
    expect(second.status).toBe(0);
    expect(readJob(jobPath(job.key)).reported).toBe(true); // surfaced at the next turn start (print mode shows no notices)
  } finally {
    model.stop();
  }
}, 200000);

test("slow pre-push: handler returns pending first, the detached worker verifies later", async () => {
  const f = fixture();
  await f.event("agent_start");
  f.commit();
  fs.writeFileSync(path.join(f.repo, ".git/hooks/pre-push"), "#!/bin/sh\nsleep 3\n", { mode: 0o755 });
  const before = f.refs(), started = Date.now();
  await f.event("agent_end");
  expect(Date.now() - started).toBeLessThan(5000);
  expect(f.notices.join("\n")).toContain("agent-checkpoint: pending");
  expect(f.refs()).toBe(before);
  const job = await settled(30_000);
  expect(job.outcome).toBe("verified");
  expect(f.refs()).not.toBe(before);
}, 40000);

test("worker killed mid-push then restarted yields one additional remote ref", async () => {
  const f = fixture(), sha = f.commit(), job = f.makeJob(sha);
  fs.writeFileSync(path.join(f.repo, ".git/hooks/pre-push"), "#!/bin/sh\nsleep 2\n", { mode: 0o755 });
  writeJob(job);
  const before = f.refs(), jobFile = jobPath(job.key);
  const child = spawn("bun", [source, "--worker", jobFile], { env: process.env, stdio: "ignore", detached: true });
  try {
    const deadline = Date.now() + 10_000;
    while (readJob(jobFile).state !== "pushing") {
      if (Date.now() >= deadline) throw new Error("worker did not enter pushing within 10 seconds");
      await Bun.sleep(20);
    }
  } finally {
    if (child.pid && child.exitCode === null && child.signalCode === null) process.kill(-child.pid, "SIGKILL");
  }
  expect(readJob(jobFile).state).not.toBe("verified");
  const result = await worker(readJob(jobFile));
  expect(result.state).toBe("verified");
  expect(f.refs().split("\n").filter(l => !before.split("\n").includes(l))).toHaveLength(1);
}, 40000);

test.skipIf(!hasOmp)("deployed extension loads in a clean HOME without a load error", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "checkpoint-home-"));
  dirs.push(root);
  const home = path.join(root, "home");
  const ext = path.join(home, ".omp/agent/extensions/agent-checkpoint-publish.ts");
  fs.mkdirSync(path.dirname(ext), { recursive: true });
  fs.symlinkSync(source, ext);
  process.env.HOME = home;
  const model = localModel(path.join(home, ".omp/agent"));
  try {
    const run = await model.turn(root, ["--no-session", "--no-tools", "-p", "Reply exactly OK."]);
    expect(run.status).toBe(0);
    expect(run.stdout).toContain("OK");
    expect(run.stdout + run.stderr).not.toContain("Failed to load extension");
  } finally {
    model.stop();
  }
}, 100000);
