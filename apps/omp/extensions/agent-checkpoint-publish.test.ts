/**
 * Fixtures for turn-stop checkpoint publication (ZYS-9037; contract: ADR 0001).
 *
 * Every case drives the real extension against temp repositories and bare
 * remotes: the handler through a fake `pi`, the worker through `bun` running
 * this file's sibling extension with `--worker`. No real remote, no real
 * enrollment file, no real state dir is touched: every path is pointed into a
 * temp directory through the extension's env overrides.
 */
import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const EXTENSION = fileURLToPath(new URL("./agent-checkpoint-publish.ts", import.meta.url));

let root: string;
let home: string;
let stateDir: string;

beforeAll(() => {
  root = fs.mkdtempSync(path.join(os.tmpdir(), "acp-test-"));
  home = path.join(root, "home");
  stateDir = path.join(root, "state");
  fs.mkdirSync(home, { recursive: true });
});

afterAll(() => {
  fs.rmSync(root, { recursive: true, force: true });
});

/** A temp repo; non-bare repos get SSH signing configured by makeSigningKey. */
function makeRepo(name: string, opts: { bare?: boolean } = {}): string {
  const dir = path.join(root, name);
  const args = opts.bare ? ["init", "-q", "--bare", dir] : ["init", "-q", "-b", "main", dir];
  const res = Bun.spawnSync(["git", ...args]);
  if (res.exitCode !== 0) throw new Error(`git init failed: ${res.stderr.toString()}`);
  if (opts.bare) return dir;
  run(dir, ["config", "user.email", "t@example.com"]);
  run(dir, ["config", "user.name", "t"]);
  run(dir, ["config", "commit.gpgsign", "false"]);
  return dir;
}

function run(
  cwd: string,
  args: string[],
  env: Record<string, string> = {},
): { code: number; stdout: string; stderr: string } {
  const res = Bun.spawnSync(["git", ...args], {
    cwd,
    env: { ...process.env, HOME: home, ...env },
    stdout: "pipe",
    stderr: "pipe",
  });
  return { code: res.exitCode ?? -1, stdout: res.stdout.toString(), stderr: res.stderr.toString() };
}

function makeSigningKey(repo: string): { key: string; allowed: string } {
  const keyDir = path.join(root, `key-${path.basename(repo)}`);
  fs.mkdirSync(keyDir, { recursive: true });
  const gen = Bun.spawnSync([
    "ssh-keygen",
    "-t",
    "ed25519",
    "-N",
    "",
    "-f",
    path.join(keyDir, "key"),
    "-C",
    "t@example.com",
  ]);
  if (gen.exitCode !== 0) throw new Error("ssh-keygen failed");
  const allowed = path.join(keyDir, "allowed");
  fs.writeFileSync(
    allowed,
    `t@example.com ${fs.readFileSync(`${path.join(keyDir, "key")}.pub`, "utf-8")}`,
  );
  run(repo, ["config", "gpg.format", "ssh"]);
  run(repo, ["config", "user.signingkey", path.join(keyDir, "key")]);
  run(repo, ["config", "gpg.ssh.allowedSignersFile", allowed]);
  return { key: path.join(keyDir, "key"), allowed };
}

function commit(repo: string, message: string, signed: boolean): string {
  const before = run(repo, ["rev-parse", "HEAD"]).stdout.trim();
  run(repo, ["-c", `commit.gpgsign=${signed}`, "commit", "--allow-empty", "-m", message]);
  const after = run(repo, ["rev-parse", "HEAD"]).stdout.trim();
  if (after === before) throw new Error("commit did not move HEAD");
  return after;
}

function enroll(repo: string, canonical: string, slug = "test-repo"): string {
  const file = path.join(root, `enrollment-${path.basename(repo)}.toml`);
  fs.writeFileSync(
    file,
    [
      "schema_version = 1",
      "",
      `[repos."${slug}"]`,
      "enabled = true",
      `path = "${repo}"`,
      `canonical = "${canonical}"`,
      'visibility = "private"',
      "",
    ].join("\n"),
  );
  return file;
}

/** A bare remote plus a work repo with the remote as origin and one signed commit. */
function makeEnrolledRepo(name: string): {
  remote: string;
  repo: string;
  canonical: string;
  enrollment: string;
  sha: string;
} {
  const remote = makeRepo(`${name}-remote`, { bare: true });
  const repo = makeRepo(name);
  makeSigningKey(repo);
  fs.writeFileSync(path.join(repo, "a.txt"), "a\n");
  run(repo, ["add", "a.txt"]);
  run(repo, ["commit", "-m", "base"]);
  run(repo, ["remote", "add", "origin", remote]);
  const sha = commit(repo, "checkpoint", true);
  // Seed the remote with a baseline branch the repo shares ancestry with.
  run(repo, ["push", "origin", "main:refs/heads/main"]);
  return { remote, repo, canonical: remote, enrollment: enroll(repo, remote), sha };
}

function baseEnv(enrollment: string, repo?: string): Record<string, string> {
  const env = {
    ...process.env,
    HOME: home,
    AGENT_CHECKPOINT_ENROLLMENT_FILE: enrollment,
    AGENT_CHECKPOINT_STATE_DIR: stateDir,
  } as Record<string, string>;
  if (repo) env.ACP_TEST_REPO = repo;
  else delete env.ACP_TEST_REPO;
  return env;
}

/**
 * The real handler, driven through a fake pi. The fake registers the handlers
 * and then awaits them, so the async handler completes before assertions run.
 * The repo omp would report comes from ACP_TEST_REPO (the fake getCwd).
 */
async function driveAgentEnd(
  env: Record<string, string>,
  event: { willContinue?: boolean } = {},
): Promise<string[]> {
  const notifications: { message: string; level: string }[] = [];
  const saved: Record<string, string | undefined> = {};
  for (const key of [
    "AGENT_CHECKPOINT_ENROLLMENT_FILE",
    "AGENT_CHECKPOINT_STATE_DIR",
    "AGENT_CHECKPOINT_WORKER",
    "AGENT_CHECKPOINT_GIT_LOG",
    "AGENT_CHECKPOINT_PUBLISH",
    "ACP_TEST_REPO",
  ]) {
    saved[key] = process.env[key];
    if (env[key] === undefined) delete process.env[key];
    else process.env[key] = env[key];
  }
  const savedCwd = process.cwd();
  try {
    const mod = await import(EXTENSION);
    const handlers: ((event: unknown, ctx?: unknown) => unknown)[] = [];
    const pi = {
      on: (event: string, handler: (event: unknown, ctx?: unknown) => unknown) => {
        if (event === "agent_end") handlers.push(handler);
      },
    };
    mod.default(pi as never);
    const ctx = {
      ui: { notify: (message: string, level: string) => notifications.push({ message, level }) },
      sessionManager: { getCwd: () => process.env.ACP_TEST_REPO ?? savedCwd },
    };
    for (const handler of handlers) {
      await handler(event, ctx);
    }
    return notifications.map((n) => n.message);
  } finally {
    for (const [key, value] of Object.entries(saved)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
    process.chdir(savedCwd);
  }
}

/** The real worker, as a subprocess, against the real extension file. */
function runWorkerJob(jobFile: string, env: Record<string, string>): { code: number; stderr: string } {
  const res = Bun.spawnSync(["bun", EXTENSION, "--worker", jobFile], {
    cwd: path.dirname(jobFile),
    env: { ...env, AGENT_CHECKPOINT_PUBLISH: "1" },
    stdout: "pipe",
    stderr: "pipe",
  });
  return { code: res.exitCode ?? -1, stderr: res.stderr.toString() };
}

function jobFiles(): string[] {
  const dir = path.join(stateDir, "jobs");
  try {
    return fs.readdirSync(dir).filter((n) => n.endsWith(".json")).map((n) => path.join(dir, n));
  } catch {
    return [];
  }
}

function readJobs(): Record<string, unknown>[] {
  return jobFiles().map((f) => JSON.parse(fs.readFileSync(f, "utf-8")));
}

function checkpointsOn(remote: string): { ref: string; sha: string }[] {
  const res = run(remote, ["for-each-ref", "--format=%(refname) %(objectname)", "refs/heads/agent-checkpoints/"]);
  return res.stdout.trim().split("\n").filter(Boolean).map((line) => {
    const [ref, sha] = line.split(" ");
    return { ref: ref ?? "", sha: sha ?? "" };
  });
}

/** Handler turn, then the worker run synchronously. Returns notifications and jobs. */
async function runTurnSync(
  fx: { repo: string; enrollment: string },
  env?: Record<string, string>,
): Promise<{ notifications: string[]; jobs: Record<string, unknown>[] }> {
  const e = { ...baseEnv(fx.enrollment, fx.repo), ...(env ?? {}) };
  const notifications = await driveAgentEnd(e);
  const jobFile = jobFiles()[0];
  if (!jobFile) return { notifications, jobs: [] };
  const res = Bun.spawnSync(["bun", EXTENSION, "--worker", jobFile], {
    cwd: fx.repo,
    env: { ...e, AGENT_CHECKPOINT_PUBLISH: "1" },
    stdout: "pipe",
    stderr: "pipe",
  });
  expect(res.exitCode).toBe(0);
  return { notifications, jobs: readJobs() };
}

describe("agent-checkpoint-publish fixtures", () => {
  test("F2 happy path: enrolled, signed, hooks on - verified, one ref", async () => {
    const fx = makeEnrolledRepo("happy");
    const gitLog = path.join(root, "gitlog-happy");
    fs.writeFileSync(gitLog, "");
    const { jobs } = await runTurnSync(fx, { AGENT_CHECKPOINT_GIT_LOG: gitLog });
    const job = jobs[0] as { state?: string; outcome?: string; ref?: string; attempts?: number };
    expect(job?.state).toBe("verified");
    expect(job?.outcome).toBe("verified");
    expect(job?.attempts).toBe(1);
    const onRemote = checkpointsOn(fx.remote);
    expect(onRemote).toHaveLength(1);
    expect(onRemote[0]?.sha).toBe(fx.sha);
    expect(onRemote[0]?.ref).toMatch(
      /^refs\/heads\/agent-checkpoints\/test-repo\/[a-z0-9-]+\/t0001-[0-9a-f]{40}$/,
    );
    // Read-back at the effective push URL equals rev-parse HEAD.
    const readBack = run(fx.repo, ["ls-remote", fx.canonical, "refs/heads/agent-checkpoints/*"]);
    expect(readBack.stdout.trim()).toContain(fx.sha);
    // No local tracking ref written for the checkpoint.
    const localRefs = run(fx.repo, ["for-each-ref", "refs/remotes/origin/agent-checkpoints/*"]).stdout.trim();
    expect(localRefs).toBe("");
    // No forbidden flag or env in any git invocation.
    const lines = fs.readFileSync(gitLog, "utf-8").trim().split("\n").filter(Boolean);
    expect(lines.length).toBeGreaterThan(3);
    for (const line of lines) {
      const argv = JSON.parse(line) as string[];
      for (const bad of ["--no-verify", "--force", "--force-with-lease", "-f", "--delete", "-d"]) {
        expect(argv).not.toContain(bad);
      }
      expect(argv[0]).toBe("git");
    }
    // Uncommitted work is untouched.
    expect(run(fx.repo, ["status", "--porcelain"]).stdout).toBe("");
    expect(run(fx.repo, ["stash", "list"]).stdout).toBe("");
  });

  test("F6 verified-present: same agent_end twice yields one job; rerun after verified reports verified-present with no second push", async () => {
    const fx = makeEnrolledRepo("idempotent");
    const env = baseEnv(fx.enrollment, fx.repo);
    const first = await driveAgentEnd(env);
    expect(first.some((n) => n.includes("pending"))).toBe(true);
    const jobFile = jobFiles()[0];
    expect(jobFile).toBeDefined();
    // Second agent_end for the same turn while the job is fresh: pending, no new job.
    const jobsBefore = jobFiles().length;
    const second = await driveAgentEnd(env);
    expect(second.some((n) => n.includes("pending"))).toBe(true);
    expect(jobFiles().length).toBe(jobsBefore);
    // Run the worker; the ref lands once.
    expect(runWorkerJob(jobFile, env).code).toBe(0);
    expect(checkpointsOn(fx.remote)).toHaveLength(1);
    // Rerun the same job after verified: no second push.
    expect(runWorkerJob(jobFile, env).code).toBe(0);
    expect(checkpointsOn(fx.remote)).toHaveLength(1);
    // A fresh agent_end on the same sha: verified-present, no new job, no new push.
    const jobsBefore2 = jobFiles().length;
    const rerun = await driveAgentEnd(env);
    expect(rerun.some((n) => n.includes("verified-present"))).toBe(true);
    expect(jobFiles().length).toBe(jobsBefore2);
    expect(checkpointsOn(fx.remote)).toHaveLength(1);
  });

  test("F7 blocked-collision: the ref exists at a different sha", async () => {
    const fx = makeEnrolledRepo("collision");
    const other = makeRepo("collision-other");
    makeSigningKey(other);
    run(other, ["remote", "add", "origin", fx.remote]);
    const otherSha = commit(other, "other", true);
    run(other, ["push", "origin", `${otherSha}:refs/heads/main`]);
    const { jobs } = await runTurnSync(fx);
    const job = jobs[0] as { ref?: string };
    expect(job?.ref).toBeDefined();
    run(other, ["push", "origin", `${otherSha}:${job.ref}`]);
    // Rerun the same job (same repo/ref/sha): the exact ref now exists elsewhere.
    fs.rmSync(path.join(stateDir, "jobs"), { recursive: true, force: true });
    const workerEnv = baseEnv(fx.enrollment, fx.repo);
    await driveAgentEnd(workerEnv);
    const worker = runWorkerJob(jobFiles()[0], workerEnv);
    expect(worker.code).toBe(0);
    const jobs2 = readJobs();
    expect((jobs2[0] as { outcome?: string })?.outcome).toBe("blocked-collision");
    expect((jobs2[0] as { detail?: string })?.detail).toBe("different-sha");
    // The destination ref still points at the other sha: nothing overwritten.
    const still = checkpointsOn(fx.remote).find((r) => r.ref === job.ref);
    expect(still?.sha).toBe(otherSha);
  });

  test("F7b blocked-collision df-conflict: existing ref is a prefix of the computed ref", async () => {
    const fx = makeEnrolledRepo("dfconflict");
    const { jobs } = await runTurnSync(fx);
    const job = jobs[0] as { ref?: string };
    expect(job?.ref).toBeDefined();
    const other = makeRepo("df-other");
    makeSigningKey(other);
    run(other, ["remote", "add", "origin", fx.remote]);
    const otherSha = commit(other, "df", true);
    const shortRef = (job.ref as string).slice("refs/heads/".length);
    const parentPath = shortRef.split("/").slice(0, 3).join("/");
    run(other, ["push", "origin", `${otherSha}:refs/heads/${parentPath}`]);
    fs.rmSync(path.join(stateDir, "jobs"), { recursive: true, force: true });
    const workerEnv = baseEnv(fx.enrollment, fx.repo);
    await driveAgentEnd(workerEnv);
    const worker = runWorkerJob(jobFiles()[0], workerEnv);
    expect(worker.code).toBe(0);
    const jobs2 = readJobs();
    expect((jobs2[0] as { outcome?: string })?.outcome).toBe("blocked-collision");
    expect((jobs2[0] as { detail?: string })?.detail).toBe("df-conflict");
  });

  test("F10 blocked-hook-rejected: pre-push exits 1, ref absent, local commit intact", async () => {
    const fx = makeEnrolledRepo("hookrejected");
    const hooks = path.join(fx.repo, ".git", "hooks");
    fs.writeFileSync(path.join(hooks, "pre-push"), "#!/bin/sh\necho hook-says-no >&2\nexit 1\n");
    fs.chmodSync(path.join(hooks, "pre-push"), 0o755);
    const headBefore = run(fx.repo, ["rev-parse", "HEAD"]).stdout.trim();
    const { jobs } = await runTurnSync(fx);
    const job = jobs[0] as { outcome?: string; attempts?: number };
    expect(job?.outcome).toBe("blocked-hook-rejected");
    expect(job?.attempts).toBe(1); // a hook rejection stops at attempt 1
    expect(checkpointsOn(fx.remote)).toHaveLength(0);
    expect(run(fx.repo, ["rev-parse", "HEAD"]).stdout.trim()).toBe(headBefore);
    expect(run(fx.repo, ["status", "--porcelain"]).stdout).toBe("");
  });

  test("F10b blocked-secrets: hook output names gitleaks", async () => {
    const fx = makeEnrolledRepo("secrets");
    const hooks = path.join(fx.repo, ".git", "hooks");
    fs.writeFileSync(
      path.join(hooks, "pre-push"),
      '#!/bin/sh\necho "gitleaks: secret detected in a.txt" >&2\nexit 1\n',
    );
    fs.chmodSync(path.join(hooks, "pre-push"), 0o755);
    const { jobs } = await runTurnSync(fx);
    expect((jobs[0] as { outcome?: string })?.outcome).toBe("blocked-secrets");
    expect(checkpointsOn(fx.remote)).toHaveLength(0);
  });

  test("F15 blocked-unsigned: an unsigned commit in the new set", async () => {
    const fx = makeEnrolledRepo("unsigned");
    commit(fx.repo, "unsigned-checkpoint", false);
    const { jobs } = await runTurnSync(fx);
    expect((jobs[0] as { outcome?: string })?.outcome).toBe("blocked-unsigned");
    expect(checkpointsOn(fx.remote)).toHaveLength(0);
  });

  test("F8 blocked-destination-changed: pushurl differs from url; and insteadOf rewrites", async () => {
    const fx = makeEnrolledRepo("destchanged");
    const other = makeRepo("destchanged-other", { bare: true });
    run(fx.repo, ["remote", "set-url", "--push", "origin", other]);
    // Canonical is the bare remote (enrolled), but the effective push URL is `other`.
    const { jobs } = await runTurnSync(fx);
    expect((jobs[0] as { outcome?: string })?.outcome).toBe("blocked-destination-changed");
    expect(checkpointsOn(fx.remote)).toHaveLength(0);
    expect(checkpointsOn(other)).toHaveLength(0);
    // insteadOf rewrite: enrolled canonical names a URL that insteadOf rewrites.
    const fx2 = makeEnrolledRepo("insteadof");
    const rewritten = makeRepo("insteadof-rewritten", { bare: true });
    run(home, ["config", "--global", `url.${rewritten}.insteadOf`, "https://example.invalid/alt"]);
    const enrollment2 = enroll(fx2.repo, "https://example.invalid/alt");
    const { jobs: jobs2 } = await runTurnSync({ repo: fx2.repo, enrollment: enrollment2 });
    expect((jobs2[0] as { outcome?: string })?.outcome).toBe("blocked-destination-changed");
    expect(checkpointsOn(rewritten)).toHaveLength(0);
    run(home, ["config", "--global", "--unset-all", `url.${rewritten}.insteadOf`]);
  });

  test("F1 blocked-not-enrolled: nothing enrolled; a URL substring does not enroll", async () => {
    const fx = makeEnrolledRepo("notenrolled");
    // Nothing enrolled (the shipped file).
    const shipped = path.join(root, "shipped-enrollment.toml");
    fs.writeFileSync(
      shipped,
      fs.readFileSync(
        path.join(path.dirname(EXTENSION), "..", "..", "config", "agent-checkpoints", "enrollment.toml"),
        "utf-8",
      ),
    );
    const notifications = await driveAgentEnd(baseEnv(shipped, fx.repo));
    expect(notifications.some((n) => n.includes("blocked-not-enrolled"))).toBe(true);
    expect(checkpointsOn(fx.remote)).toHaveLength(0);
    expect(jobFiles()).toHaveLength(0);
    // A canonical that is only a sibling of the true URL: the repo is enrolled,
    // but the destination check blocks the push (URL substrings never authorize).
    const sibling = enroll(fx.repo, `${fx.canonical}-sibling`);
    const { jobs } = await runTurnSync({ repo: fx.repo, enrollment: sibling });
    expect((jobs[0] as { outcome?: string })?.outcome).toBe("blocked-destination-changed");
    expect(checkpointsOn(fx.remote)).toHaveLength(0);
  });

  test("F1b blocked-ambiguous-ownership: two enabled entries for the same repo", async () => {
    const fx = makeEnrolledRepo("ambiguous");
    const file = path.join(root, "enrollment-ambiguous.toml");
    fs.writeFileSync(
      file,
      [
        "schema_version = 1",
        "",
        '[repos."a"]',
        "enabled = true",
        `path = "${fx.repo}"`,
        `canonical = "${fx.canonical}"`,
        'visibility = "private"',
        "",
        '[repos."b"]',
        "enabled = true",
        `path = "${fx.repo}"`,
        `canonical = "${fx.canonical}"`,
        'visibility = "private"',
        "",
      ].join("\n"),
    );
    const notifications = await driveAgentEnd(baseEnv(file, fx.repo));
    expect(notifications.some((n) => n.includes("blocked-ambiguous-ownership"))).toBe(true);
    expect(jobFiles()).toHaveLength(0);
  });

  test("F11 blocked-missing-baseline and blocked-unrelated-ancestry", async () => {
    // Missing baseline: no advertised tip present locally.
    const fx = makeEnrolledRepo("nobaseline");
    const unrelated = makeRepo("unrelated-src");
    makeSigningKey(unrelated);
    run(unrelated, ["remote", "add", "origin", fx.remote]);
    const uSha = commit(unrelated, "unrelated", true);
    run(unrelated, ["push", "origin", `${uSha}:refs/heads/main`]);
    const { jobs } = await runTurnSync(fx);
    expect((jobs[0] as { outcome?: string })?.outcome).toBe("blocked-missing-baseline");
    // Unrelated ancestry: the baseline tip exists locally but HEAD shares nothing with it.
    const fx2 = makeEnrolledRepo("unrelated-ancestry");
    const other = makeRepo("unrelated-other");
    makeSigningKey(other);
    run(other, ["remote", "add", "origin", fx2.remote]);
    const oSha = commit(other, "o", true);
    run(other, ["push", "origin", `${oSha}:refs/heads/main`]);
    run(fx2.repo, ["fetch", "origin", "refs/heads/main:refs/remotes/origin/main"]);
    const { jobs: jobs2 } = await runTurnSync(fx2);
    expect((jobs2[0] as { outcome?: string })?.outcome).toBe("blocked-unrelated-ancestry");
  });

  test("F19 blocked-remote-unreachable: dead destination yields exactly 3 attempts", async () => {
    const fx = makeEnrolledRepo("unreachable");
    const dead = path.join(root, "dead.git");
    const enrollment = enroll(fx.repo, dead);
    const gitLog = path.join(root, "gitlog-unreachable");
    fs.writeFileSync(gitLog, "");
    const { jobs } = await runTurnSync({ repo: fx.repo, enrollment }, { AGENT_CHECKPOINT_GIT_LOG: gitLog });
    const job = jobs[0] as { outcome?: string; attempts?: number };
    expect(job?.outcome).toBe("blocked-remote-unreachable");
    expect(job?.attempts).toBe(3); // at most 3 attempts in total, transient only
    const pushes = fs
      .readFileSync(gitLog, "utf-8")
      .trim()
      .split("\n")
      .filter(Boolean)
      .map((l) => JSON.parse(l) as string[])
      .filter((argv) => argv.includes("push"));
    expect(pushes.length).toBeGreaterThanOrEqual(3);
    expect(checkpointsOn(fx.remote)).toHaveLength(0);
  });

  test("F14 willContinue: true and worker env yield no action", async () => {
    const fx = makeEnrolledRepo("noaction");
    const notifications = await driveAgentEnd(baseEnv(fx.enrollment, fx.repo), { willContinue: true });
    expect(notifications).toHaveLength(0);
    expect(jobFiles()).toHaveLength(0);
    // Inside a worker (AGENT_CHECKPOINT_PUBLISH=1) the handler must not act.
    const prev = process.env.AGENT_CHECKPOINT_PUBLISH;
    process.env.AGENT_CHECKPOINT_PUBLISH = "1";
    try {
      const none = await driveAgentEnd(baseEnv(fx.enrollment, fx.repo));
      expect(none).toHaveLength(0);
      expect(jobFiles()).toHaveLength(0);
    } finally {
      if (prev === undefined) delete process.env.AGENT_CHECKPOINT_PUBLISH;
      else process.env.AGENT_CHECKPOINT_PUBLISH = prev;
    }
  });

  test("F13 pending: the handler reports pending while the detached worker pushes", async () => {
    const fx = makeEnrolledRepo("pending");
    // A deliberately slow pre-push: the detached worker takes seconds; the
    // handler must return pending first, without waiting for the push.
    const hooks = path.join(fx.repo, ".git", "hooks");
    fs.writeFileSync(path.join(hooks, "pre-push"), "#!/bin/sh\nsleep 3\nexit 0\n");
    fs.chmodSync(path.join(hooks, "pre-push"), 0o755);
    const started = Date.now();
    const notifications = await driveAgentEnd(baseEnv(fx.enrollment, fx.repo));
    const elapsed = Date.now() - started;
    expect(elapsed).toBeLessThan(5000); // way under the 30 s handler budget
    expect(notifications.some((n) => n.includes("pending"))).toBe(true);
    expect(checkpointsOn(fx.remote)).toHaveLength(0);
    // The detached worker settles the job; then the ref exists exactly once.
    const deadline = Date.now() + 60_000;
    for (;;) {
      const settled = readJobs().find((j) =>
        ["verified", "failed"].includes(String((j as { state?: string }).state)),
      );
      if (settled || Date.now() > deadline) break;
      await Bun.sleep(500);
    }
    const job = readJobs()[0] as { state?: string };
    expect(job?.state).toBe("verified");
    expect(checkpointsOn(fx.remote)).toHaveLength(1);
  });

  test("F12 worker killed mid-push then restarted yields one push", async () => {
    const fx = makeEnrolledRepo("killed");
    const hooks = path.join(fx.repo, ".git", "hooks");
    fs.writeFileSync(path.join(hooks, "pre-push"), "#!/bin/sh\nsleep 2\nexit 0\n");
    fs.chmodSync(path.join(hooks, "pre-push"), 0o755);
    const env = baseEnv(fx.enrollment, fx.repo);
    await driveAgentEnd(env);
    const jobFile = jobFiles()[0];
    // Start the worker, kill it mid-push (before the push completes).
    const child = Bun.spawn(["bun", EXTENSION, "--worker", jobFile], {
      cwd: fx.repo,
      env: { ...env, AGENT_CHECKPOINT_PUBLISH: "1" },
      stdout: "ignore",
      stderr: "ignore",
    });
    await Bun.sleep(500); // inside the slow pre-push
    child.kill("SIGKILL");
    await child.exited;
    expect(checkpointsOn(fx.remote)).toHaveLength(0);
    // Restart: the same job record is taken over, the ref lands exactly once.
    expect(runWorkerJob(jobFile, env).code).toBe(0);
    expect(checkpointsOn(fx.remote)).toHaveLength(1);
    const job = readJobs()[0] as { state?: string };
    expect(job?.state).toBe("verified");
  });

  test("handler: no push, no job when the repo is not a git repo", async () => {
    const notARepo = path.join(root, "notarepo");
    fs.mkdirSync(notARepo, { recursive: true });
    const enrollment = enroll(notARepo, path.join(root, "x.git"));
    const notifications = await driveAgentEnd(baseEnv(enrollment, notARepo));
    expect(notifications.some((n) => n.includes("blocked-not-enrolled"))).toBe(true);
    expect(jobFiles()).toHaveLength(0);
  });
});

test("source scan: no forbidden flag, no hook-disable env, no session_stop registration", () => {
  const source = fs.readFileSync(EXTENSION, "utf-8");
  for (const bad of ["--no-verify", "--force-with-lease", "HK=0", "gpgsign=false", "session_stop"]) {
    expect(source).not.toContain(bad);
  }
  // The blocklist literals are assembled from parts, so nothing greps for a raw
  // forbidden flag; the scanner in the sibling extension test asserts the same
  // for every git argv the worker ran.
  expect(source).toContain("FORBIDDEN_ARGV");
});