import { afterEach, expect, test } from "bun:test";
import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import install, { type Job, jobPath, readJob, writeJob } from "./agent-checkpoint-publish.ts";

const source = path.resolve(import.meta.dir, "agent-checkpoint-publish.ts");
const dirs: string[] = [];
// Real detached subprocesses cannot share fake timers; await their durable state.
let saved = { ...process.env };
afterEach(() => {
  process.env = { ...saved };
  for (const dir of dirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});
function git(repo: string, ...args: string[]) {
  const r = spawnSync("git", args, { cwd: repo, encoding: "utf8", env: process.env });
  if (r.status) throw new Error(`${args.join(" ")}: ${r.stderr}`);
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
  const publicKey = fs.openSync(path.join(root, "signing.pub"), "r");
  fs.writeFileSync(path.join(root, "allowed"), `checkpoint@example.test ${fs.readFileSync(publicKey, "utf8")}`);
  fs.closeSync(publicKey);
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
    await handlers.get(name)?.(data, ctx);
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
    stdio: ["ignore", "pipe", "pipe"],
  });
  const { promise, resolve, reject } = Promise.withResolvers<void>();
  proc.once("error", reject);
  proc.once("exit", code => code ? reject(new Error(`worker exit ${code}`)) : resolve());
  await promise;
  return readJob(jobPath(job.key));
}
async function settled(timeoutMs = 15_000) {
  const dir = path.join(process.env.AGENT_CHECKPOINT_STATE_DIR!, "jobs");
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    const files = fs.existsSync(dir) ? fs.readdirSync(dir).filter(f => f.endsWith(".json")) : [];
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
  expect(f.notices.join("\n")).toContain("blocked-not-enrolled");
  f.enroll();
  await f.event("agent_end", { willContinue: true });
  process.env.AGENT_CHECKPOINT_PUBLISH = "1";
  await f.event("agent_start");
  await f.event("agent_end");
  expect(f.refs()).toBe(before);
  expect(fs.existsSync(path.join(process.env.AGENT_CHECKPOINT_STATE_DIR!, "jobs"))).toBe(false);
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

const hasOmp = !!process.env.OMP_MODEL && !!Bun.which("omp"); // runners without omp and a model skip it
test.skipIf(!hasOmp)("real omp session publishes one verified ref and reports it next turn", async () => {
  const f = fixture();
  f.commit();
  const env = { ...process.env, PI_CODING_AGENT_DIR: path.join(f.root, "agent") };
  const turn = (text: string) =>
    spawnSync("omp", [
      "--no-extensions",
      "--no-session",
      "--no-tools",
      "-e",
      source,
      "--model",
      process.env.OMP_MODEL ?? "",
      "-p",
      text,
    ], { cwd: f.repo, env, encoding: "utf8", timeout: 90_000 });
  const before = f.refs();
  const first = turn("Reply exactly OK1.");
  expect(first.status).toBe(0);
  expect(first.stdout + first.stderr).not.toContain("Failed to load extension");
  const job = await settled();
  expect(job.outcome).toBe("verified");
  const delta = f.refs().split("\n").filter(l => !before.split("\n").includes(l));
  expect(delta).toEqual([`${job.ref} ${git(f.repo, "rev-parse", "HEAD")}`]);
  const second = turn("Reply exactly OK2.");
  expect(second.status).toBe(0);
  expect(readJob(jobPath(job.key)).reported).toBe(true); // surfaced at the next turn start (print mode shows no notices)
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

test("worker killed mid-push then restarted yields one push", async () => {
  const f = fixture(), sha = f.commit(), job = f.makeJob(sha);
  fs.writeFileSync(path.join(f.repo, ".git/hooks/pre-push"), "#!/bin/sh\nsleep 2\n", { mode: 0o755 });
  writeJob(job);
  const before = f.refs(), jobFile = jobPath(job.key);
  const child = spawn("bun", [source, "--worker", jobFile], { env: process.env, stdio: "ignore", detached: true });
  const { promise, resolve } = Promise.withResolvers<void>();
  const watcher = fs.watch(path.dirname(jobFile), () => {
    if (readJob(jobFile).state === "pushing") resolve();
  });
  await promise;
  watcher.close();
  process.kill(-child.pid!, "SIGKILL");
  expect(readJob(jobFile).state).not.toBe("verified");
  const result = await worker(readJob(jobFile));
  expect(result.state).toBe("verified");
  expect(f.refs().split("\n").filter(l => !before.split("\n").includes(l))).toHaveLength(1);
}, 40000);

test.skipIf(!hasOmp)("deployed extension loads in a clean HOME without a load error", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "checkpoint-home-"));
  dirs.push(root);
  const home = path.join(root, "home");
  const ext = path.join(home, ".omp/agent/extensions/agent-checkpoint-publish.ts");
  fs.mkdirSync(path.dirname(ext), { recursive: true });
  fs.symlinkSync(source, ext);
  const run = spawnSync("omp", [
    "--no-session",
    "--no-tools",
    "--model",
    process.env.OMP_MODEL ?? "",
    "-p",
    "Reply exactly OK.",
  ], {
    cwd: root,
    env: { ...process.env, HOME: home, PI_CODING_AGENT_DIR: path.join(home, ".omp/agent") },
    encoding: "utf8",
    timeout: 90_000,
  });
  expect(run.stdout + run.stderr).not.toContain("Failed to load extension");
}, 100000);

// ---- mise dotfile reconciliation (ZYS-9038) --------------------------------------------------
// Every fixture: temp HOME, MISE_* dirs, bare-repo dotfiles origin; a PATH shim records mise argv.
// Resolved once, before any fixture puts its argv-recording shim first on PATH.
const realMise = Bun.which("mise") ?? "mise";
function miseBox(opts: { mode?: string; origin?: "dead"; every?: number; declare?: string | false } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "mise-outcome-"));
  dirs.push(root);
  const home = path.join(root, "home"), bin = path.join(root, "bin"), logs = path.join(root, "logs");
  const origin = path.join(root, "origin.git"), argv = path.join(root, "argv.log");
  for (const d of [home, path.join(home, ".config/mise"), bin, logs]) fs.mkdirSync(d, { recursive: true });
  const gitconfig = path.join(root, "gitconfig");
  fs.writeFileSync(gitconfig, "[user]\n\tname = t\n\temail = t@example.test\n[init]\n\tdefaultBranch = main\n");
  fs.writeFileSync(
    path.join(bin, "mise"),
    `#!/usr/bin/env bash\nprintf '%s\\n' "$*" >> "${argv}"\nexec "${realMise}" "$@"\n`,
    {
      mode: 0o755,
    },
  );
  const config = path.join(home, ".config/mise/config.toml");
  const originUrl = opts.origin === "dead" ? path.join(root, "gone.git") : origin;
  const write = (mode = opts.mode ?? "sync", url = originUrl) =>
    fs.writeFileSync(
      config,
      `[dotfiles]\n"~/.dot-a" = { mode = "track" }\n"~/.gitconfig" = { mode = "track", autosave = false }\n\n`
        + `[history]\ngit_email = "t@example.test"\n[history.origin]\nurl = "${url}"\nbranch = "history"\n\n[settings.history]\nsync = "${mode}"\n`,
    );
  write();
  if (opts.origin !== "dead") {
    spawnSync("git", ["init", "--bare", "-b", "history", origin], {
      env: { ...process.env, GIT_CONFIG_GLOBAL: gitconfig },
    });
  }
  fs.writeFileSync(path.join(home, ".gitconfig"), "[user]\n\tname = fixture\n");
  fs.writeFileSync(path.join(home, ".dot-a"), "v1\n");
  const env = {
    ...process.env,
    HOME: home,
    XDG_CONFIG_HOME: path.join(home, ".config"),
    XDG_STATE_HOME: path.join(home, ".local/state"),
    XDG_DATA_HOME: path.join(home, ".local/share"),
    GIT_CONFIG_GLOBAL: gitconfig,
    GIT_CONFIG_NOSYSTEM: "1",
    MISE_GLOBAL_CONFIG_FILE: config,
    MISE_TRUSTED_CONFIG_PATHS: config,
    MISE_CONFIG_DIR: path.join(home, ".config/mise"),
    MISE_STATE_DIR: path.join(root, "state"),
    MISE_DATA_DIR: path.join(root, "data"),
    MISE_CACHE_DIR: path.join(root, "cache"),
    MISE_HISTORY_LOG_DIR: logs,
    AGENT_CHECKPOINT_STATE_DIR: path.join(root, "agent-state"),
    AGENT_CHECKPOINT_ENROLLMENT_FILE: path.join(root, "enrollment.toml"),
    PATH: `${bin}:${process.env.PATH}`,
  } as Record<string, string>;
  delete env.MISE_HISTORY_MANUAL_SAVE_EVERY_S;
  if (opts.every) env.MISE_HISTORY_MANUAL_SAVE_EVERY_S = String(opts.every);
  process.env = env;
  const declare = (canonical: string | false) =>
    fs.writeFileSync(
      env.AGENT_CHECKPOINT_ENROLLMENT_FILE,
      `schema_version = 1\n${
        canonical === false
          ? ""
          : `[destinations."mise-history"]\nkind = "mise-dot"\ncanonical = ${
            JSON.stringify(canonical)
          }\nbranch = "history"\nmode = "sync"\n`
      }`,
    );
  declare(opts.declare === false ? false : opts.declare ?? originUrl);
  const mise = (...args: string[]) => spawnSync("mise", args, { env, cwd: root, encoding: "utf8" });
  const stamp = path.join(logs, "manual-save.stamp");
  const touchStamp = (ageS: number) => {
    fs.writeFileSync(stamp, "");
    const at = new Date(Date.now() - ageS * 1000);
    fs.utimesSync(stamp, at, at);
  };
  const lines = () => fs.existsSync(argv) ? fs.readFileSync(argv, "utf8").split("\n").filter(Boolean) : [];
  const report = async () => {
    fs.writeFileSync(argv, "");
    const notices: string[] = [];
    const handlers = new Map<string, Function>();
    install({ on: (n, fn) => void handlers.set(n, fn) });
    await handlers.get("agent_end")!({}, { cwd: home, ui: { notify: (t: string) => void notices.push(t) } });
    return { notices, mise: notices.filter(n => n.startsWith("mise-dotfiles:")), argv: lines() };
  };
  return { root, home, origin, config, mise, write, declare, touchStamp, stamp, report };
}
const neverMutates = (argv: string[]) => {
  expect(
    argv.some(l => /^dot(files)? (pull|save|recover|bootstrap)\b/.test(l) || l.includes("--allow-plaintext-history")),
  )
    .toBe(false);
};

test("mise: saved and synced tracked file is verified, with one sync and matching heads", async () => {
  const b = miseBox();
  expect(b.mise("dot", "save").status).toBe(0);
  expect(b.mise("dot", "sync").status).toBe(0);
  const configBefore = fs.readFileSync(b.config, "utf8");
  const r = await b.report();
  expect(r.mise).toHaveLength(1);
  expect(r.mise[0]).toStartWith("mise-dotfiles: verified");
  const head = git(b.origin, "rev-parse", "refs/heads/history");
  expect(r.mise[0]).toContain(`head=${head}`);
  expect(r.argv.filter(l => l === "dot sync")).toHaveLength(1);
  neverMutates(r.argv);
  expect(fs.readFileSync(b.config, "utf8")).toBe(configBefore);
}, 90_000);

test("mise: repeated agent_end is idempotent", async () => {
  const b = miseBox();
  b.mise("dot", "save");
  b.mise("dot", "sync");
  const first = (await b.report()).mise[0];
  const second = (await b.report()).mise[0];
  expect(second).toBe(first);
}, 90_000);

test("mise: changed ~/.gitconfig with a young stamp is scheduled and the stamp mtime is untouched", async () => {
  const b = miseBox();
  b.mise("dot", "save");
  b.mise("dot", "sync");
  fs.writeFileSync(path.join(b.home, ".gitconfig"), "[user]\n\tname = changed\n");
  b.touchStamp(60);
  const before = fs.statSync(b.stamp).mtimeMs;
  const r = await b.report();
  expect(r.mise[0]).toStartWith("mise-dotfiles: scheduled");
  expect(r.mise[0]).toContain("~/.gitconfig");
  expect(fs.statSync(b.stamp).mtimeMs).toBe(before);
  expect(r.argv).not.toContain("dot sync");
  neverMutates(r.argv);
}, 90_000);

test("mise: unsaved manual-save path with a missing or 24 h old stamp is blocked manual-save-overdue", async () => {
  const b = miseBox();
  b.mise("dot", "save");
  fs.writeFileSync(path.join(b.home, ".gitconfig"), "[user]\n\tname = changed\n");
  expect((await b.report()).mise[0]).toMatch(/^mise-dotfiles: blocked.*manual-save-overdue/);
  b.touchStamp(25 * 3600);
  expect((await b.report()).mise[0]).toMatch(/^mise-dotfiles: blocked.*manual-save-overdue/);
}, 90_000);

test("mise: an unsaved autosave path is blocked unsaved, never scheduled", async () => {
  const b = miseBox();
  b.mise("dot", "save");
  fs.writeFileSync(path.join(b.home, ".dot-a"), "v2\n");
  b.touchStamp(60);
  const r = await b.report();
  expect(r.mise[0]).toMatch(/^mise-dotfiles: blocked.*unsaved paths=~\/\.dot-a/);
  expect(r.mise[0]).not.toContain("scheduled");
}, 90_000);

test("mise: fetch-only is blocked fetch-only and never syncs", async () => {
  const b = miseBox({ mode: "fetch-only" });
  b.mise("dot", "save");
  const r = await b.report();
  expect(r.mise[0]).toMatch(/^mise-dotfiles: blocked.*fetch-only/);
  expect(r.argv).not.toContain("dot sync");
  neverMutates(r.argv);
}, 90_000);

test("mise: offline origin is blocked offline", async () => {
  const b = miseBox({ origin: "dead" });
  b.mise("dot", "save");
  expect((await b.report()).mise[0]).toMatch(/^mise-dotfiles: blocked.*offline/);
}, 90_000);

test(
  "mise: origin differing from the declared canonical, or no declaration, is blocked destination-changed",
  async () => {
    const b = miseBox({ declare: "/nowhere/else.git" });
    b.mise("dot", "save");
    expect((await b.report()).mise[0]).toMatch(/^mise-dotfiles: blocked.*destination-changed/);
    b.declare(false);
    expect((await b.report()).mise[0]).toMatch(/^mise-dotfiles: blocked.*destination-changed/);
  },
  90_000,
);

test(
  "mise: a path edited on both sides is blocked conflict with per-path commands; both sides stay recoverable",
  async () => {
    const a = miseBox();
    expect(a.mise("dot", "save").status).toBe(0);
    expect(a.mise("dot", "sync").status).toBe(0);
    const savedA = { ...process.env };
    const bBox = miseBox();
    fs.rmSync(bBox.origin, { recursive: true });
    fs.cpSync(a.origin, bBox.origin, { recursive: true });
    const adopt = bBox.mise("bootstrap", "--adopt", a.origin, "--replace-history", "--yes");
    expect(adopt.status).toBe(0);
    fs.writeFileSync(path.join(bBox.home, ".dot-a"), "v2-B\n");
    bBox.mise("dot", "save");
    expect(bBox.mise("dot", "sync").status).toBe(0);
    fs.cpSync(bBox.origin, a.origin, { recursive: true, force: true });
    process.env = savedA;
    fs.writeFileSync(path.join(a.home, ".dot-a"), "v3-A\n");
    a.mise("dot", "save");
    a.mise("dot", "sync");
    const r = await a.report();
    expect(r.mise[0]).toMatch(/^mise-dotfiles: blocked.*conflict paths=~\/\.dot-a/);
    expect(r.mise[0]).toContain("mise dot conflicts ~/.dot-a");
    expect(r.mise[0]).toContain("mise dot pull --take-remote ~/.dot-a");
    expect(r.mise[0]).toContain("mise dot pull --keep-local ~/.dot-a");
    neverMutates(r.argv);
    expect(fs.readFileSync(path.join(a.home, ".dot-a"), "utf8")).toBe("v3-A\n");
    expect(a.mise("dot", "pull", "--take-remote", "~/.dot-a").status).toBe(0);
    expect(fs.readFileSync(path.join(a.home, ".dot-a"), "utf8")).toBe("v2-B\n");
    expect(a.mise("dot", "undo", "-y").status).toBe(0);
    expect(fs.readFileSync(path.join(a.home, ".dot-a"), "utf8")).toBe("v3-A\n");
  },
  180_000,
);

test("mise: absent from PATH omits the outcome entirely", async () => {
  const b = miseBox();
  process.env.PATH = "/nonexistent";
  const notices: string[] = [];
  const handlers = new Map<string, Function>();
  install({ on: (n, fn) => void handlers.set(n, fn) });
  await handlers.get("agent_end")!({}, { cwd: b.home, ui: { notify: (t: string) => void notices.push(t) } });
  expect(notices.filter(n => n.startsWith("mise-dotfiles:"))).toEqual([]);
});
