// Native turn-stop checkpoint publisher. No staging, committing, or remote-ref cleanup.
// The same file is the detached worker entrypoint; deployment needs no sibling modules.
import { spawn, spawnSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const namespace = "refs/heads/agent-checkpoints/";
const ttl = 86_400_000;
const stale = 180_000;
const workerFile = fileURLToPath(import.meta.url);
const stateRoot = () =>
  process.env.AGENT_CHECKPOINT_STATE_DIR ?? path.join(os.homedir(), ".local/state/agent-checkpoints");
const enrollmentPath = () =>
  process.env.AGENT_CHECKPOINT_ENROLLMENT_FILE ?? path.join(os.homedir(), ".config/agent-checkpoints/enrollment.toml");
const now = () => Date.now();

type Context = {
  cwd?: string;
  sessionManager?: { getCwd?(): string; getSessionId?(): string };
  ui?: { notify?(text: string, level: string): void };
};
type Entry = { slug: string; path: string; canonical: string; remote: string; visibility: string; namespace: string };
export type Job = {
  key: string;
  repo: string;
  identity: string;
  ref: string;
  sha: string;
  turn: string;
  entry: Entry;
  provenance: string[];
  dirty: boolean;
  createdAt: number;
  heartbeatAt: number;
  attempts: number;
  state: "queued" | "pushing" | "pushed" | "verified" | "failed" | "expired";
  outcome: string;
  detail: string;
  reported?: boolean;
};
type Result = { code: number; text: string; out: string };
class Block extends Error {
  constructor(readonly outcome: string, detail = "") {
    super(detail);
  }
}
const block = (outcome: string, detail = ""): never => {
  throw new Block(outcome, detail);
};
const slug = (s: string) =>
  s.toLowerCase().replace(/[^a-z0-9-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 48) || "detached";
const expand = (s: string) => s.startsWith("~/") ? path.join(os.homedir(), s.slice(2)) : s;
export const jobPath = (key: string) => path.join(stateRoot(), "jobs", `${key}.json`);
export const readJob = (file: string): Job => JSON.parse(fs.readFileSync(file, "utf8"));
export function writeJob(job: Job) {
  const file = jobPath(job.key);
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  const temp = `${file}.${randomUUID()}`;
  fs.writeFileSync(temp, JSON.stringify(job), { mode: 0o600, flag: "wx" });
  fs.renameSync(temp, file);
}
function hooksEnabled() {
  if (
    [process.env.HK, process.env.HUSKY, process.env.LEFTHOOK].includes("0") || process.env.GIT_CONFIG_COUNT
    || process.env.GIT_CONFIG_PARAMETERS
  ) {
    block("blocked-unsafe-state", "hook or config override in environment");
  }
}
function record(argv: string[]) {
  const file = process.env.AGENT_CHECKPOINT_GIT_LOG;
  if (file) fs.appendFileSync(file, JSON.stringify({ argv, HK: process.env.HK }) + "\n");
}
function local(repo: string, args: string[]): string {
  hooksEnabled();
  record(args);
  const result = spawnSync("git", args, { cwd: repo, encoding: "utf8", timeout: 3000 });
  if (result.status !== 0) block("blocked-unsafe-state", result.stderr || "local git failed");
  return result.stdout.trim();
}
async function command(repo: string, exe: "git" | "gitleaks", args: string[]): Promise<Result> {
  hooksEnabled();
  if (exe === "git") record(args);
  const { promise, resolve } = Promise.withResolvers<Result>();
  const options = { cwd: repo, stdio: ["ignore", "pipe", "pipe"] as ["ignore", "pipe", "pipe"], detached: true };
  const child = exe === "git" ? spawn("git", args, options) : spawn("gitleaks", args, options);
  let out = "", err = "", timeout = false;
  const timer = setTimeout(() => {
    timeout = true;
    try {
      if (child.pid) process.kill(-child.pid, "SIGKILL");
    } catch { /* process already exited */ }
  }, Number(process.env.AGENT_CHECKPOINT_ATTEMPT_TIMEOUT_MS) || 35 * 60_000);
  child.stdout.on("data", d => {
    out += d;
  });
  child.stderr.on("data", d => {
    err += d;
  });
  child.once("error", e => {
    clearTimeout(timer);
    resolve({ code: 127, out, text: String(e) });
  });
  child.once("close", code => {
    clearTimeout(timer);
    resolve({ code: timeout ? 124 : code ?? 1, out, text: out + "\n" + err });
  });
  return promise;
}
function identity(repo: string) {
  return fs.realpathSync(local(repo, ["rev-parse", "--path-format=absolute", "--git-common-dir"]));
}
function ownership(repo: string): Entry {
  let config: any;
  try {
    config = Bun.TOML.parse(fs.readFileSync(enrollmentPath(), "utf8"));
  } catch {
    return block("blocked-not-enrolled");
  }
  if (config.schema_version !== 1) block("blocked-not-enrolled");
  const id = identity(repo);
  const entries: Entry[] = [];
  for (const [name, value] of Object.entries(config.repos ?? {})) {
    const e = value as any;
    if (e.enabled !== true || typeof e.path !== "string") continue;
    try {
      if (identity(expand(e.path)) === id) entries.push({ ...e, slug: name, remote: e.remote ?? "origin" });
    } catch { /* unrelated invalid entry never authorizes */ }
  }
  if (!entries.length) block("blocked-not-enrolled");
  if (entries.length !== 1) block("blocked-ambiguous-ownership");
  const e = entries[0];
  if (
    Object.values(config.repos ?? {}).filter((v: any) => v.enabled === true && v.canonical === e.canonical).length !== 1
  ) block("blocked-ambiguous-ownership");
  if (
    typeof e.canonical !== "string" || !["private", "public"].includes(e.visibility) || e.namespace !== namespace
    || !/^[a-zA-Z0-9._-]+$/.test(e.remote)
  ) block("blocked-not-enrolled", "invalid enrollment policy");
  return e;
}
function safeDestination(url: string) {
  return url.replace(/(https?:\/\/)[^/@\s]+@/g, "$1").replace(/[?#].*$/, "");
}
export function report(job: Job) {
  return `agent-checkpoint: ${job.outcome} repo=${job.entry.slug} ref=${job.ref} destination=${
    safeDestination(job.entry.canonical)
  } sha=${job.sha} attempts=${job.attempts} uncommitted=${job.dirty} ${job.detail}`;
}
function failResult(result: Result, hook = false): never {
  const tail = safeDestination(result.text.split("\n").slice(-20).join("\n"));
  if (/gitleaks|secret detected/i.test(result.text)) {
    block("blocked-secrets", `exit=${result.code}; local work intact; ${tail}`);
  }
  if (
    /authentication|permission denied|could not read username|403|401|remote rejected|non-fast-forward/i.test(
      result.text,
    )
  ) block("blocked-remote-rejected", tail);
  if (
    result.code === 124
    || /could not resolve|connection|network|does not appear to be a git repository|could not read from remote|unable to access/i
      .test(result.text)
  ) block("blocked-remote-unreachable", tail);
  block(hook ? "blocked-hook-rejected" : "blocked-remote-rejected", `exit=${result.code}; local work intact; ${tail}`);
}
async function refs(job: Job, url: string) {
  const result = await command(job.repo, "git", ["ls-remote", "--", url]);
  if (result.code) failResult(result);
  return result.out.trim().split("\n").filter(Boolean).map(line => {
    const [sha, ref] = line.split(/\s+/);
    return { sha, ref };
  });
}
function collision(job: Job, listing: { sha: string; ref: string }[]) {
  const exact = listing.find(r => r.ref === job.ref);
  if (exact) {
    if (exact.sha !== job.sha) block("blocked-collision", "different-sha");
    return true;
  }
  if (listing.some(r => r.ref.startsWith(job.ref + "/") || job.ref.startsWith(r.ref + "/"))) {
    block("blocked-collision", "df-conflict");
  }
  return false;
}
async function attempt(job: Job) {
  const entry = ownership(job.repo);
  if (identity(job.repo) !== job.identity || (["slug", "path", "canonical", "remote", "visibility", "namespace"] as const).some(key => entry[key] !== job.entry[key])) {
    block("blocked-destination-changed", "enrollment changed");
  }
  if (!job.ref.startsWith(namespace) || !job.ref.endsWith(job.sha)) block("blocked-namespace");
  local(job.repo, ["check-ref-format", job.ref]);
  const dry = await command(job.repo, "git", ["push", "--dry-run", "-v", entry.remote, `${job.sha}:${job.ref}`]);
  const urls = [...dry.text.matchAll(/^Pushing to (.+)$/gm)].map(m => m[1].trim());
  if (urls.length > 1) block("blocked-ambiguous-ownership", "multiple push destinations");
  if (!urls.length) failResult(dry);
  const url = urls[0];
  if (url !== entry.canonical) block("blocked-destination-changed", "effective push URL differs from enrollment");
  const listing = await refs(job, url);
  if (collision(job, listing)) return "verified-present";
  const tips: string[] = [];
  for (const r of listing) {
    if (!/^[a-f0-9]{40}$/.test(r.sha)) continue;
    try {
      local(job.repo, ["cat-file", "-e", `${r.sha}^{commit}`]);
      tips.push(r.sha);
    } catch { /* advertised object absent locally */ }
  }
  if (!tips.length) block("blocked-missing-baseline");
  let related = false;
  for (const tip of tips) {
    try {
      local(job.repo, ["merge-base", tip, job.sha]);
      related = true;
      break;
    } catch { /* disconnected history */ }
  }
  if (!related) block("blocked-unrelated-ancestry");
  const reachable = local(job.repo, ["rev-list", job.sha, "--not", ...tips]).split("\n").filter(Boolean);
  if (reachable.some(sha => !job.provenance.includes(sha))) {
    block("blocked-provenance", "newly reachable ancestry was not created in this turn");
  }
  for (const sha of new Set([job.sha, ...reachable])) {
    const signature = await command(job.repo, "git", ["verify-commit", sha]);
    if (signature.code) block("blocked-unsigned", `signature verification failed: ${sha}`);
  }
  if (reachable.length) {
    const scan = await command(job.repo, "gitleaks", [
      "git",
      "--no-banner",
      "--redact",
      `--log-opts=${job.sha} --not ${tips.join(" ")}`,
      ".",
    ]);
    if (scan.code === 1) block("blocked-secrets", "secret scan rejected reachable commits");
    if (scan.code) block("blocked-unsafe-state", "secret scanner unavailable or failed");
  }
  if (dry.code) failResult(dry, true);
  job.state = "pushing";
  writeJob(job);
  const push = await command(job.repo, "git", ["push", url, `${job.sha}:${job.ref}`]);
  if (!push.code) {
    job.state = "pushed";
    writeJob(job);
  }
  // A lost push response is uncertain. Always read back before considering a retry.
  const after = await refs(job, url);
  if (collision(job, after)) return "verified";
  if (push.code) failResult(push, true);
  block("blocked-remote-unreachable", "push completed but read-back is absent");
}
async function executeJob(file: string) {
  const job = readJob(file);
  if (["verified", "failed", "expired"].includes(job.state)) return;
  if (now() - job.createdAt >= ttl) {
    job.state = "expired";
    job.outcome = "expired";
    writeJob(job);
    return;
  }
  const heartbeat = setInterval(() => {
    job.heartbeatAt = now();
    writeJob(job);
  }, 60_000);
  try {
    while (job.attempts < 3) {
      job.attempts++;
      job.heartbeatAt = now();
      writeJob(job);
      try {
        job.outcome = await attempt(job);
        job.state = "verified";
        job.detail = "remote read-back matches";
        break;
      } catch (e) {
        job.outcome = e instanceof Block ? e.outcome : "blocked-unsafe-state";
        job.detail = e instanceof Error ? e.message : String(e);
        if (job.outcome !== "blocked-remote-unreachable" || job.attempts >= 3) {
          job.state = "failed";
          break;
        }
      }
    }
    if (job.state !== "verified") job.state = "failed";
    writeJob(job);
  } finally {
    clearInterval(heartbeat);
  }
}
export async function runWorker(file: string) {
  if (process.env.AGENT_CHECKPOINT_PUBLISH === "1") return;
  const bun = Bun.which("bun"), flock = Bun.which("flock");
  if (!bun || !flock) block("blocked-isolation-unavailable");
  const child = spawn("flock", ["-n", "-F", `${file}.lock`, bun, workerFile, "--execute-job", file], {
    stdio: "inherit",
    env: { ...process.env, AGENT_CHECKPOINT_PUBLISH: "1" },
  });
  const { promise, resolve, reject } = Promise.withResolvers<void>();
  child.once("error", reject);
  child.once("exit", code => code === 0 || code === 1 ? resolve() : reject(new Error(`worker exit ${code}`)));
  return promise;
}
function launch(job: Job) {
  const bun = Bun.which("bun"), setsid = Bun.which("setsid");
  if (!bun || !setsid || !Bun.which("flock")) block("blocked-isolation-unavailable");
  const child = spawn("setsid", [bun, workerFile, "--worker", jobPath(job.key)], {
    detached: true,
    stdio: "ignore",
    env: process.env,
  });
  child.once("error", e => {
    job.state = "failed";
    job.outcome = "blocked-isolation-unavailable";
    job.detail = String(e);
    writeJob(job);
  });
  child.unref();
}
function jobs(): Job[] {
  try {
    return fs.readdirSync(path.join(stateRoot(), "jobs")).filter(n => /^[a-f0-9]{64}\.json$/.test(n)).map(n =>
      readJob(jobPath(n.slice(0, -5)))
    );
  } catch {
    return [];
  }
}
export default function install(pi: { on(name: string, handler: (event: any, ctx: Context) => unknown): void }) {
  let start: string | undefined, turn = randomUUID();
  const cwd = (ctx: Context) => ctx.cwd ?? ctx.sessionManager?.getCwd?.() ?? process.cwd();
  const surface = (ctx: Context) => {
    for (const job of jobs().filter(j => j.repo === cwd(ctx) && !j.reported)) {
      if (now() - job.createdAt >= ttl && ["queued", "pushing", "pushed"].includes(job.state)) {
        job.state = "expired";
        job.outcome = "expired";
        writeJob(job);
      }
      if (["verified", "failed", "expired"].includes(job.state)) {
        ctx.ui?.notify?.(report(job), job.state === "verified" ? "info" : "warning");
        job.reported = true;
        writeJob(job);
      } else if (now() - job.heartbeatAt > stale) launch(job);
    }
  };
  pi.on("agent_start", (_event, ctx) => {
    if (process.env.AGENT_CHECKPOINT_PUBLISH === "1") return;
    surface(ctx);
    turn = randomUUID();
    try {
      start = local(cwd(ctx), ["rev-parse", "HEAD"]);
    } catch {
      start = undefined;
    }
  });
  pi.on("agent_end", async (event, ctx) => {
    if (event.willContinue === true || process.env.AGENT_CHECKPOINT_PUBLISH === "1") return;
    const repo = cwd(ctx);
    try {
      const entry = ownership(repo);
      const sha = local(repo, ["rev-parse", "HEAD"]);
      const branch = local(repo, ["symbolic-ref", "--short", "HEAD"]);
      const ref = `${namespace}${slug(entry.slug)}/${slug(branch)}/${turn}-${sha}`;
      local(repo, ["check-ref-format", ref]);
      const id = identity(repo), key = createHash("sha256").update(`${id}\0${ref}\0${sha}`).digest("hex");
      const file = jobPath(key);
      if (fs.existsSync(file)) {
        const existing = readJob(file);
        ctx.ui?.notify?.(report(existing), "info");
        return;
      }
      const provenance = start && start !== sha
        ? local(repo, ["rev-list", sha, `^${start}`]).split("\n").filter(Boolean)
        : [sha];
      const job: Job = {
        key,
        repo,
        identity: id,
        ref,
        sha,
        turn,
        entry,
        provenance,
        dirty: !!local(repo, ["status", "--porcelain"]),
        createdAt: now(),
        heartbeatAt: now(),
        attempts: 0,
        state: "queued",
        outcome: "pending",
        detail: "worker detached",
      };
      writeJob(job);
      launch(job);
      ctx.ui?.notify?.(report(job), "info");
    } catch (e) {
      ctx.ui?.notify?.(
        `agent-checkpoint: ${e instanceof Block ? e.outcome : "blocked-unsafe-state"} ${
          e instanceof Error ? e.message : e
        }`,
        "warning",
      );
    }
  });
}
if (import.meta.main) {
  const [mode, file] = process.argv.slice(2);
  if (mode === "--worker" && file) await runWorker(file);
  else if (mode === "--execute-job" && file && process.env.AGENT_CHECKPOINT_PUBLISH === "1") await executeJob(file);
}
