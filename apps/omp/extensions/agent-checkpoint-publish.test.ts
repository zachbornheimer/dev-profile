import { afterEach, expect, test } from "bun:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import install, { type Job, jobPath, readJob, writeJob } from "./agent-checkpoint-publish.ts";

const source = path.resolve(import.meta.dir, "agent-checkpoint-publish.ts");
const dirs: string[] = [];
let saved = { ...process.env };
afterEach(() => {
  process.env = { ...saved };
  for (const dir of dirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});
function git(repo: string, ...args: string[]) {
  const r = Bun.spawnSync(["git", ...args], { cwd: repo, encoding: "utf8", env: process.env });
  if (r.exitCode) throw new Error(`${args.join(" ")}: ${r.stderr}`);
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
  const gen = Bun.spawnSync(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", key]);
  expect(gen.exitCode).toBe(0);
  fs.writeFileSync(path.join(root, "allowed"), `checkpoint@example.test ${fs.readFileSync(key + ".pub", "utf8")}`);
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
  const proc = Bun.spawn([process.execPath, source, "--worker", jobPath(job.key)], {
    env: process.env,
    stdout: "pipe",
    stderr: "pipe",
  });
  const code = await proc.exited;
  if (code) throw new Error(await new Response(proc.stderr).text());
  return readJob(jobPath(job.key));
}
async function settled() {
  const dir = path.join(process.env.AGENT_CHECKPOINT_STATE_DIR!, "jobs");
  const end = Date.now() + 15_000;
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
