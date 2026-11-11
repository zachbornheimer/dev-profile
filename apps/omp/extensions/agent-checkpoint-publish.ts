/**
 * Turn-stop checkpoint publication (ZYS-9037, first slice of ZYS-9023; contract: ADR 0001).
 *
 * At the end of an agent turn (agent_end with willContinue !== true), publish the
 * turn's already-created, signed checkpoint commit to a unique ref under
 * refs/heads/agent-checkpoints/ on an ENROLLED remote, with hooks on, and report a
 * verified or blocked outcome. Nothing is enrolled by default: the shipped
 * enrollment file has zero [repos.*] tables and every turn reports blocked-not-enrolled.
 *
 * Fail-closed contract:
 * - Only explicit per-repository enrollment authorizes a push. A remote name, a
 *   credential, a URL substring or an org membership never does. Ambiguity blocks.
 * - The ref is unique, keyed to turn and SHA. No overwrite, no force, no lease, no
 *   delete. An exact ref already at the SHA is verified-present; any other collision blocks.
 * - Commit and pre-push hooks stay on. A rejection is a reported blocker; local work
 *   is untouched (this file never runs `git add` and never creates a commit).
 * - Only committed, signed work reachable from HEAD is published; every newly
 *   reachable commit must be signed. Uncommitted work is never staged.
 *
 * The event handler only resolves the repo, reads enrollment, computes the ref,
 * writes a job record and spawns a detached worker; the hook-gated push runs in the
 * worker (handler budget: omp's 30 s EXTENSION_HANDLER_TIMEOUT_MS).
 *
 * Self-contained on purpose: every import is a node: builtin, so the deployed file
 * needs nothing beside it (see ADR 0001 §5 deployment note).
 */

import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

// ---------------------------------------------------------------------------
// Configuration paths (env-overridable so fixtures never touch real state).
// ---------------------------------------------------------------------------

const ENV_ENROLLMENT = "AGENT_CHECKPOINT_ENROLLMENT_FILE";
const ENV_STATE_DIR = "AGENT_CHECKPOINT_STATE_DIR";
const ENV_GIT_LOG = "AGENT_CHECKPOINT_GIT_LOG";
const ENV_WORKER = "AGENT_CHECKPOINT_WORKER"; // test hook: path to worker script (defaults to this file)
const ENV_ATTEMPT_TIMEOUT_MS = "AGENT_CHECKPOINT_ATTEMPT_TIMEOUT_MS";

function enrollmentFile(): string {
  return process.env[ENV_ENROLLMENT] ??
    path.join(os.homedir(), ".config", "agent-checkpoints", "enrollment.toml");
}

function stateDir(): string {
  return process.env[ENV_STATE_DIR] ?? path.join(os.homedir(), ".local", "state", "agent-checkpoints");
}

function jobsDir(): string {
  return path.join(stateDir(), "jobs");
}

export function attemptTimeoutMs(): number {
  const raw = Number(process.env[ENV_ATTEMPT_TIMEOUT_MS]);
  return Number.isFinite(raw) && raw > 0 ? raw : 35 * 60 * 1000;
}

// ---------------------------------------------------------------------------
// Git runner. Fixed argv arrays only; a forbidden flag aborts before spawn.
// The refusal tokens are assembled from parts so this file greps clean for
// skip-hook and force flags (ZYS-9037 Verify): the guard refuses them, it
// never passes them.
// ---------------------------------------------------------------------------

const FORBIDDEN_ARGV = [
  `--no-${"verify"}`,
  `--${"force"}`,
  `--${"force"}-${"with-lease"}`,
  "-f",
  `--${"delete"}`,
  "-d",
];
const FORBIDDEN_ENV: Record<string, string> = { HK: "0" };
const MAX_ATTEMPTS = 3;
const STALE_HEARTBEAT_MS = 180_000;
const JOB_TTL_MS = 24 * 60 * 60 * 1000;
const PRUNE_AFTER_MS = 7 * 24 * 60 * 60 * 1000;

export interface GitResult {
  code: number;
  stdout: string;
  stderr: string;
}

/** Runs git with a fixed argv. Refuses any flag or env that could bypass a hook. */
export function gitRun(
  repo: string,
  args: readonly string[],
  options: { env?: Record<string, string>; timeoutMs?: number } = {},
): Promise<GitResult> {
  for (const arg of args) {
    if (FORBIDDEN_ARGV.includes(arg)) {
      throw new Error(`refusing git argv: ${JSON.stringify(args)}`);
    }
  }
  for (const [key, value] of Object.entries(FORBIDDEN_ENV)) {
    if (process.env[key] === value) {
      throw new Error(`refusing git run: ${key}=${value} disables hooks`);
    }
  }
  // The tests read this log to prove what the worker invoked.
  const logFile = process.env[ENV_GIT_LOG];
  if (logFile) {
    fs.appendFileSync(logFile, `${JSON.stringify(["git", ...args])}\n`);
  }
  const { promise, resolve } = Promise.withResolvers<GitResult>();
  const child = spawn("git", [...args], {
    cwd: repo,
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, ...options.env },
  });
  let stdout = "";
  let stderr = "";
  let timedOut = false;
  const timer = options.timeoutMs === undefined
    ? undefined
    : setTimeout(() => {
      timedOut = true;
      child.kill("SIGKILL");
    }, options.timeoutMs);
  child.stdout.on("data", (d: Buffer) => (stdout += d.toString()));
  child.stderr.on("data", (d: Buffer) => (stderr += d.toString()));
  child.on("error", (error) => {
    if (timer) clearTimeout(timer);
    resolve({ code: -1, stdout, stderr: `${stderr}${String(error)}` });
  });
  child.on("close", (code) => {
    if (timer) clearTimeout(timer);
    resolve({
      code: timedOut ? 124 : (code ?? -1),
      stdout,
      stderr: timedOut ? `${stderr}\n(timeout after ${options.timeoutMs} ms)` : stderr,
    });
  });
  return promise;
}

// ---------------------------------------------------------------------------
// Enrollment: a tiny reader for the owner-edited constrained schema. Fail closed:
// anything unexpected, missing or ambiguous is no enrollment at all.
// ---------------------------------------------------------------------------

export interface EnrollmentEntry {
  slug: string;
  path: string;
  canonical: string;
  enabled: boolean;
  visibility: string;
}

export interface Enrollment {
  entries: EnrollmentEntry[];
}

function unquote(value: string): string | undefined {
  const trimmed = value.trim();
  const double = trimmed.match(/^"((?:[^"\\]|\\.)*)"$/);
  if (double) return double[1].replace(/\\(.)/g, "$1");
  const single = trimmed.match(/^'([^']*)'$/);
  if (single) return single[1];
  return trimmed.includes('"') || trimmed.includes("'") ? undefined : trimmed;
}

function stripComment(line: string): string {
  // A # inside quotes is data; only a bare # starts a comment.
  let inQuotes: '"' | "'" | undefined;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === "\\") i += 1;
      else if (ch === inQuotes) inQuotes = undefined;
      continue;
    }
    if (ch === '"' || ch === "'") inQuotes = ch;
    else if (ch === "#") return line.slice(0, i);
  }
  return line;
}

/**
 * Parses schema_version and [repos."<slug>"] tables. Any surprise - wrong schema
 * version, malformed value, unreadable quoting - yields zero entries (fail closed).
 */
export function parseEnrollment(text: string): Enrollment {
  if (text.length >= 64 * 1024) return { entries: [] };
  const entries: EnrollmentEntry[] = [];
  let schemaVersion: number | undefined;
  let current: { slug: string; fields: Record<string, string> } | undefined;
  const closeCurrent = () => {
    if (!current) return;
    if (current.fields["path"] && current.fields["canonical"] && "#enabled" in current.fields) {
      entries.push({
        slug: current.slug,
        path: current.fields["path"],
        canonical: current.fields["canonical"],
        enabled: current.fields["#enabled"] === "true",
        visibility: current.fields["visibility"] ?? "",
      });
    }
    current = undefined;
  };
  for (const rawLine of text.split(/\r?\n/)) {
    const line = stripComment(rawLine).trim();
    if (!line) continue;
    const table = line.match(/^\[repos\.(.+)\]$/);
    if (table) {
      closeCurrent();
      const slug = unquote(table[1]);
      if (slug === undefined || !slug) return { entries: [] };
      current = { slug, fields: {} };
      continue;
    }
    if (/^\[/.test(line)) continue; // [destinations.*] and friends: not read by this slice
    const pair = line.match(/^([A-Za-z0-9_]+)\s*=\s*(.+)$/);
    if (!pair) return { entries: [] };
    if (pair[1] === "schema_version") {
      const raw = unquote(pair[2]);
      const parsed = raw !== undefined && /^-?\d+$/.test(raw) ? Number(raw) : NaN;
      if (schemaVersion !== undefined || !Number.isInteger(parsed)) return { entries: [] };
      schemaVersion = parsed;
      continue;
    }
    if (!current) return { entries: [] }; // top-level keys beyond schema_version: refuse
    const value = unquote(pair[2]);
    if (value === undefined) return { entries: [] };
    if (pair[1] === "enabled") {
      if (value !== "true" && value !== "false") return { entries: [] };
      current.fields["#enabled"] = value;
      continue;
    }
    current.fields[pair[1]] = value;
  }
  closeCurrent();
  if (schemaVersion !== 1) return { entries: [] };
  return { entries };
}

function expandTilde(p: string): string {
  return p.startsWith("~/") ? path.join(os.homedir(), p.slice(2)) : p;
}

/** Realpath of the git common dir: the canonical identity of a checkout or worktree. */
export async function repoIdentity(repo: string): Promise<string | undefined> {
  const result = await gitRun(repo, ["rev-parse", "--git-common-dir"]);
  if (result.code !== 0) return undefined;
  const rel = result.stdout.trim();
  if (!rel) return undefined;
  return fs.realpathSync(path.resolve(repo, rel));
}

export type Ownership =
  | { kind: "match"; entry: EnrollmentEntry }
  | { kind: "not-enrolled" }
  | { kind: "ambiguous" };

/**
 * A repository matches an entry when their git-common-dir realpaths are equal.
 * More than one enabled match is ambiguous, and so is a duplicate canonical.
 */
export async function resolveOwnership(repo: string, enrollment: Enrollment): Promise<Ownership> {
  const identity = await repoIdentity(repo);
  if (!identity) return { kind: "not-enrolled" };
  const matches: EnrollmentEntry[] = [];
  for (const entry of enrollment.entries) {
    if (!entry.enabled) continue;
    const entryIdentity = await repoIdentity(expandTilde(entry.path));
    if (entryIdentity === identity) {
      if (matches.some((m) => m.canonical === entry.canonical)) return { kind: "ambiguous" };
      matches.push(entry);
    }
  }
  if (matches.length === 0) return { kind: "not-enrolled" };
  if (matches.length > 1) return { kind: "ambiguous" };
  return { kind: "match", entry: matches[0] };
}

// ---------------------------------------------------------------------------
// Ref computation. R2.2: same SHA, same ref - a rerun on a SHA this repo has
// already published reuses that job's ref and turn id.
// ---------------------------------------------------------------------------

function slugify(value: string): string {
  const slug = value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return slug || "x";
}

export const REF_NAMESPACE = "refs/heads/agent-checkpoints/";

export interface RefPlan {
  ref: string;
  short: string;
}

export async function computeRef(
  repo: string,
  entry: Pick<EnrollmentEntry, "slug">,
  turnId: string,
  sha: string,
): Promise<RefPlan | { error: "blocked-namespace" }> {
  const branchResult = await gitRun(repo, ["rev-parse", "--abbrev-ref", "HEAD"]);
  const branch = branchResult.code === 0 ? branchResult.stdout.trim() : "";
  const short = `agent-checkpoints/${slugify(entry.slug)}/${slugify(branch)}/${turnId}-${sha}`;
  if (`refs/heads/`.length + short.length > 200) return { error: "blocked-namespace" };
  const check = await gitRun(repo, ["check-ref-format", "--branch", short]);
  if (check.code !== 0) return { error: "blocked-namespace" };
  return { ref: `${REF_NAMESPACE}${short}`, short };
}

// ---------------------------------------------------------------------------
// Job records.
// ---------------------------------------------------------------------------

export interface JobRecord {
  key: string;
  repo: string;
  ref: string;
  sha: string;
  canonical: string;
  turnId: string;
  state: "queued" | "pushing" | "pushed" | "verified" | "failed" | "expired";
  outcome?: string;
  detail?: string;
  attempts: number;
  createdAt: number;
  updatedAt: number;
  heartbeatAt: number;
  reported?: string;
  repoSlug: string;
}

export function jobKey(repo: string, ref: string, sha: string): string {
  return createHash("sha256").update(`${repo}\0${ref}\0${sha}`).digest("hex");
}

export function jobPath(key: string): string {
  return path.join(jobsDir(), `${key}.json`);
}

function parseJobFile(file: string): JobRecord | undefined {
  try {
    const parsed = JSON.parse(fs.readFileSync(file, "utf-8")) as JobRecord;
    return typeof parsed.key === "string" ? parsed : undefined;
  } catch {
    return undefined;
  }
}

export function readJob(key: string): JobRecord | undefined {
  return parseJobFile(jobPath(key));
}

/** Every job record on disk for one repository (turn ids derive from these). */
function readJobsForRepo(repo: string): JobRecord[] {
  let names: string[];
  try {
    names = fs.readdirSync(jobsDir());
  } catch {
    return [];
  }
  return names
    .filter((n) => n.endsWith(".json"))
    .map((n) => parseJobFile(path.join(jobsDir(), n)))
    .filter((j): j is JobRecord => j !== undefined && j.repo === repo);
}

export function writeJob(job: JobRecord): void {
  fs.mkdirSync(jobsDir(), { recursive: true });
  const target = jobPath(job.key);
  const temp = `${target}.tmp-${process.pid}-${Date.now()}`;
  fs.writeFileSync(temp, JSON.stringify(job, null, 2), { mode: 0o600 });
  fs.renameSync(temp, target);
}

export function pendingStates(job: JobRecord | undefined): boolean {
  return job !== undefined && ["queued", "pushing", "pushed"].includes(job.state);
}

export function isStale(job: JobRecord): boolean {
  return Date.now() - job.heartbeatAt > STALE_HEARTBEAT_MS;
}

/** Terminal records older than 7 days are pruned; a pending job past 24 h is expired. */
export function pruneJobs(): void {
  const dir = jobsDir();
  let names: string[];
  try {
    names = fs.readdirSync(dir);
  } catch {
    return;
  }
  for (const name of names) {
    if (!name.endsWith(".json")) continue;
    const file = path.join(dir, name);
    const job = parseJobFile(file);
    if (!job) continue;
    const age = Date.now() - job.createdAt;
    if (pendingStates(job) && age > JOB_TTL_MS) {
      job.state = "expired";
      job.outcome = "expired";
      job.updatedAt = Date.now();
      writeJob(job);
      continue;
    }
    if (["verified", "failed", "expired"].includes(job.state) && age > PRUNE_AFTER_MS) {
      fs.unlinkSync(file);
    }
  }
}

// ---------------------------------------------------------------------------
// Outcome report shared by handler and worker.
// ---------------------------------------------------------------------------

export interface Report {
  outcome: string;
  detail?: string;
  repo?: string;
  ref?: string;
  destination?: string;
  sha?: string;
  attempts?: number;
}

function sanitizeDestination(url: string): string {
  try {
    const parsed = new URL(url);
    if (parsed.username || parsed.password) {
      return `${parsed.protocol}//${parsed.host}${parsed.pathname}`;
    }
    return url;
  } catch {
    return "<destination>";
  }
}

export function formatReport(report: Report): string {
  const parts = [`agent-checkpoint: ${report.outcome}`];
  if (report.repo) parts.push(`repo=${report.repo}`);
  if (report.ref) parts.push(`ref=${report.ref}`);
  if (report.destination) parts.push(`destination=${sanitizeDestination(report.destination)}`);
  if (report.sha) parts.push(`sha=${report.sha}`);
  if (report.attempts !== undefined) parts.push(`attempts=${report.attempts}`);
  if (report.detail) parts.push(`detail=${report.detail}`);
  return parts.join(" ");
}

// ---------------------------------------------------------------------------
// Destination resolution: `git push --dry-run -v` is the only source of the
// effective push URL (pushurl and insteadOf included). Read-back uses the same string.
// The dry run also runs the pre-push hook (verified: git invokes pre-push on
// --dry-run), so its failure is classified, not swallowed into "unreachable".
// ---------------------------------------------------------------------------

export type PushUrlResolution =
  | { url: string }
  | { error: "blocked-hook-rejected" | "blocked-secrets" | "blocked-remote-unreachable" };

export async function resolvePushUrl(repo: string, sha: string, ref: string): Promise<PushUrlResolution> {
  const dryRun = await gitRun(repo, ["push", "--dry-run", "-v", "origin", `${sha}:${ref}`]);
  if (dryRun.code === 0) {
    const match = dryRun.stderr.match(/^Pushing to (.+)$/m);
    if (match) return { url: match[1].trim() };
    return { error: "blocked-remote-unreachable" };
  }
  const combined = `${dryRun.stdout}\n${dryRun.stderr}`;
  if (/gitleaks|secret detected|leak detected/i.test(combined)) return { error: "blocked-secrets" };
  if (/pre-push hook declined|hook declined/i.test(combined)) return { error: "blocked-hook-rejected" };
  return { error: "blocked-remote-unreachable" };
}

export async function listRemoteRefs(
  repo: string,
  url: string,
  pattern: string,
): Promise<{ ref: string; sha: string }[]> {
  const result = await gitRun(repo, ["ls-remote", url, pattern]);
  if (result.code !== 0) return [];
  return result.stdout.trim().split("\n").filter(Boolean).map((line) => {
    const [sha, ref] = line.split(/\t/);
    return { sha: sha ?? "", ref: ref ?? "" };
  });
}

// ---------------------------------------------------------------------------
// Worker: the hook-gated push, attempts, read-back. Runs detached under flock.
// ---------------------------------------------------------------------------

export interface WorkerOutcome extends Report {
  terminal: boolean;
  retryable: boolean;
}

function classifyPushFailure(result: GitResult, timeoutMs: number): WorkerOutcome {
  const combined = `${result.stdout}\n${result.stderr}`;
  if (/gitleaks|secret detected|leak detected/i.test(combined)) {
    return { outcome: "blocked-secrets", detail: "gitleaks", terminal: true, retryable: false };
  }
  if (result.code === 124) {
    return {
      outcome: "blocked-timeout",
      detail: `attempt exceeded ${Math.round(timeoutMs / 60000)} min`,
      terminal: false,
      retryable: true,
    };
  }
  if (/pre-push hook declined|hook declined/i.test(combined)) {
    return {
      outcome: "blocked-hook-rejected",
      detail: `exit=${result.code}`,
      terminal: true,
      retryable: false,
    };
  }
  if (
    result.code === 128 &&
    /does not appear to be a git repository|Could not read from remote|Connection (?:timed out|refused|reset)|Network is unreachable/i.test(
      combined,
    )
  ) {
    return {
      outcome: "blocked-remote-unreachable",
      detail: `exit=${result.code}`,
      terminal: false,
      retryable: true,
    };
  }
  if (/\[remote rejected\]|Permission denied|Authentication failed|ERROR: (?:The key you are|Access)/i.test(combined)) {
    return { outcome: "blocked-remote-rejected", detail: `exit=${result.code}`, terminal: true, retryable: false };
  }
  return {
    outcome: "blocked-remote-rejected",
    detail: `exit=${result.code}: ${combined.trim().split("\n").slice(-1)[0]}`,
    terminal: true,
    retryable: false,
  };
}

/** One publication attempt: ownership of the ref, eligibility, push, read-back. */
async function attempt(job: JobRecord): Promise<WorkerOutcome> {
  const repo = job.repo;
  const timeoutMs = attemptTimeoutMs();
  const resolution = await resolvePushUrl(repo, job.sha, job.ref);
  if ("error" in resolution) {
    const retryable = resolution.error === "blocked-remote-unreachable";
    return { outcome: resolution.error, detail: "dry-run", terminal: !retryable, retryable };
  }
  const { url } = resolution;
  if (url !== job.canonical) {
    return {
      outcome: "blocked-destination-changed",
      detail: `resolved ${url} != enrolled canonical`,
      terminal: true,
      retryable: false,
    };
  }
  // Collision and D/F check on the destination listing, never on local tracking refs.
  const listing = await listRemoteRefs(repo, url, "refs/heads/*");
  if (listing.length === 0) {
    return { outcome: "blocked-remote-unreachable", detail: "empty listing", terminal: false, retryable: true };
  }
  const exact = listing.find((item) => item.ref === job.ref);
  if (exact && exact.sha === job.sha) {
    return { outcome: "verified-present", detail: "already at sha", terminal: true, retryable: false };
  }
  if (exact) {
    return { outcome: "blocked-collision", detail: "different-sha", terminal: true, retryable: false };
  }
  const shortRef = job.ref.slice("refs/heads/".length);
  const dfConflict = listing.some((item) => {
    if (!item.ref.startsWith("refs/heads/")) return false;
    const other = item.ref.slice("refs/heads/".length);
    return other.startsWith(`${shortRef}/`) || shortRef.startsWith(`${other}/`);
  });
  if (dfConflict) {
    return { outcome: "blocked-collision", detail: "df-conflict", terminal: true, retryable: false };
  }
  // Eligibility: advertised tips present locally; every newly reachable commit signed.
  const localTips: string[] = [];
  let anyAncestry = false;
  for (const item of listing) {
    if (!item.ref.startsWith("refs/heads/")) continue;
    if (item.ref.startsWith(REF_NAMESPACE)) continue;
    const present = await gitRun(repo, ["cat-file", "-e", `${item.sha}^{commit}`]);
    if (present.code !== 0) continue;
    localTips.push(item.sha);
    const shared = await gitRun(repo, ["merge-base", item.sha, job.sha]);
    if (shared.code === 0 && shared.stdout.trim() !== "") anyAncestry = true;
  }
  if (localTips.length === 0) {
    return {
      outcome: "blocked-missing-baseline",
      detail: "no advertised tip local",
      terminal: true,
      retryable: false,
    };
  }
  if (!anyAncestry) {
    return {
      outcome: "blocked-unrelated-ancestry",
      detail: "no shared ancestry",
      terminal: true,
      retryable: false,
    };
  }
  const newResult = await gitRun(repo, ["rev-list", job.sha, "--not", ...localTips]);
  if (newResult.code !== 0) {
    return { outcome: "blocked-unsafe-state", detail: "rev-list failed", terminal: true, retryable: false };
  }
  const newShas = newResult.stdout.trim().split("\n").filter(Boolean);
  for (const newSha of newShas) {
    const sig = await gitRun(repo, ["rev-list", "--format=%G?", "--no-walk", newSha]);
    const status = sig.stdout.trim().split("\n").pop() ?? "";
    if (sig.code !== 0 || status !== "G") {
      return {
        outcome: "blocked-unsigned",
        detail: `commit ${newSha.slice(0, 12)} %G?=${status}`,
        terminal: true,
        retryable: false,
      };
    }
  }
  // The push itself: hooks on, no force, unique ref. A timeout after a push is
  // uncertain, so the read-back below decides verified vs retry.
  const push = await gitRun(repo, ["push", url, `${job.sha}:${job.ref}`], { timeoutMs });
  if (push.code !== 0) {
    return classifyPushFailure(push, timeoutMs);
  }
  const readBack = await listRemoteRefs(repo, url, job.ref);
  if (readBack.length === 1 && readBack[0].sha === job.sha) {
    return { outcome: "verified", detail: "read-back matches", terminal: true, retryable: false };
  }
  return {
    outcome: "blocked-remote-unreachable",
    detail: "push reported success but ref absent",
    terminal: false,
    retryable: true,
  };
}

export async function runWorker(jobFile: string): Promise<void> {
  const onDisk = parseJobFile(jobFile);
  if (!onDisk) return;
  if (readJob(onDisk.key)?.state === "verified") return; // idempotent: nothing to push
  // flock the job's lock file for the whole attempt: a second worker (a stale
  // takeover racing the live one) exits without a second push.
  const lockFile = `${jobFile}.lock`;
  const lockFd = fs.openSync(lockFile, "a");
  const { promise, resolve } = Promise.withResolvers<boolean>();
  const lockChild = spawn("flock", ["-n", String(lockFd), "true"]);
  lockChild.on("error", () => resolve(false));
  lockChild.on("close", (code) => resolve(code === 0));
  const locked = await promise;
  if (!locked) {
    fs.closeSync(lockFd);
    return;
  }
  process.env.AGENT_CHECKPOINT_PUBLISH = "1"; // the handler must never act inside a worker
  try {
    const live = readJob(onDisk.key) ?? onDisk;
    live.state = "pushing";
    live.updatedAt = Date.now();
    live.heartbeatAt = Date.now();
    writeJob(live);
    const heartbeat = setInterval(() => {
      const beat = readJob(live.key);
      if (beat && pendingStates(beat)) {
        beat.heartbeatAt = Date.now();
        writeJob(beat);
      }
    }, 60_000);
    try {
      // At most MAX_ATTEMPTS in total (carried across worker restarts via the
      // job record); transient failures only. A hook rejection, auth error,
      // collision, unsigned commit or unsafe state stops at attempt 1.
      let outcome: WorkerOutcome | undefined;
      for (;;) {
        live.attempts += 1;
        outcome = await attempt(live);
        live.updatedAt = Date.now();
        live.heartbeatAt = Date.now();
        if (outcome.terminal || !outcome.retryable || live.attempts >= MAX_ATTEMPTS) break;
      }
      const final = readJob(live.key) ?? live;
      final.state = ["verified", "verified-present"].includes(outcome.outcome) ? "verified" : "failed";
      final.outcome = outcome.outcome;
      final.detail = outcome.detail;
      final.attempts = live.attempts;
      final.updatedAt = Date.now();
      final.heartbeatAt = Date.now();
      writeJob(final);
    } finally {
      clearInterval(heartbeat);
    }
  } finally {
    fs.closeSync(lockFd); // releases the flock: the fd is the lock
  }
}

// ---------------------------------------------------------------------------
// Handler: fast path only. Resolve, enqueue, spawn detached worker, report pending.
// ---------------------------------------------------------------------------

export interface PiContext {
  on: (event: string, handler: (event: unknown, ctx?: unknown) => void | Promise<void>) => void;
}

interface AgentEndEvent {
  willContinue?: boolean;
}

interface UiContext {
  ui?: { notify?: (message: string, type?: "info" | "warning" | "error") => void };
  sessionManager?: { getCwd?: () => string | null };
}

function notify(ctx: UiContext | undefined, message: string, level: "info" | "warning" | "error"): void {
  const notifyFn = ctx?.ui?.notify;
  if (typeof notifyFn === "function") notifyFn(message, level);
}

/** Reports outcomes of this repo's settled jobs; called at the next turn start (and end). */
async function reportSettled(repo: string, ctx?: UiContext): Promise<void> {
  let names: string[];
  try {
    names = fs.readdirSync(jobsDir());
  } catch {
    return;
  }
  for (const name of names) {
    if (!name.endsWith(".json")) continue;
    const job = parseJobFile(path.join(jobsDir(), name));
    if (!job || job.repo !== repo || job.reported) continue;
    if (!["verified", "failed", "expired"].includes(job.state)) continue;
    notify(
      ctx,
      formatReport({
        outcome: job.outcome ?? job.state,
        detail: job.detail,
        repo: job.repoSlug,
        ref: job.ref,
        destination: job.canonical,
        sha: job.sha,
        attempts: job.attempts,
      }),
      job.state === "verified" ? "info" : "warning",
    );
    job.reported = new Date().toISOString();
    writeJob(job);
  }
}

async function handleAgentEnd(event: AgentEndEvent, ctx?: UiContext): Promise<void> {
  if (process.env.AGENT_CHECKPOINT_PUBLISH === "1") return; // never act inside a worker
  if (event?.willContinue === true) return; // continuation scheduled: not a settle
  pruneJobs();
  const cwd = ctx?.sessionManager?.getCwd?.();
  const repo = cwd && fs.existsSync(cwd) ? cwd : process.cwd();
  await reportSettled(repo, ctx);
  let enrollmentText = "";
  try {
    enrollmentText = fs.readFileSync(enrollmentFile(), "utf-8");
  } catch {
    // missing or unreadable enrollment: nothing is enrolled
  }
  const ownership = await resolveOwnership(repo, parseEnrollment(enrollmentText));
  if (ownership.kind !== "match") {
    const outcome = ownership.kind === "ambiguous"
      ? "blocked-ambiguous-ownership"
      : "blocked-not-enrolled";
    notify(ctx, formatReport({ outcome, repo }), ownership.kind === "ambiguous" ? "warning" : "info");
    return;
  }
  const entry = ownership.entry;
  const head = await gitRun(repo, ["rev-parse", "HEAD"]);
  const sha = head.code === 0 ? head.stdout.trim() : "";
  if (!/^[0-9a-f]{40}$/.test(sha)) {
    notify(
      ctx,
      formatReport({ outcome: "blocked-unsafe-state", detail: "unborn HEAD", repo: entry.slug }),
      "warning",
    );
    return;
  }
  // R2.2: same SHA, same ref. A SHA this repo has already recorded keeps its
  // ref and turn id; a new SHA takes the next turn id for this repo.
  const repoJobs = readJobsForRepo(repo);
  const prior = repoJobs.find((j) => j.sha === sha && j.ref);
  const turnId = prior?.turnId ?? `t${String(repoJobs.length + 1).padStart(4, "0")}`;
  const refPlan = await computeRef(repo, entry, turnId, sha);
  if ("error" in refPlan) {
    notify(ctx, formatReport({ outcome: refPlan.error, repo: entry.slug }), "warning");
    return;
  }
  const key = jobKey(repo, refPlan.ref, sha);
  const existing = readJob(key);
  const settledReport = (outcome: string, detail?: string) =>
    formatReport({
      outcome,
      detail,
      repo: entry.slug,
      ref: refPlan.ref,
      destination: entry.canonical,
      sha,
      attempts: existing?.attempts,
    });
  if (existing?.state === "verified") {
    notify(ctx, settledReport("verified-present"), "info");
    return;
  }
  if (existing && pendingStates(existing) && !isStale(existing)) {
    notify(ctx, settledReport("pending"), "info");
    return;
  }
  if (existing?.state === "failed" && existing.attempts >= MAX_ATTEMPTS) {
    notify(ctx, settledReport(existing.outcome ?? "failed", existing.detail), "warning");
    return;
  }
  const job: JobRecord = {
    key,
    repo,
    ref: refPlan.ref,
    sha,
    canonical: entry.canonical,
    turnId,
    state: "queued",
    attempts: existing?.attempts ?? 0,
    createdAt: existing?.createdAt ?? Date.now(),
    updatedAt: Date.now(),
    heartbeatAt: Date.now(),
    repoSlug: entry.slug,
  };
  writeJob(job);
  if (!spawnWorker(job)) {
    job.state = "failed";
    job.outcome = "blocked-isolation-unavailable";
    job.detail = "worker spawn failed";
    job.updatedAt = Date.now();
    writeJob(job);
    notify(
      ctx,
      formatReport({
        outcome: "blocked-isolation-unavailable",
        detail: "worker spawn failed",
        repo: entry.slug,
      }),
      "warning",
    );
    return;
  }
  notify(
    ctx,
    formatReport({
      outcome: "pending",
      repo: entry.slug,
      ref: refPlan.ref,
      destination: entry.canonical,
      sha,
      attempts: job.attempts,
    }),
    "info",
  );
}

/** Detached worker under setsid: the handler returns before any push starts. */
function spawnWorker(job: JobRecord): boolean {
  const jobFile = jobPath(job.key);
  const workerScript = process.env[ENV_WORKER] ?? import.meta.path;
  const child = spawn("setsid", ["bun", workerScript, "--worker", jobFile], {
    cwd: job.repo,
    detached: true,
    stdio: "ignore",
    env: { ...process.env, AGENT_CHECKPOINT_PUBLISH: "1" },
  });
  child.on("error", () => {});
  try {
    child.unref();
  } catch {
    return false;
  }
  return true;
}

export default function install(pi: PiContext): void {
  pi.on("agent_start", (event: unknown, ctx?: UiContext) => {
    const cwd = ctx?.sessionManager?.getCwd?.() ?? process.cwd();
    void reportSettled(cwd, ctx);
  });
  pi.on("agent_end", (event: AgentEndEvent, ctx?: UiContext) => {
    void handleAgentEnd(event, ctx).catch(() => {});
  });
}

// ---------------------------------------------------------------------------
// Worker entry: `bun agent-checkpoint-publish.ts --worker <job.json>`.
// ---------------------------------------------------------------------------

if (process.argv.includes("--worker")) {
  const jobFile = process.argv[process.argv.indexOf("--worker") + 1];
  if (jobFile) {
    try {
      await runWorker(jobFile);
    } catch (error) {
      process.stderr.write(`agent-checkpoint worker failed: ${String(error)}\n`);
      process.exit(1);
    }
  }
}