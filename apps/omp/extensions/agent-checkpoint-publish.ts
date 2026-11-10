/**
 * Turn-stop checkpoint publication and mise dotfile reconciliation (ADR 0001).
 *
 * ZYS-9037: on `agent_end` with `willContinue !== true`, publish the session's
 * committed work as a checkpoint ref under `refs/heads/agent-checkpoints/`
 * through a detached, hook-gated worker. Enrollment is per repository and
 * owner-edited only; nothing publishes without an enabled `[repos.*]` entry
 * whose effective push URL equals the declared `canonical`.
 *
 * ZYS-9038: in the same `agent_end` report, report exactly one mise
 * reconciliation outcome - `verified`, `scheduled`, `pending` or `blocked` -
 * computed read-only from `mise dot status --json` plus one `mise dot sync`
 * when verification requires it. The extension never runs `mise dot pull`,
 * `mise dot save`, `mise dot recover` or `mise dot bootstrap`, never touches
 * the watchdog stamp or `~/.local/state/mise/history/`, and never passes
 * `--allow-plaintext-history`.
 *
 * One self-contained file: deployed by a `source =` dotfiles entry in
 * `config/mise.toml`; node builtins only.
 */
import { spawn, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  chmodSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  realpathSync,
  renameSync,
  statSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import os from "node:os";
import path from "node:path";

export const OWNED_REF_PREFIX = "refs/heads/agent-checkpoints/";
export const MAX_REF_BYTES = 200;

/** Hook-disabling environment variables the publisher scrubs (R3.1). */
export const HOOK_DISABLE_ENV = [
  "HUSKY",
  "HUSKY_SKIP_HOOKS",
  "HUSKY_DEBUG",
  "LEFTHOOK",
  "LEFTHOOK_MERGED",
  "SKIP",
  "SKIP_HOOKS",
];

// ---------------------------------------------------------------------------
// Public shapes
// ---------------------------------------------------------------------------

export type RepoOutcome =
  | "verified"
  | "verified-present"
  | "pending"
  | "expired"
  | "failed"
  | "blocked-not-enrolled"
  | "blocked-ambiguous-ownership"
  | "blocked-destination-changed"
  | "blocked-namespace"
  | "blocked-collision"
  | "blocked-missing-baseline"
  | "blocked-unrelated-ancestry"
  | "blocked-provenance"
  | "blocked-unsigned"
  | "blocked-hook-rejected"
  | "blocked-remote-rejected"
  | "blocked-isolation-unavailable"
  | "blocked-timeout"
  | "blocked-remote-unreachable";

export interface RepoReport {
  outcome: RepoOutcome;
  detail?: string;
  ref?: string;
  sha?: string;
  jobKey?: string;
  hookOutput?: string[];
}

export type MiseOutcome = "verified" | "scheduled" | "pending" | "blocked";
export type MiseBlockedReason =
  | "conflict"
  | "failing"
  | "offline"
  | "fetch-only"
  | "unsaved"
  | "manual-save-overdue"
  | "destination-changed";

export interface MiseCondition {
  reason: MiseBlockedReason;
  message: string;
  paths?: string[];
  commands?: string[];
}

export interface MiseReport {
  outcome: MiseOutcome;
  reason?: string;
  detail?: string;
  paths?: string[];
  conditions?: MiseCondition[];
  commands?: string[];
  syncRan: boolean;
  localHead?: string | null;
  remoteHead?: string | null;
}

export interface TurnEndReport {
  schema: 1;
  at: string;
  repository?: RepoReport;
  mise?: MiseReport;
}

// ---------------------------------------------------------------------------
// Injectable environment (tests override; production uses the node defaults)
// ---------------------------------------------------------------------------

export interface RunResult {
  code: number | null;
  stdout: string;
  stderr: string;
  signal: NodeJS.Signals | null;
}

export interface Deps {
  env: Record<string, string | undefined>;
  now(): number;
  spawn(cmd: string, args: string[], opts?: { cwd?: string; timeout?: number }): RunResult;
  spawnDetached(cmd: string, args: string[], env: Record<string, string | undefined>): void;
  which(cmd: string): string | undefined;
  readFile(p: string): string | null;
  writeFile(p: string, content: string): void;
  realpath(p: string): string | null;
  exists(p: string): boolean;
  statMtime(p: string): number | null;
  mkdirs(p: string): void;
}

const defaultDeps: Deps = {
  env: process.env as Record<string, string | undefined>,
  now: () => Date.now(),
  spawn: (cmd, args, opts) => {
    const r = spawnSync(cmd, args, {
      cwd: opts?.cwd,
      env: deps.env,
      timeout: opts?.timeout,
      maxBuffer: 16 * 1024 * 1024,
      encoding: "utf8",
    });
    return {
      code: r.status,
      stdout: r.stdout ?? "",
      stderr: r.stderr ?? "",
      signal: r.signal,
    };
  },
  spawnDetached: (cmd, args, env) => {
    const child = spawn(cmd, args, { detached: true, stdio: "ignore", env: env as NodeJS.ProcessEnv });
    child.unref();
  },
  which: (cmd) => {
    for (const dir of (deps.env.PATH ?? "").split(path.delimiter)) {
      if (!dir) continue;
      const candidate = path.join(dir, cmd);
      if (existsSync(candidate)) return candidate;
    }
    return undefined;
  },
  readFile: (p) => {
    try {
      return readFileSync(p, "utf8");
    } catch {
      return null;
    }
  },
  writeFile: (p, content) => {
    writeFileSync(p, content);
  },
  realpath: (p) => {
    try {
      return realpathSync(p);
    } catch {
      return null;
    }
  },
  exists: (p) => existsSync(p),
  statMtime: (p) => {
    try {
      return statSync(p).mtimeMs;
    } catch {
      return null;
    }
  },
  mkdirs: (p) => mkdirSync(p, { recursive: true }),
};

type PartialDeps = { [K in keyof Deps]?: Deps[K] };
const deps: Deps = { ...defaultDeps };

/** Test seam: override any dependency. Returns the previous values. */
export function __setDepsForTests(overrides: PartialDeps): PartialDeps {
  const previous: PartialDeps = {};
  for (const key of Object.keys(overrides) as (keyof Deps)[]) {
    (previous as Record<string, unknown>)[key] = deps[key];
    (deps as Record<string, unknown>)[key] = overrides[key] as unknown;
  }
  return previous;
}

export function __resetDeps(): void {
  Object.assign(deps, defaultDeps);
}

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

function home(): string {
  return deps.env.HOME ?? os.homedir();
}

/** Resolve a leading `~/` against the current HOME (mise prints tilde paths). */
export function resolveTilde(p: string | undefined): string | null {
  if (!p) return null;
  if (p === "~") return home();
  if (p.startsWith("~/")) return path.join(home(), p.slice(2));
  return p;
}

function gitEnv(): Record<string, string | undefined> {
  const env: Record<string, string | undefined> = { ...deps.env };
  for (const key of HOOK_DISABLE_ENV) delete env[key];
  return env;
}

export function runGit(args: string[], opts?: { cwd?: string; timeout?: number }): RunResult {
  return deps.spawn("git", args, { cwd: opts?.cwd, timeout: opts?.timeout });
}

function writeFileAtomic(p: string, content: string): void {
  deps.mkdirs(path.dirname(p));
  const tmp = `${p}.tmp-${process.pid}-${deps.now()}`;
  deps.writeFile(tmp, content);
  try {
    chmodSync(tmp, 0o600);
  } catch {
    // chmod failures are not fatal for the record
  }
  try {
    renameSync(tmp, p);
  } catch {
    // rename can fail across devices; fall back to a direct write
    deps.writeFile(p, content);
  }
}

// ---------------------------------------------------------------------------
// Enrollment (ADR section 4, strict-subset TOML: the owner edits this file)
// ---------------------------------------------------------------------------

export interface EnrollmentRepo {
  slug: string;
  enabled: boolean;
  path?: string;
  canonical?: string;
  visibility?: string;
  destination?: string;
}

export interface EnrollmentDestination {
  name: string;
  kind?: string;
  canonical?: string;
  branch?: string;
  mode?: string;
}

export interface Enrollment {
  schemaVersion: number;
  repos: EnrollmentRepo[];
  destinations: EnrollmentDestination[];
}

/**
 * Parse the enrollment file. `null` for anything unreadable or with a
 * schema_version other than 1: the publisher reads nothing and reports
 * `blocked-not-enrolled` (ADR section 4).
 */
export function parseEnrollmentTOML(text: string): Enrollment | null {
  const enrollment: Enrollment = { schemaVersion: 0, repos: [], destinations: [] };
  let table: "root" | "repos" | "destinations" = "root";
  let currentName = "";
  for (const rawLine of text.split("\n")) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const tableMatch = line.match(/^\[(repos|destinations)\."([^"]+)"\]$/);
    if (tableMatch) {
      table = tableMatch[1] as "repos" | "destinations";
      currentName = tableMatch[2];
      if (table === "repos") {
        enrollment.repos.push({ slug: currentName, enabled: true });
      } else {
        enrollment.destinations.push({ name: currentName });
      }
      continue;
    }
    if (line.startsWith("[")) continue; // unknown or nested table: ignore keys
    const kv = line.match(/^([A-Za-z0-9_-]+)\s*=\s*(.+)$/);
    if (!kv) return null; // unparseable line: unreadable file
    const key = kv[1];
    const value = parseTomlValue(kv[2]);
    if (value === null) return null;
    if (table === "root") {
      if (key === "schema_version" && typeof value === "number") enrollment.schemaVersion = value;
    } else if (table === "repos") {
      const entry = enrollment.repos[enrollment.repos.length - 1];
      applyEnrollmentKey(entry, key, value);
    } else {
      const entry = enrollment.destinations[enrollment.destinations.length - 1];
      applyEnrollmentKey(entry, key, value);
    }
  }
  if (enrollment.schemaVersion !== 1) return null;
  return enrollment;
}

function applyEnrollmentKey(entry: Record<string, unknown>, key: string, value: string | number | boolean): void {
  switch (key) {
    case "enabled":
      entry.enabled = value === true || value === "true";
      break;
    case "kind":
    case "path":
    case "canonical":
    case "branch":
    case "mode":
    case "visibility":
    case "destination":
      if (typeof value === "string") entry[key] = value;
      break;
    default:
      break; // unknown keys are ignored, not fatal
  }
}

function parseTomlValue(raw: string): string | number | boolean | null {
  const t = raw.trim();
  if (t === "true") return true;
  if (t === "false") return false;
  if (t.startsWith("\"")) {
    const m = t.match(/^"((?:[^"\\]|\\.)*)"/);
    if (!m) return null;
    return m[1].replace(/\\(.)/g, "$1");
  }
  if (/^-?\d+$/.test(t)) return parseInt(t, 10);
  // bare string: a trailing comment must be separated by whitespace
  const bare = t.split(/\s+#/, 1)[0];
  return bare.length > 0 ? bare : null;
}

export function enrollmentPath(): string {
  return deps.env.AGENT_CHECKPOINT_ENROLLMENT ?? path.join(home(), ".config", "agent-checkpoints", "enrollment.toml");
}

function loadEnrollment(): Enrollment | null {
  const text = deps.readFile(enrollmentPath());
  if (text === null) return null;
  return parseEnrollmentTOML(text);
}

// ---------------------------------------------------------------------------
// Ref grammar (ADR section 6)
// ---------------------------------------------------------------------------

export function slugify(part: string): string {
  return part
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, "-")
    .replace(/^-+/, "")
    .replace(/-+$/, "");
}

export function buildCheckpointRef(
  repoSlug: string,
  branchSlug: string,
  turnId: string,
  sha: string,
): { ref: string; short: string } | { error: "blocked-namespace" } {
  if (!/^[a-z0-9-]+$/.test(repoSlug)) return { error: "blocked-namespace" };
  if (!/^[a-z0-9-]+$/.test(branchSlug)) return { error: "blocked-namespace" };
  if (!/^t\d+$/.test(turnId)) return { error: "blocked-namespace" };
  if (!/^[0-9a-f]{40}$/.test(sha)) return { error: "blocked-namespace" };
  const short = `agent-checkpoints/${repoSlug}/${branchSlug}/${turnId}-${sha}`;
  const ref = `${OWNED_REF_PREFIX}${short}`;
  if (ref.length > MAX_REF_BYTES) return { error: "blocked-namespace" };
  return { ref, short };
}

/** R1.2/R2.1 defense in depth: only refs in the owned namespace may be pushed. */
export function refInOwnedNamespace(ref: string): boolean {
  return ref.startsWith(OWNED_REF_PREFIX) && ref.length <= MAX_REF_BYTES;
}

// ---------------------------------------------------------------------------
// Job records (ADR section 8)
// ---------------------------------------------------------------------------

export interface JobRecord {
  key: string;
  repoCommonDir: string;
  repoSlug: string;
  branchSlug: string;
  ref: string;
  sha: string;
  canonical: string;
  provenance: string[];
  provenanceTips: string[];
  turnId: string;
  state: "queued" | "pushing" | "pushed" | "verified" | "failed" | "expired";
  attempts: number;
  outcome?: RepoOutcome;
  detail?: string;
  exitCode?: number | null;
  hookOutput?: string[];
  createdAt: string;
  updatedAt: string;
  heartbeatAt: string;
}

export function stateDir(): string {
  return deps.env.AGENT_CHECKPOINT_STATE_DIR ?? path.join(home(), ".local", "state", "agent-checkpoints");
}

export function jobKey(repoCommonDir: string, ref: string, sha: string): string {
  return createHash("sha256").update(`${repoCommonDir}\0${ref}\0${sha}`).digest("hex");
}

function jobPath(key: string): string {
  return path.join(stateDir(), "jobs", `${key}.json`);
}

export function readJob(key: string): JobRecord | null {
  const text = deps.readFile(jobPath(key));
  if (text === null) return null;
  try {
    return JSON.parse(text) as JobRecord;
  } catch {
    return null;
  }
}

export function writeJob(job: JobRecord): void {
  job.updatedAt = new Date(deps.now()).toISOString();
  writeFileAtomic(jobPath(job.key), `${JSON.stringify(job, null, "\t")}\n`);
}

// ---------------------------------------------------------------------------
// Repository matching (ADR section 3.1)
// ---------------------------------------------------------------------------

/** Resolve the git common dir (realpath) of a checkout or worktree. */
export function gitCommonDirOf(repoDir: string): string | null {
  const r = runGit(["rev-parse", "--git-common-dir"], { cwd: repoDir, timeout: 10000 });
  if (r.code !== 0) return null;
  const printed = r.stdout.trim();
  if (!printed) return null;
  const common = path.isAbsolute(printed) ? printed : path.resolve(repoDir, printed);
  return deps.realpath(common) ?? common;
}

/** Resolve an enrollment `path` to the git common dir it names (checkout, .git, or worktree). */
export function enrollmentPathToCommonDir(entryPath: string): string | null {
  const expanded = resolveTilde(entryPath);
  if (!expanded) return null;
  for (const candidate of [expanded, path.join(expanded, ".git")]) {
    const dir = realpathOrNull(candidate);
    if (dir === null) continue;
    if (!isDirectory(dir)) continue;
    // a worktree's .git is a file; its admin dir holds `commondir`
    const commondirFile = path.join(dir, "commondir");
    if (deps.exists(commondirFile)) {
      const text = deps.readFile(commondirFile);
      if (text) {
        const base = text.trim();
        const resolved = path.isAbsolute(base) ? base : path.resolve(dir, base);
        const real = realpathOrNull(resolved);
        if (real) return real;
      }
    }
    if (deps.exists(path.join(dir, "HEAD")) && deps.exists(path.join(dir, "objects"))) return dir;
  }
  // a worktree whose .git is a gitdir link
  const gitLink = expanded.endsWith(".git") ? null : path.join(expanded, ".git");
  if (gitLink && !isDirectory(gitLink)) {
    const text = deps.readFile(gitLink);
    if (text?.startsWith("gitdir:")) {
      const admin = text.slice("gitdir:".length).trim();
      const adminReal = realpathOrNull(path.isAbsolute(admin) ? admin : path.resolve(expanded, admin));
      if (adminReal) {
        const commondirFile = path.join(adminReal, "commondir");
        if (deps.exists(commondirFile)) {
          const base = deps.readFile(commondirFile)?.trim();
          if (base) {
            const resolved = path.isAbsolute(base) ? base : path.resolve(adminReal, base);
            return realpathOrNull(resolved);
          }
        }
        return adminReal;
      }
    }
  }
  return null;
}

function realpathOrNull(p: string): string | null {
  if (deps.realpath) return deps.realpath(p);
  return p;
}

function isDirectory(p: string): boolean {
  try {
    return statSync(p).isDirectory();
  } catch {
    return false;
  }
}

export type MatchResult =
  | { kind: "entry"; entry: EnrollmentRepo }
  | { kind: "not-enrolled" }
  | { kind: "ambiguous" };

/** R1.1/R1.3: match by repository identity (git common dir), enabled entries only. */
export function matchRepository(enrollment: Enrollment | null, repoCommonDir: string): MatchResult {
  if (!enrollment) return { kind: "not-enrolled" };
  const matches: EnrollmentRepo[] = [];
  for (const entry of enrollment.repos) {
    if (!entry.enabled) continue;
    if (!entry.path) continue;
    const entryCommon = enrollmentPathToCommonDir(entry.path);
    if (entryCommon && entryCommon === repoCommonDir) matches.push(entry);
  }
  if (matches.length === 0) return { kind: "not-enrolled" };
  if (matches.length > 1) return { kind: "ambiguous" };
  return { kind: "entry", entry: matches[0] };
}

// ---------------------------------------------------------------------------
// Repository outcome at turn end (ADR sections 3, 5, 8)
// ---------------------------------------------------------------------------

const NON_TERMINAL: JobRecord["state"][] = ["queued", "pushing", "pushed"];

function toIso(ms: number): string {
  return new Date(ms).toISOString();
}

function turnCounter(repoCommonDir: string): number {
  const jobsDir = path.join(stateDir(), "jobs");
  if (!deps.exists(jobsDir)) return 1;
  let count = 0;
  try {
    const files = readdirSyncSafe(jobsDir);
    for (const file of files) {
      if (!file.endsWith(".json")) continue;
      const text = deps.readFile(path.join(jobsDir, file));
      if (!text) continue;
      try {
        const job = JSON.parse(text) as JobRecord;
        if (job.repoCommonDir === repoCommonDir) count++;
      } catch {
        // a corrupt record does not reset the counter
      }
    }
  } catch {
    // unreadable dir: start at 1
  }
  return count + 1;
}

function readdirSyncSafe(dir: string): string[] {
  return readdirSync(dir);
}

/**
 * Compute the repository part of the turn-end report. Enqueues a job record
 * and launches the detached worker for fresh checkpoints; never pushes here.
 */
export function repositoryReport(repoDir: string, enrollment: Enrollment | null): RepoReport {
  const repoCommonDir = gitCommonDirOf(repoDir);
  if (!repoCommonDir) {
    return { outcome: "pending", detail: "not a git repository" };
  }
  const match = matchRepository(enrollment, repoCommonDir);
  if (match.kind === "not-enrolled") return { outcome: "blocked-not-enrolled" };
  if (match.kind === "ambiguous") return { outcome: "blocked-ambiguous-ownership" };
  const entry = match.entry;
  if (!entry.canonical) return { outcome: "blocked-not-enrolled", detail: "entry has no canonical push URL" };

  const headInfo = runGit(["rev-parse", "HEAD"], { cwd: repoDir, timeout: 10000 });
  if (headInfo.code !== 0 || !/^[0-9a-f]{40}/.test(headInfo.stdout.trim())) {
    return { outcome: "pending", detail: "repository has no commits on HEAD" };
  }
  const sha = headInfo.stdout.trim();
  const branchInfo = runGit(["branch", "--show-current"], { cwd: repoDir, timeout: 10000 });
  const branchSlug = slugify((branchInfo.code === 0 ? branchInfo.stdout.trim() : "") || "head") || "head";
  const turnId = `t${String(turnCounter(repoCommonDir)).padStart(4, "0")}`;
  const built = buildCheckpointRef(entry.slug, branchSlug, turnId, sha);
  if ("error" in built) return { outcome: built.error };
  const key = jobKey(repoCommonDir, built.ref, sha);

  const existing = readJob(key);
  if (existing) {
    if (existing.state === "verified") {
      return { outcome: "verified-present", ref: built.ref, sha, jobKey: key };
    }
    if (existing.state === "failed" || existing.state === "expired") {
      return {
        outcome: existing.state === "failed" ? "failed" : "expired",
        ref: built.ref,
        sha,
        jobKey: key,
        detail: existing.detail,
      };
    }
    // non-terminal: queued, pushing or pushed (R5.1, R5.2)
    const ageMs = deps.now() - Date.parse(existing.createdAt);
    if (ageMs > JOB_TTL_MS) {
      const expiredJob = {
        ...existing,
        state: "expired" as const,
        outcome: "expired" as RepoOutcome,
        detail: "job exceeded its 24 h TTL",
      };
      writeJob(expiredJob);
      return { outcome: "expired", ref: built.ref, sha, jobKey: key };
    }
    return { outcome: "pending", ref: built.ref, sha, jobKey: key, detail: `job ${existing.state}` };
  }

  // provenance recorded at enqueue: commits unique against all local
  // remote-tracking refs, plus those refs' tips (worker re-checks against the
  // advertised tips, allowing commits that were on either tip set).
  const provenanceTips = tipsOfRemotes(repoDir);
  const provenance = revListNot(repoDir, sha, provenanceTips.length ? provenanceTips : []);

  if (!deps.which("setsid") || !deps.which("flock")) {
    return { outcome: "blocked-isolation-unavailable", ref: built.ref, sha, jobKey: key };
  }

  const job: JobRecord = {
    key,
    repoCommonDir,
    repoSlug: entry.slug,
    branchSlug,
    ref: built.ref,
    sha,
    canonical: entry.canonical,
    provenance,
    provenanceTips,
    turnId,
    state: "queued",
    attempts: 0,
    createdAt: toIso(deps.now()),
    updatedAt: toIso(deps.now()),
    heartbeatAt: toIso(deps.now()),
  };
  writeJob(job);
  launchWorker(key);
  return { outcome: "pending", ref: built.ref, sha, jobKey: key, detail: "job queued" };
}

function tipsOfRemotes(repoDir: string): string[] {
  const r = runGit(["for-each-ref", "refs/remotes", "--format=%(objectname)"], { cwd: repoDir, timeout: 10000 });
  if (r.code !== 0) return [];
  return r.stdout
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => /^[0-9a-f]{40}$/.test(line));
}

function revListNot(repoDir: string, sha: string, tips: string[]): string[] {
  const args = ["rev-list", sha, "--not", ...tips];
  const r = runGit(args, { cwd: repoDir, timeout: 30000 });
  if (r.code !== 0) return [];
  return r.stdout
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => /^[0-9a-f]{40}$/.test(line));
}

/** Launch the detached worker: setsid -> flock -> this file in worker mode. */
export function launchWorker(key: string): void {
  const self = selfPath();
  if (!self || !deps.which("setsid") || !deps.which("flock")) return;
  const lock = path.join(stateDir(), "jobs", `${key}.lock`);
  deps.mkdirs(path.dirname(lock));
  const env = { ...gitEnv(), AGENT_CHECKPOINT_PUBLISH: "1" };
  deps.spawnDetached(
    "setsid",
    ["flock", lock, process.execPath, self, "--agent-checkpoint-worker", key],
    env,
  );
}

export function selfPath(): string | null {
  const fromMeta = (import.meta as unknown as { path?: string }).path;
  if (fromMeta) return fromMeta;
  const argv1 = process.argv[1];
  if (argv1 && existsSync(argv1)) return path.resolve(argv1);
  return null;
}

const JOB_TTL_MS = 24 * 60 * 60 * 1000;

// ---------------------------------------------------------------------------
// Worker (ADR sections 7, 8, 9): the slow, hook-gated push
// ---------------------------------------------------------------------------

const HOOK_REJECTION_RE = /pre-push|hook|declined to update|protected branch/i;
const TRANSIENT: RepoOutcome[] = ["blocked-remote-unreachable", "blocked-timeout"];

export function attemptBudgetMs(): number {
  const raw = parseInt(deps.env.AGENT_CHECKPOINT_ATTEMPT_MS ?? "", 10);
  return Number.isFinite(raw) && raw > 0 ? raw : 35 * 60 * 1000;
}

/** Push-destination derivation (ADR 7.1): dry-run -v, same URL for push and read-back. */
export function resolvePushDestination(repoDir: string, canonical: string, timeoutMs: number):
  | { kind: "resolved"; url: string; remote: string }
  | { kind: "hook-rejected"; stderr: string }
  | { kind: "unreachable"; stderr: string }
  | { kind: "timeout" }
  | { kind: "destination-changed" }
{
  const remotes = runGit(["remote"], { cwd: repoDir, timeout: 10000 });
  if (remotes.code !== 0) return { kind: "unreachable", stderr: remotes.stderr };
  const names = remotes.stdout
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const matching: { name: string; url: string }[] = [];
  for (const name of names) {
    const url = runGit(["remote", "get-url", "--push", name], { cwd: repoDir, timeout: 10000 });
    if (url.code === 0 && url.stdout.trim() === canonical) matching.push({ name, url: url.stdout.trim() });
  }
  if (matching.length === 0) return { kind: "destination-changed" };
  const remote = matching[0];
  const dry = runGit(["push", "--dry-run", "-v", remote.name], { cwd: repoDir, timeout: timeoutMs });
  if (dry.code === null && dry.signal) return { kind: "timeout" };
  if (dry.code !== 0) {
    if (HOOK_REJECTION_RE.test(dry.stderr)) return { kind: "hook-rejected", stderr: dry.stderr };
    return { kind: "unreachable", stderr: dry.stderr };
  }
  const urlMatch = dry.stderr.match(/Pushing to (\S+)/);
  if (!urlMatch) return { kind: "destination-changed" };
  if (urlMatch[1] !== canonical) return { kind: "destination-changed" };
  return { kind: "resolved", url: urlMatch[1], remote: remote.name };
}

export interface LsRemoteListing {
  refs: { ref: string; sha: string }[];
  reachable: boolean;
}

export function lsRemote(url: string, refspec: string | null, timeoutMs: number): LsRemoteListing {
  const args = ["ls-remote", url];
  if (refspec) args.push(refspec);
  const r = runGit(args, { timeout: timeoutMs });
  if (r.code !== 0) return { refs: [], reachable: false };
  const refs: { ref: string; sha: string }[] = [];
  for (const line of r.stdout.split("\n")) {
    const m = line.trim().match(/^([0-9a-f]{40})\t(.+)$/);
    if (m) refs.push({ sha: m[1], ref: m[2] });
  }
  return { refs, reachable: true };
}

export function runCheckpointWorker(key: string): RepoOutcome | null {
  const job = readJob(key);
  if (!job) return null;
  if (job.state === "verified" || job.state === "failed" || job.state === "expired") return null;

  const repoDir = job.repoCommonDir;
  const heartbeat = setInterval(() => {
    const current = readJob(key);
    if (current && (current.state === "pushing" || current.state === "pushed")) {
      current.heartbeatAt = toIso(deps.now());
      writeJob(current);
    }
  }, 60_000);
  if (typeof heartbeat.unref === "function") heartbeat.unref();

  const finish = (outcome: RepoOutcome, detail?: string, extra?: Partial<JobRecord>): RepoOutcome => {
    clearInterval(heartbeat);
    const final = readJob(key) ?? job;
    const transient = TRANSIENT.includes(outcome) && final.attempts < 3;
    final.state = transient
      ? "queued"
      : outcome === "verified" || outcome === "verified-present"
      ? "verified"
      : "failed";
    final.outcome = outcome;
    final.detail = detail;
    Object.assign(final, extra ?? {});
    final.heartbeatAt = toIso(deps.now());
    writeJob(final);
    return outcome;
  };

  const setPushing = (): void => {
    const current = readJob(key) ?? job;
    current.state = "pushing";
    current.attempts += 1;
    current.heartbeatAt = toIso(deps.now());
    writeJob(current);
  };

  while (true) {
    const before = readJob(key) ?? job;
    if (before.attempts >= 3) return finish("blocked-timeout", "three attempts exhausted");
    setPushing();
    const startedAt = deps.now();

    const destination = resolvePushDestination(repoDir, job.canonical, attemptBudgetMs());
    if (destination.kind === "destination-changed") return finish("blocked-destination-changed");
    if (destination.kind === "hook-rejected") {
      return finish("blocked-hook-rejected", "the pre-push hook rejected the checkpoint; local work is intact", {
        hookOutput: lastLines(destination.stderr, 20),
      });
    }
    if (destination.kind === "timeout") return finish("blocked-timeout", "push dry-run exceeded the attempt budget");
    if (destination.kind === "unreachable") {
      return finish("blocked-remote-unreachable", lastLines(destination.stderr, 3));
    }
    const url = destination.url;

    if (!refInOwnedNamespace(job.ref)) return finish("blocked-namespace");
    const shortRef = job.ref.slice("refs/heads/".length);
    const format = runGit(["check-ref-format", "--branch", shortRef], { cwd: repoDir, timeout: 10000 });
    if (format.code !== 0) return finish("blocked-namespace", "ref fails git check-ref-format");

    const listing = lsRemote(url, null, 60_000);
    if (!listing.reachable) return finish("blocked-remote-unreachable", "ls-remote could not read the destination");
    const existing = listing.refs.find((item) => item.ref === job.ref);
    if (existing && existing.sha === job.sha) {
      clearInterval(heartbeat);
      const current = readJob(key) ?? job;
      current.state = "verified";
      current.outcome = "verified-present";
      current.detail = "ref already at the checkpoint SHA; nothing pushed";
      writeJob(current);
      return "verified-present";
    }
    if (existing) return finish("blocked-collision", "different-sha");
    for (const item of listing.refs) {
      if (item.ref.startsWith(`${job.ref}/`) || job.ref.startsWith(`${item.ref}/`)) {
        return finish("blocked-collision", "df-conflict");
      }
    }

    const tips = [
      ...new Set(listing.refs.filter((item) => item.ref.startsWith("refs/heads/")).map((item) => item.sha)),
    ];
    const present = tips.filter((tip) =>
      runGit(["cat-file", "-e", `${tip}^{commit}`], { cwd: repoDir, timeout: 10000 }).code === 0
    );
    if (present.length === 0) return finish("blocked-missing-baseline", "no advertised tip is present locally");

    let related = false;
    for (const tip of present) {
      const base = runGit(["merge-base", job.sha, tip], { cwd: repoDir, timeout: 30000 });
      if (base.code === 0 && /^[0-9a-f]{40}/.test(base.stdout.trim())) {
        related = true;
        break;
      }
    }
    if (!related) {
      return finish("blocked-unrelated-ancestry", "the checkpoint shares no ancestry with any advertised tip");
    }

    const unique = revListNot(repoDir, job.sha, present);
    const allowed = new Set([...job.provenance, ...revListNot(repoDir, job.sha, job.provenanceTips)]);
    if (!unique.every((commit) => allowed.has(commit))) {
      return finish("blocked-provenance", "a commit outside the recorded provenance list would be pushed");
    }

    for (const commit of unique) {
      const sig = runGit(["log", "-1", "--format=%G?", commit], { cwd: repoDir, timeout: 10000 });
      const flag = sig.stdout.trim();
      if (sig.code !== 0 || flag !== "G") {
        return finish(
          "blocked-unsigned",
          `commit ${commit.slice(0, 12)} is not signed with a good signature (${
            flag || "unreadable"
          }); never retried with signing disabled`,
        );
      }
    }

    const push = runGit(["push", url, `${job.sha}:${job.ref}`], { cwd: repoDir, timeout: attemptBudgetMs() });
    if (push.code !== 0) {
      if (push.signal) return finish("blocked-timeout", "push exceeded the attempt budget");
      if (HOOK_REJECTION_RE.test(push.stderr)) {
        return finish("blocked-hook-rejected", "the pre-push hook rejected the checkpoint; local work is intact", {
          exitCode: push.code,
          hookOutput: lastLines(push.stderr, 20),
        });
      }
      return finish("blocked-remote-rejected", lastLines(push.stderr, 5), {
        exitCode: push.code,
        hookOutput: lastLines(push.stderr, 20),
      });
    }

    const current = readJob(key) ?? job;
    current.state = "pushed";
    current.heartbeatAt = toIso(deps.now());
    writeJob(current);

    const readback = lsRemote(url, job.ref, 60_000);
    const readbackSha = readback.refs.find((item) => item.ref === job.ref)?.sha;
    if (!readback.reachable) return finish("blocked-remote-unreachable", "read-back could not reach the destination");
    if (readbackSha !== job.sha) {
      return finish("blocked-remote-rejected", "read-back did not show the ref at the pushed SHA", {
        hookOutput: lastLines(push.stdout + push.stderr, 20),
      });
    }
    if (deps.now() - startedAt > attemptBudgetMs()) return finish("blocked-timeout", "attempt exceeded its budget");
    return finish("verified", "pushed and verified by ls-remote read-back");
  }
}

function lastLines(text: string, count: number): string[] {
  return text
    .split("\n")
    .map((line) => line.trimEnd())
    .filter((line) => line.length > 0)
    .slice(-count);
}

// ---------------------------------------------------------------------------
// Mise reconciliation (ZYS-9038, ADR section 10)
// ---------------------------------------------------------------------------

export interface MiseSyncStatus {
  origin?: string;
  branch?: string;
  mode?: string;
  last_publish?: string | null;
  pending_applications?: string[] | null;
  conflicts?: unknown[] | null;
  last_error?: string | null;
  failing_since?: string | null;
}

export interface MiseStatusHistory {
  enabled?: boolean;
  unsaved?: string[] | null;
  pending_operations?: number;
  sync?: MiseSyncStatus;
  history_repo?: string;
}

export interface MiseCoverage {
  /** path (tilde form) -> autosave (false means manual-save) */
  autosaveByPath: Map<string, boolean>;
  available: boolean;
}

export function syncCeilingMs(): number {
  const raw = parseInt(deps.env.AGENT_CHECKPOINT_MISE_SYNC_MS ?? "", 10);
  return Number.isFinite(raw) && raw > 0 ? raw : 12_000;
}

function lsRemoteCeilingMs(): number {
  const raw = parseInt(deps.env.AGENT_CHECKPOINT_MISE_LSREMOTE_MS ?? "", 10);
  return Number.isFinite(raw) && raw > 0 ? raw : 5_000;
}

function runMise(args: string[], timeoutMs: number): RunResult {
  return deps.spawn("mise", args, { timeout: timeoutMs });
}

export function readMiseStatus(): MiseStatusHistory | null {
  const r = runMise(["dot", "status", "--json"], 20_000);
  if (r.code !== 0) return null;
  try {
    const parsed = JSON.parse(r.stdout) as { history?: MiseStatusHistory };
    return parsed.history ?? null;
  } catch {
    return null;
  }
}

export function readMiseCoverage(): MiseCoverage {
  const r = runMise(["dot", "history", "show", "--json"], 20_000);
  if (r.code === 0) {
    try {
      const parsed = JSON.parse(r.stdout) as {
        tree?: { coverage?: { entries?: { path: string; autosave?: boolean }[] } };
      };
      const entries = parsed.tree?.coverage?.entries ?? [];
      const map = new Map<string, boolean>();
      for (const entry of entries) map.set(entry.path, entry.autosave !== false);
      return { autosaveByPath: map, available: true };
    } catch {
      // fall through to `mise dot paths`
    }
  }
  // Fallback: the paths table prints `track manual-save` rows for autosave = false.
  const paths = runMise(["dot", "paths"], 20_000);
  const map = new Map<string, boolean>();
  if (paths.code === 0) {
    for (const line of paths.stdout.split("\n")) {
      const m = line.trim().match(/^(\S+)\s+track\s+(default|manual-save)\b/);
      if (m) map.set(m[1], m[2] === "default");
    }
    return { autosaveByPath: map, available: map.size > 0 };
  }
  return { autosaveByPath: map, available: false };
}

export interface StampFacts {
  present: boolean;
  ageMs: number | null;
}

export function manualSaveStampFacts(): StampFacts {
  const everyS = parseInt(deps.env.MISE_HISTORY_MANUAL_SAVE_EVERY_S ?? "", 10);
  const everyMs = (Number.isFinite(everyS) && everyS > 0 ? everyS : 86_400) * 1000;
  const logDir = resolveTilde(deps.env.MISE_HISTORY_LOG_DIR)
    ?? path.join(home(), ".local", "state", "mise-history-watchdog");
  const stamp = path.join(logDir, "manual-save.stamp");
  const mtime = deps.statMtime(stamp);
  if (mtime === null) return { present: false, ageMs: null };
  return { present: true, ageMs: deps.now() - mtime };
}

export function manualSaveEveryMs(): number {
  const everyS = parseInt(deps.env.MISE_HISTORY_MANUAL_SAVE_EVERY_S ?? "", 10);
  return (Number.isFinite(everyS) && everyS > 0 ? everyS : 86_400) * 1000;
}

export interface MiseDecisionInput {
  mode: string;
  conflicts: { path: string; reason: string }[];
  lastError: string | null;
  failingSince: string | null;
  unsavedAutosave: string[];
  unsavedManualSave: string[];
  stamp: StampFacts;
  manualSaveEveryMs: number;
  pendingOperations: number;
  pendingApplications: string[];
  reconciliationQueued: boolean;
  declaredCanonical: string | null;
  declaredDestinationPresent: boolean;
  liveOrigin?: string;
  originReachable: boolean | null;
}

export type MiseDecision =
  | { outcome: "blocked"; conditions: MiseCondition[] }
  | { outcome: "pending"; reason: string }
  | { outcome: "scheduled"; paths: string[] }
  | { outcome: "verify" };

/** The deterministic outcome rules. Precedence: blocked > pending > scheduled > verified. */
export function decideMiseOutcome(input: MiseDecisionInput): MiseDecision {
  const conditions: MiseCondition[] = [];

  if (input.conflicts.length > 0) {
    const paths = input.conflicts.map((conflict) => conflict.path);
    const commands: string[] = [];
    for (const path of paths) {
      commands.push(`mise dot conflicts ${path}`);
      commands.push(`mise dot pull --take-remote ${path}`);
      commands.push(`mise dot pull --keep-local ${path}`);
    }
    conditions.push({
      reason: "conflict",
      message: "paths changed on both sides; the owner resolves each one manually",
      paths,
      commands,
    });
  }
  if (input.lastError !== null || input.failingSince !== null) {
    conditions.push({
      reason: "failing",
      message: "sync is failing; see history.sync.last_error / failing_since",
    });
  }
  if (input.originReachable === false) {
    conditions.push({ reason: "offline", message: "the dotfiles origin is unreachable" });
  }
  if (input.mode !== "sync") {
    conditions.push({
      reason: "fetch-only",
      message: input.mode === "fetch-only"
        ? "the configured adopt state on this machine is fetch-only; nothing is pushed"
        : `history.sync.mode is "${input.mode}"; no push happens in this mode`,
    });
  }
  if (input.unsavedAutosave.length > 0) {
    conditions.push({
      reason: "unsaved",
      message: "autosave paths with unsaved edits; the watcher or mise dot save captures them, never this extension",
      paths: input.unsavedAutosave,
    });
  }
  const manualOverdue = input.unsavedManualSave.length > 0
    && (!input.stamp.present || (input.stamp.ageMs !== null && input.stamp.ageMs >= input.manualSaveEveryMs));
  if (manualOverdue) {
    conditions.push({
      reason: "manual-save-overdue",
      message: input.stamp.present
        ? "a manual-save path is unsaved and the watchdog stamp is at or past its 24 h cadence"
        : "a manual-save path is unsaved and the watchdog stamp is missing",
      paths: input.unsavedManualSave,
    });
  }
  const destinationMatches = input.declaredDestinationPresent
    && input.declaredCanonical !== null
    && input.declaredCanonical === (input.liveOrigin ?? undefined);
  if (!destinationMatches) {
    conditions.push({
      reason: "destination-changed",
      message: input.declaredDestinationPresent
        ? "the live dotfiles origin differs from the canonical declared in enrollment"
        : "the enrollment file declares no [destinations.\"mise-history\"] canonical for the live origin",
    });
  }

  if (conditions.length > 0) return { outcome: "blocked", conditions };
  if (input.pendingOperations > 0 || input.pendingApplications.length > 0) {
    return { outcome: "pending", reason: "mise reports pending operations" };
  }
  if (input.reconciliationQueued) return { outcome: "pending", reason: "reconciliation-queued" };
  if (input.unsavedManualSave.length > 0) return { outcome: "scheduled", paths: input.unsavedManualSave };
  return { outcome: "verify" };
}

export interface MiseVerification {
  syncExit: number | null;
  conflicts: boolean;
  pendingOperations: number;
  lastError: string | null;
  localHead: string | null;
  remoteHead: string | null;
  originReachable: boolean;
}

/** `verified` requires evidence, never a plain exit code (R10.8). */
export function verifyMiseOutcome(
  v: MiseVerification,
): { outcome: "verified" | "blocked" | "pending"; detail?: string } {
  if (v.syncExit === null) {
    // the sync attempt was killed by its ceiling; the caller queues a job
    return { outcome: "pending", detail: "sync did not finish inside the handler budget" };
  }
  if (v.conflicts) return { outcome: "blocked", detail: "sync recorded conflicts" };
  if (v.lastError !== null) return { outcome: "blocked", detail: "sync reported an error" };
  if (v.pendingOperations > 0) return { outcome: "pending", detail: "history still reports pending operations" };
  if (!v.originReachable) return { outcome: "blocked", detail: "the origin is unreachable" };
  if (v.localHead === null && v.remoteHead === null) {
    return { outcome: "verified", detail: "no history exists on either side" };
  }
  if (v.localHead === null) return { outcome: "blocked", detail: "the local history head is unreadable" };
  if (v.remoteHead === null) return { outcome: "blocked", detail: "the origin has no history branch after sync" };
  if (v.localHead !== v.remoteHead) {
    return { outcome: "blocked", detail: "the origin head does not equal the local history head after sync" };
  }
  return { outcome: "verified" };
}

export interface MiseJobRecord {
  key: string;
  origin: string;
  branch: string;
  state: "queued" | "verified" | "failed";
  outcome?: MiseOutcome;
  detail?: string;
  createdAt: string;
  updatedAt: string;
}

function miseJobKey(origin: string, branch: string): string {
  return createHash("sha256").update(`${origin}\0${branch}`).digest("hex");
}

function miseJobPath(key: string): string {
  return path.join(stateDir(), "mise-jobs", `${key}.json`);
}

function readMiseJob(key: string): MiseJobRecord | null {
  const text = deps.readFile(miseJobPath(key));
  if (text === null) return null;
  try {
    return JSON.parse(text) as MiseJobRecord;
  } catch {
    return null;
  }
}

function writeMiseJob(record: MiseJobRecord): void {
  record.updatedAt = new Date(deps.now()).toISOString();
  writeFileAtomic(miseJobPath(record.key), `${JSON.stringify(record, null, "\t")}\n`);
}

function removeMiseJob(key: string): void {
  try {
    unlinkSync(miseJobPath(key));
  } catch {
    // already gone
  }
}

function localHistoryHead(historyRepo: string | null): string | null {
  if (!historyRepo) return null;
  const r = runGit(["rev-parse", "HEAD"], { cwd: historyRepo, timeout: 10_000 });
  if (r.code !== 0) return null;
  const sha = r.stdout.trim();
  return /^[0-9a-f]{40}$/.test(sha) ? sha : null;
}

/**
 * Compute the mise reconciliation outcome. Read-only except one
 * `mise dot sync` when verification requires it, and the detached
 * reconciliation worker when that sync exceeds the handler budget.
 */
export function reconcileMise(declaredCanonical: string | null, declaredPresent: boolean): MiseReport | undefined {
  if (!deps.which("mise")) return undefined; // nothing to reconcile on this machine

  const status = readMiseStatus();
  if (!status || status.enabled !== true) return undefined;

  const sync = status.sync ?? {};
  const conflicts = (sync.conflicts ?? []).map((item) => {
    if (Array.isArray(item) && typeof item[0] === "string") {
      return { path: item[0], reason: typeof item[1] === "string" ? item[1] : "" };
    }
    return { path: String(item), reason: "" };
  });
  const unsaved = (status.unsaved ?? []).map((item) => (typeof item === "string" ? item : String(item)));
  const coverage = readMiseCoverage();
  const stamp = manualSaveStampFacts();
  const unsavedAutosave: string[] = [];
  const unsavedManualSave: string[] = [];
  for (const p of unsaved) {
    const autosave = coverage.autosaveByPath.get(p);
    if (autosave === false) unsavedManualSave.push(p);
    else unsavedAutosave.push(p);
  }

  const origin = sync.origin;
  const key = miseJobKey(origin ?? "<unset>", sync.branch ?? "history");
  const miseJob = readMiseJob(key);
  const reconciliationQueued = miseJob !== null && miseJob.state === "queued";
  if (miseJob && miseJob.state !== "queued") removeMiseJob(key);

  const probe = origin
    ? lsRemote(origin, `refs/heads/${sync.branch ?? "history"}`, lsRemoteCeilingMs())
    : { refs: [], reachable: false };
  const remoteHead = probe.refs.find((item) => item.ref === `refs/heads/${sync.branch ?? "history"}`)?.sha ?? null;
  const historyRepo = resolveTilde(status.history_repo) ?? null;
  const localHead = localHistoryHead(historyRepo);

  const decision = decideMiseOutcome({
    mode: sync.mode ?? "",
    conflicts,
    lastError: sync.last_error ?? null,
    failingSince: sync.failing_since ?? null,
    unsavedAutosave,
    unsavedManualSave,
    stamp,
    manualSaveEveryMs: manualSaveEveryMs(),
    pendingOperations: status.pending_operations ?? 0,
    pendingApplications: sync.pending_applications ?? [],
    reconciliationQueued,
    declaredCanonical,
    declaredDestinationPresent: declaredPresent,
    liveOrigin: origin,
    originReachable: probe.reachable ? true : null,
  });

  if (decision.outcome === "blocked" || decision.outcome === "pending" || decision.outcome === "scheduled") {
    return miseReportFromDecision(decision, {
      syncRan: false,
      localHead,
      remoteHead: probe.reachable ? remoteHead : null,
    });
  }

  // candidate verified: one bounded sync, then evidence (R10.8)
  const syncRun = runMise(["dot", "sync"], syncCeilingMs());
  if (syncRun.code === null) {
    // exceeded the handler budget: queue the detached reconciliation worker
    const record: MiseJobRecord = {
      key,
      origin: origin ?? "<unset>",
      branch: sync.branch ?? "history",
      state: "queued",
      createdAt: new Date(deps.now()).toISOString(),
      updatedAt: new Date(deps.now()).toISOString(),
    };
    writeMiseJob(record);
    if (deps.which("setsid") && deps.which("flock")) {
      const lock = path.join(stateDir(), "mise-jobs", `${key}.lock`);
      deps.mkdirs(path.dirname(lock));
      const self = selfPath();
      if (self) {
        deps.spawnDetached(
          "setsid",
          ["flock", lock, process.execPath, self, "--agent-checkpoint-mise-worker", key],
          { ...gitEnv(), AGENT_CHECKPOINT_PUBLISH: "1" },
        );
      }
    }
    return {
      outcome: "pending",
      reason: "reconciliation-queued",
      detail: "mise dot sync exceeded the handler budget; a detached worker finishes it",
      paths: undefined,
      conditions: undefined,
      commands: undefined,
      syncRan: false,
      localHead,
      remoteHead,
    };
  }
  const postStatus = readMiseStatus() ?? status;
  const postSync = postStatus.sync ?? {};
  const postProbe = origin
    ? lsRemote(origin, `refs/heads/${postSync.branch ?? sync.branch ?? "history"}`, lsRemoteCeilingMs())
    : { refs: [], reachable: false };
  const postRemoteHead = postProbe.refs.find((item) => item.ref === `refs/heads/${postSync.branch ?? "history"}`)?.sha
    ?? null;
  const postLocalHead = localHistoryHead(resolveTilde(postStatus.history_repo) ?? historyRepo);

  const verification = verifyMiseOutcome({
    syncExit: syncRun.code,
    conflicts: (postSync.conflicts ?? []).length > 0,
    pendingOperations: postStatus.pending_operations ?? 0,
    lastError: postSync.last_error ?? null,
    localHead: postLocalHead,
    remoteHead: postProbe.reachable ? postRemoteHead : null,
    originReachable: postProbe.reachable,
  });
  if (verification.outcome === "verified") {
    return {
      outcome: "verified",
      syncRan: true,
      localHead: postLocalHead,
      remoteHead: postRemoteHead,
      detail: verification.detail,
    };
  }
  if (verification.outcome === "pending") {
    return {
      outcome: "pending",
      reason: "pending-operations",
      detail: verification.detail,
      syncRan: true,
      localHead: postLocalHead,
      remoteHead: postRemoteHead,
    };
  }
  return {
    outcome: "blocked",
    reason: "failing",
    detail: verification.detail,
    syncRan: true,
    localHead: postLocalHead,
    remoteHead: postRemoteHead,
  };
}

function miseReportFromDecision(
  decision: Exclude<MiseDecision, { outcome: "verify" }>,
  base: { syncRan: boolean; localHead: string | null; remoteHead: string | null },
): MiseReport {
  if (decision.outcome === "blocked") {
    const commands = decision.conditions.flatMap((condition) => condition.commands ?? []);
    return {
      outcome: "blocked",
      reason: decision.conditions[0].reason,
      conditions: decision.conditions,
      paths: decision.conditions.flatMap((condition) => condition.paths ?? []),
      commands: commands.length > 0 ? commands : undefined,
      syncRan: base.syncRan,
      localHead: base.localHead,
      remoteHead: base.remoteHead,
    };
  }
  if (decision.outcome === "pending") {
    return {
      outcome: "pending",
      reason: decision.reason,
      syncRan: base.syncRan,
      localHead: base.localHead,
      remoteHead: base.remoteHead,
    };
  }
  return {
    outcome: "scheduled",
    paths: decision.paths,
    syncRan: base.syncRan,
    localHead: base.localHead,
    remoteHead: base.remoteHead,
  };
}

/** The detached mise reconciliation worker: finish the sync the handler could not. */
export function runMiseWorker(key: string): MiseOutcome | null {
  const record = readMiseJob(key);
  if (!record || record.state !== "queued") return null;
  const syncRun = runMise(["dot", "sync"], 5 * 60_000);
  const status = readMiseStatus();
  const sync = status?.sync ?? {};
  const origin = sync.origin;
  const probe = origin
    ? lsRemote(origin, `refs/heads/${sync.branch ?? "history"}`, 30_000)
    : { refs: [], reachable: false };
  const remoteHead = probe.refs.find((item) => item.ref === `refs/heads/${sync.branch ?? "history"}`)?.sha ?? null;
  const localHead = localHistoryHead(resolveTilde(status?.history_repo) ?? null);
  const verification = verifyMiseOutcome({
    syncExit: syncRun.code,
    conflicts: (sync.conflicts ?? []).length > 0,
    pendingOperations: status?.pending_operations ?? 0,
    lastError: sync.last_error ?? null,
    localHead,
    remoteHead: probe.reachable ? remoteHead : null,
    originReachable: probe.reachable,
  });
  record.state = verification.outcome === "verified" ? "verified" : "failed";
  record.outcome = verification.outcome === "pending" ? "pending" : verification.outcome;
  record.detail = verification.detail;
  writeMiseJob(record);
  return record.outcome;
}

// ---------------------------------------------------------------------------
// Turn-end report (the one surface omp surfaces per turn)
// ---------------------------------------------------------------------------

export function buildTurnEndReport(repoDir: string): TurnEndReport {
  const report: TurnEndReport = { schema: 1, at: new Date(deps.now()).toISOString() };

  const enrollment = loadEnrollment();
  if (gitCommonDirOf(repoDir)) {
    try {
      report.repository = repositoryReport(repoDir, enrollment);
    } catch (error) {
      report.repository = { outcome: "failed", detail: `publication error: ${String(error)}` };
    }
  }

  const destination = enrollment?.destinations.find((item) => item.name === "mise-history") ?? null;
  try {
    const mise = reconcileMise(destination?.canonical ?? null, destination !== null);
    if (mise) report.mise = mise;
  } catch (error) {
    report.mise = {
      outcome: "blocked",
      reason: "failing",
      detail: `reconciliation error: ${String(error)}`,
      syncRan: false,
    };
  }
  return report;
}

export function reportDir(): string {
  return path.join(stateDir(), "reports");
}

export function writeReport(report: TurnEndReport): string {
  const dir = reportDir();
  deps.mkdirs(dir);
  const stamp = report.at.replace(/[:.]/g, "-");
  const perTurn = path.join(dir, `agent-end-${stamp}.json`);
  writeFileAtomic(perTurn, `${JSON.stringify(report, null, "\t")}\n`);
  writeFileAtomic(path.join(dir, "last-report.json"), `${JSON.stringify(report, null, "\t")}\n`);
  pruneReports(dir);
  return perTurn;
}

function pruneReports(dir: string): void {
  const cutoff = deps.now() - 7 * 24 * 60 * 60 * 1000;
  try {
    for (const file of readdirSync(dir)) {
      if (!file.startsWith("agent-end-")) continue;
      const full = path.join(dir, file);
      try {
        if (statSync(full).mtimeMs < cutoff) unlinkSync(full);
      } catch {
        // vanished meanwhile
      }
    }
  } catch {
    // pruning is best effort
  }
}

function notifyLine(report: TurnEndReport): string {
  const repo = report.repository ? ` checkpoint: ${report.repository.outcome}` : "";
  const mise = report.mise
    ? ` · mise: ${report.mise.outcome}${report.mise.reason ? `/${report.mise.reason}` : ""}`
    : "";
  return `turn end${repo}${mise}`;
}

export type OmpContext = {
  hasUI?: boolean;
  cwd?: string;
  ui?: { notify?: (message: string, type?: "info" | "warning" | "error") => void };
};

export type ExtensionAPI = {
  on: (event: string, handler: (event: unknown, ctx: OmpContext) => unknown) => void;
};

export default function agentCheckpointPublish(pi: ExtensionAPI): void {
  pi.on("agent_end", (event: { willContinue?: boolean } | undefined, ctx: OmpContext) => {
    try {
      // R5.4: a continuation is scheduled; this end is not a settle.
      if (event?.willContinue === true) return;
      // R8.3: never act inside the worker.
      if (deps.env.AGENT_CHECKPOINT_PUBLISH === "1") return;
      const repoDir = ctx?.cwd ?? process.cwd();
      const report = buildTurnEndReport(repoDir);
      writeReport(report);
      if (ctx?.hasUI && typeof ctx.ui?.notify === "function") {
        ctx.ui.notify(
          notifyLine(report),
          report.mise?.outcome === "blocked" || report.repository?.outcome.startsWith("blocked") ? "warning" : "info",
        );
      }
    } catch {
      // the extension never breaks a turn end
    }
  });
}

// ---------------------------------------------------------------------------
// Worker entry points (spawned via setsid/flock by the handler or launchWorker)
// ---------------------------------------------------------------------------

if (import.meta.main) {
  const args = process.argv.slice(2);
  const mode = args[0];
  const key = args[1];
  if (mode === "--agent-checkpoint-worker" && key) {
    process.exitCode = runCheckpointWorker(key) ? 0 : 1;
  } else if (mode === "--agent-checkpoint-mise-worker" && key) {
    process.exitCode = runMiseWorker(key) ? 0 : 1;
  } else {
    process.stderr.write(
      `usage: ${process.argv[1]} --agent-checkpoint-worker <jobKey> | --agent-checkpoint-mise-worker <jobKey>\n`,
    );
    process.exitCode = 2;
  }
}
