// Hermetic tests for the turn-stop checkpoint publication extension
// (apps/omp/extensions/agent-checkpoint-publish.ts).
//
// Every mise fixture runs in a sandbox HOME with its own MISE_CONFIG_DIR,
// MISE_STATE_DIR and MISE_HISTORY_LOG_DIR, and a bare-repo dotfiles origin -
// never the real origin and never the real ~/.gitconfig. A PATH shim records
// every mise invocation the extension makes, so the suite proves the
// extension never runs `mise dot pull`, `mise dot save`, `mise dot recover`,
// `mise dot bootstrap`, and never passes `--allow-plaintext-history`.
import { beforeEach, describe, expect, setDefaultTimeout, test } from "bun:test";
import { spawnSync } from "node:child_process";
import {
  chmodSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  utimesSync,
  writeFileSync,
} from "node:fs";
import os from "node:os";
import path from "node:path";
import * as acp from "./agent-checkpoint-publish.ts";

const suiteRoot = path.join(
  os.tmpdir(),
  `acp-tests-${process.pid}-${Date.now()}`,
);
mkdirSync(suiteRoot, { recursive: true });
// Many tests spawn git/mise/bun children; bun's 5 s default is too tight under load.
setDefaultTimeout(60_000);

// Hermetic git: the machine's global config installs hk hooks (hook.hk-*) that
// would fire on every fixture commit and push. A suite-owned global config
// keeps fixture repositories free of them; tests that need a hook write it.
const suiteGitConfig = path.join(suiteRoot, "gitconfig");
writeFileSync(
  suiteGitConfig,
  "[user]\n\tname = acp-fixture\n\temail = fixture@probe\n[init]\n\tdefaultBranch = main\n",
);
process.env.GIT_CONFIG_GLOBAL = suiteGitConfig;
process.env.GIT_CONFIG_NOSYSTEM = "1";

// ---------------------------------------------------------------------------
// Signing: every test repository signs its commits over SSH, the way the
// profile signs GPG commits on real machines. allowedSignersFile makes
// `git log --format=%G?` report "G" inside the worker.
const signingKey = path.join(suiteRoot, "signing-key");
const signersFile = path.join(suiteRoot, "allowed_signers");
spawnSync("ssh-keygen", ["-t", "ed25519", "-N", "", "-f", signingKey, "-C", "acp-test"], {
  env: process.env,
});
writeFileSync(signersFile, `fixture@probe ${readFileSync(`${signingKey}.pub`, "utf8")}`);
chmodSync(signersFile, 0o600);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

interface RunOut {
  code: number;
  stdout: string;
  stderr: string;
}

function sh(
  cmd: string,
  args: string[],
  env: Record<string, string | undefined>,
  cwd?: string,
  timeout = 120_000,
): RunOut {
  const r = spawnSync(cmd, args, {
    env: env as NodeJS.ProcessEnv,
    cwd,
    timeout,
    encoding: "utf8",
    maxBuffer: 16 * 1024 * 1024,
  });
  return { code: r.status ?? -1, stdout: r.stdout ?? "", stderr: r.stderr ?? "" };
}

function shOut(cmd: string, args: string[], env: Record<string, string | undefined>, cwd?: string): string {
  return sh(cmd, args, env, cwd).stdout.trim();
}

const GIT_IDENTITY = {
  GIT_AUTHOR_NAME: "acp-fixture",
  GIT_AUTHOR_EMAIL: "fixture@probe",
  GIT_COMMITTER_NAME: "acp-fixture",
  GIT_COMMITTER_EMAIL: "fixture@probe",
};

export interface SandboxOpts {
  mode?: "sync" | "fetch-only";
  /** "dead" points the origin at a path that does not exist; otherwise a bare repo is created. */
  origin?: "dead" | string;
  declareMise?: boolean;
  miseCanonical?: string;
  manualSaveEveryS?: number;
}

export interface Sandbox {
  root: string;
  home: string;
  origin: string;
  state: string;
  logs: string;
  agentState: string;
  binDir: string;
  argvLog: string;
  configPath: string;
  enrollmentPath: string;
  env: Record<string, string>;
  /** Arrange mise state with the real mise binary (recorded, but truncated before extension calls). */
  miseRun(args: string[], envOverride?: Record<string, string>): RunOut;
  setMode(mode: "sync" | "fetch-only"): void;
  truncateArgvLog(): void;
  argvLogLines(): string[];
  configBytes(): string;
  touchStamp(ageSeconds?: number): void;
  stampMtime(): number | null;
  dispose(): void;
}

function makeSandbox(opts: SandboxOpts = {}): Sandbox {
  const root = path.join(suiteRoot, `sb-${Math.random().toString(36).slice(2)}`);
  const home = path.join(root, "home");
  const origin = opts.origin === "dead"
    ? path.join(root, "dead-origin.git")
    : (opts.origin ?? path.join(root, "origin.git"));
  const state = path.join(root, "state");
  const logs = path.join(root, "logs");
  const agentState = path.join(root, "agent-state");
  const binDir = path.join(root, "bin");
  const argvLog = path.join(root, "mise-argv.log");
  for (const dir of [home, path.join(home, ".config", "mise"), state, logs, agentState, binDir]) {
    mkdirSync(dir, { recursive: true });
  }
  if (opts.origin !== "dead") {
    sh("git", ["init", "--bare", "-b", "history", origin], process.env);
  }
  const mode = opts.mode ?? "sync";
  const configPath = path.join(home, ".config", "mise", "config.toml");
  writeFileSync(
    configPath,
    [
      "[dotfiles]",
      "\"~/.dot-a\" = { mode = \"track\" }",
      "\"~/.gitconfig\" = { mode = \"track\", autosave = false }",
      "",
      "[history]",
      "git_email = \"fixture@probe\"",
      "",
      "[history.origin]",
      `url = "${origin}"`,
      "branch = \"history\"",
      "",
      "[settings.history]",
      `sync = "${mode}"`,
      "",
    ].join("\n"),
  );
  // a valid gitconfig: git parses it while mise captures it as a dotfile
  writeFileSync(path.join(home, ".gitconfig"), "[user]\n\tname = fixture\n\temail = fixture@probe\n");
  writeFileSync(path.join(home, ".dot-a"), "v1\n");
  // argv-recording mise shim, first on PATH
  const miseBin = shOut("bash", ["-lc", "command -v mise"], process.env) || "mise";
  writeFileSync(
    path.join(binDir, "mise"),
    `#!/usr/bin/env bash\nprintf '%s\\n' "$*" >> "${argvLog}"\nexec "${miseBin}" "$@"\n`,
  );
  chmodSync(path.join(binDir, "mise"), 0o755);
  const env: Record<string, string> = {
    ...process.env,
    ...GIT_IDENTITY,
    HOME: home,
    XDG_CONFIG_HOME: path.join(home, ".config"),
    XDG_STATE_HOME: path.join(home, ".local", "state"),
    XDG_DATA_HOME: path.join(home, ".local", "share"),
    XDG_CACHE_HOME: path.join(home, ".cache"),
    MISE_GLOBAL_CONFIG_FILE: configPath,
    MISE_TRUSTED_CONFIG_PATHS: configPath,
    MISE_STATE_DIR: state,
    MISE_DATA_DIR: path.join(root, "data"),
    MISE_CACHE_DIR: path.join(root, "cache"),
    MISE_HISTORY_LOG_DIR: logs,
    AGENT_CHECKPOINT_STATE_DIR: agentState,
    AGENT_CHECKPOINT_ENROLLMENT: path.join(root, "enrollment.toml"),
    PATH: `${binDir}:${process.env.PATH ?? ""}`,
  };
  if (opts.manualSaveEveryS !== undefined) env.MISE_HISTORY_MANUAL_SAVE_EVERY_S = String(opts.manualSaveEveryS);
  const sb: Sandbox = {
    root,
    home,
    origin,
    state,
    logs,
    agentState,
    binDir,
    argvLog,
    configPath,
    enrollmentPath: env.AGENT_CHECKPOINT_ENROLLMENT,
    env,
    miseRun(args, envOverride) {
      return sh("mise", args, { ...env, ...(envOverride ?? {}) }, root);
    },
    setMode(newMode) {
      const text = readFileSync(configPath, "utf8").replace(/sync = "(sync|fetch-only)"/, `sync = "${newMode}"`);
      writeFileSync(configPath, text);
    },
    truncateArgvLog() {
      writeFileSync(argvLog, "");
    },
    argvLogLines() {
      return readFileSync(argvLog, "utf8").split("\n").filter((line) => line.length > 0);
    },
    configBytes() {
      return readFileSync(configPath, "utf8");
    },
    touchStamp(ageSeconds = 0) {
      const stamp = path.join(logs, "manual-save.stamp");
      writeFileSync(stamp, "");
      if (ageSeconds > 0) {
        const at = new Date(Date.now() - ageSeconds * 1000);
        utimesSync(stamp, at, at);
      }
    },
    stampMtime() {
      const stamp = path.join(logs, "manual-save.stamp");
      if (!existsSync(stamp)) return null;
      return statSync(stamp).mtimeMs;
    },
    dispose() {
      rmSync(root, { recursive: true, force: true });
    },
  };
  enroll(sb, {});
  return sb;
}

/** The publisher derives its destination from an existing remote (ADR 7.1): give a fixture repository one. */
function ensureRemote(repo: string, url: string): void {
  if (shOut("git", ["-C", repo, "remote"], process.env) !== "") return;
  sh("git", ["-C", repo, "remote", "add", "origin", url], process.env);
}

function enroll(sb: Sandbox, opts: {
  declareMise?: boolean;
  miseCanonical?: string;
  repos?: {
    slug: string;
    path: string;
    canonical: string;
    enabled?: boolean;
    visibility?: string;
    remote?: string | false;
  }[];
}): void {
  const lines = ["", "schema_version = 1", ""];
  if (opts.declareMise !== false) {
    lines.push(
      "[destinations.\"mise-history\"]",
      "kind = \"mise-dot\"",
      `canonical = "${opts.miseCanonical ?? sb.origin}"`,
      "branch = \"history\"",
      "mode = \"fetch-only\"",
      "",
    );
  }
  for (const repo of opts.repos ?? []) {
    if (repo.remote !== false) ensureRemote(repo.path, repo.remote ?? repo.canonical);
    lines.push(`[repos."${repo.slug}"]`);
    lines.push(`enabled = ${repo.enabled ?? true}`);
    lines.push(`path = "${repo.path}"`);
    lines.push(`canonical = "${repo.canonical}"`);
    if (repo.visibility) lines.push(`visibility = "${repo.visibility}"`);
    lines.push("");
  }
  writeFileSync(sb.enrollmentPath, lines.join("\n") + "\n");
}

/**
 * Builds the turn-end report. The detached worker is stubbed unless the test
 * asks for it, so an in-process runCheckpointWorker call is the only actor on
 * the job.
 */
function buildReport(sb: Sandbox, repoDir?: string, opts: { spawnWorker?: boolean } = {}): acp.TurnEndReport {
  acp.__setDepsForTests({ env: sb.env as Record<string, string | undefined> });
  if (!opts.spawnWorker) acp.__setDepsForTests({ spawnDetached: () => {} });
  return acp.buildTurnEndReport(repoDir ?? sb.home);
}

async function waitUntil<T>(fn: () => T | undefined, timeoutMs: number, what: string): Promise<T> {
  const deadline = Date.now() + timeoutMs;
  let last: T | undefined;
  while (Date.now() < deadline) {
    last = fn();
    if (last !== undefined) return last;
    await Bun.sleep(100);
  }
  throw new Error(`timed out waiting for ${what}`);
}

// ---------------------------------------------------------------------------
// Git repository fixtures
// ---------------------------------------------------------------------------

function makeGitRepo(dir: string, opts: { sign?: boolean } = {}): string {
  mkdirSync(dir, { recursive: true });
  const sign = opts.sign ?? true;
  sh("git", ["init", "-b", "main", dir], process.env);
  const config: [string, string][] = [
    ["user.name", "acp-fixture"],
    ["user.email", "fixture@probe"],
    ["commit.gpgsign", sign ? "true" : "false"],
  ];
  if (sign) {
    config.push(["gpg.format", "ssh"], ["user.signingkey", signingKey], ["gpg.ssh.allowedSignersFile", signersFile]);
  }
  for (const [key, value] of config) sh("git", ["-C", dir, "config", key, value], process.env);
  commitFile(dir, "README.md", "initial\n", "initial commit");
  return dir;
}

function commitFile(repo: string, file: string, content: string, message: string): string {
  writeFileSync(path.join(repo, file), content);
  sh("git", ["-C", repo, "add", "-A"], process.env);
  sh("git", ["-C", repo, "commit", "-m", message], process.env);
  return shOut("git", ["-C", repo, "rev-parse", "HEAD"], process.env);
}

function lsRemoteOf(url: string, refspec?: string): { shas: string[]; ok: boolean } {
  const r = sh("git", ["ls-remote", url, ...(refspec ? [refspec] : [])], process.env, undefined, 30_000);
  if (r.code !== 0) return { shas: [], ok: false };
  return {
    shas: r.stdout.split("\n").map((l) => l.trim().split(/\s+/)[0]).filter((s) => /^[0-9a-f]{40}$/.test(s)),
    ok: true,
  };
}

// ---------------------------------------------------------------------------
beforeEach(() => {
  acp.__resetDeps();
});

describe("mise outcome (ZYS-9038)", () => {
  test(
    "saved and synced tracked file reports verified",
    async () => {
      const sb = makeSandbox();
      try {
        expect(sb.miseRun(["dot", "save"]).code).toBe(0);
        expect(sb.miseRun(["dot", "sync"]).code).toBe(0);
        const configBefore = sb.configBytes();
        sb.truncateArgvLog();
        const report = buildReport(sb);
        const mise = report.mise!;
        expect(mise.outcome).toBe("verified");
        expect(mise.syncRan).toBe(true);
        expect(mise.localHead).toBeTruthy();
        expect(mise.remoteHead).toBe(mise.localHead);
        const remote = lsRemoteOf(sb.origin, "refs/heads/history");
        expect(remote.shas).toContain(mise.localHead!);
        // the extension ran only read-only commands plus one sync
        const argv = sb.argvLogLines();
        expect(argv.filter((l) => l === "dot sync")).toHaveLength(1);
        expect(argv.some((l) => /^dot(files)? (pull|save|recover|bootstrap)/.test(l))).toBe(false);
        expect(argv.some((l) => l.includes("--allow-plaintext-history"))).toBe(false);
        // encryption, secret scans and configured destinations unchanged
        expect(sb.configBytes()).toBe(configBefore);
        expect(report.repository).toBeUndefined(); // not a git repository
      } finally {
        sb.dispose();
      }
    },
    90_000,
  );

  test(
    "changed manual-save path with a young stamp reports scheduled and the stamp is untouched",
    async () => {
      const sb = makeSandbox();
      try {
        expect(sb.miseRun(["dot", "save"]).code).toBe(0);
        expect(sb.miseRun(["dot", "sync"]).code).toBe(0);
        writeFileSync(path.join(sb.home, ".gitconfig"), "[user]\n\tname = changed\n");
        sb.touchStamp(60);
        const stampBefore = sb.stampMtime();
        sb.truncateArgvLog();
        const report = buildReport(sb);
        const mise = report.mise!;
        expect(mise.outcome).toBe("scheduled");
        expect(mise.paths).toEqual(["~/.gitconfig"]);
        expect(sb.stampMtime()).toBe(stampBefore);
        expect(sb.argvLogLines().some((l) => /^dot(files)? save/.test(l))).toBe(false);
      } finally {
        sb.dispose();
      }
    },
    90_000,
  );

  test(
    "manual-save path unsaved with no stamp is blocked manual-save-overdue",
    async () => {
      const sb = makeSandbox();
      try {
        expect(sb.miseRun(["dot", "save"]).code).toBe(0);
        writeFileSync(path.join(sb.home, ".gitconfig"), "[user]\n\tname = changed2\n");
        sb.truncateArgvLog();
        const report = buildReport(sb);
        expect(report.mise!.outcome).toBe("blocked");
        expect(report.mise!.reason).toBe("manual-save-overdue");
      } finally {
        sb.dispose();
      }
    },
    90_000,
  );

  test(
    "manual-save path unsaved with a stale stamp is blocked manual-save-overdue",
    async () => {
      const sb = makeSandbox();
      try {
        expect(sb.miseRun(["dot", "save"]).code).toBe(0);
        writeFileSync(path.join(sb.home, ".gitconfig"), "[user]\n\tname = changed3\n");
        sb.touchStamp(25 * 3600);
        const report = buildReport(sb);
        expect(report.mise!.outcome).toBe("blocked");
        expect(report.mise!.reason).toBe("manual-save-overdue");
      } finally {
        sb.dispose();
      }
    },
    90_000,
  );

  test(
    "path edited on both sides is blocked conflict with per-path commands; both versions recoverable",
    async () => {
      const sbA = makeSandbox();
      const sbB = makeSandbox({ origin: sbA.origin });
      try {
        expect(sbA.miseRun(["dot", "save"]).code).toBe(0);
        expect(sbA.miseRun(["dot", "sync"]).code).toBe(0);
        // machine B adopts the origin history, then diverges on the same path
        expect(sbB.miseRun(["bootstrap", "--adopt", sbA.origin, "--replace-history", "--yes"]).code).toBe(0);
        writeFileSync(path.join(sbB.home, ".dot-a"), "v2-B\n");
        expect(sbB.miseRun(["dot", "save"]).code).toBe(0);
        expect(sbB.miseRun(["dot", "sync"]).code).toBe(0);
        // machine A edits the same path and syncs: the push is held and a conflict is recorded
        writeFileSync(path.join(sbA.home, ".dot-a"), "v3-A\n");
        expect(sbA.miseRun(["dot", "save"]).code).toBe(0);
        expect(sbA.miseRun(["dot", "sync"]).code).toBe(0);
        const configBefore = sbA.configBytes();
        sbA.truncateArgvLog();
        const report = buildReport(sbA);
        const mise = report.mise!;
        expect(mise.outcome).toBe("blocked");
        expect(mise.reason).toBe("conflict");
        expect(mise.paths).toEqual(["~/.dot-a"]);
        expect(mise.commands).toContain("mise dot conflicts ~/.dot-a");
        expect(mise.commands).toContain("mise dot pull --take-remote ~/.dot-a");
        expect(mise.commands).toContain("mise dot pull --keep-local ~/.dot-a");
        // the extension never resolves anything
        expect(sbA.argvLogLines().some((l) => /^dot(files)? pull/.test(l))).toBe(false);
        expect(sbA.configBytes()).toBe(configBefore);
        // live --take-remote applies the origin's version; undo restores this side
        expect(sbA.miseRun(["dot", "pull", "--take-remote", "~/.dot-a"]).code).toBe(0);
        expect(readFileSync(path.join(sbA.home, ".dot-a"), "utf8")).toBe("v2-B\n");
        expect(sbA.miseRun(["dot", "undo", "-y"]).code).toBe(0);
        expect(readFileSync(path.join(sbA.home, ".dot-a"), "utf8")).toBe("v3-A\n");
      } finally {
        sbA.dispose();
        sbB.dispose();
      }
    },
    180_000,
  );

  test(
    "offline origin is blocked offline",
    async () => {
      const sb = makeSandbox({ origin: "dead" });
      try {
        expect(sb.miseRun(["dot", "save"]).code).toBe(0);
        const report = buildReport(sb);
        expect(report.mise!.outcome).toBe("blocked");
        expect(report.mise!.conditions!.map((condition) => condition.reason)).toContain("offline");
      } finally {
        sb.dispose();
      }
    },
    90_000,
  );

  test(
    "fetch-only mode is blocked fetch-only and never verified",
    async () => {
      const sb = makeSandbox({ mode: "fetch-only" });
      try {
        expect(sb.miseRun(["dot", "save"]).code).toBe(0);
        sb.truncateArgvLog();
        const report = buildReport(sb);
        const mise = report.mise!;
        expect(mise.outcome).toBe("blocked");
        expect(mise.reason).toBe("fetch-only");
        // fetch-only never syncs
        expect(sb.argvLogLines().some((l) => l === "dot sync")).toBe(false);
      } finally {
        sb.dispose();
      }
    },
    90_000,
  );

  test(
    "unsaved autosave path is blocked unsaved, never scheduled",
    async () => {
      const sb = makeSandbox();
      try {
        expect(sb.miseRun(["dot", "save"]).code).toBe(0);
        writeFileSync(path.join(sb.home, ".dot-a"), "v2-unsaved\n");
        sb.touchStamp(60); // a young stamp must not downgrade this to scheduled
        const report = buildReport(sb);
        const mise = report.mise!;
        expect(mise.outcome).toBe("blocked");
        expect(mise.reason).toBe("unsaved");
        expect(mise.paths).toEqual(["~/.dot-a"]);
        expect(mise.outcome).not.toBe("scheduled");
      } finally {
        sb.dispose();
      }
    },
    90_000,
  );

  test(
    "origin changed against the declared canonical is blocked destination-changed",
    async () => {
      const sb = makeSandbox();
      try {
        enroll(sb, { miseCanonical: path.join(sb.root, "other-origin.git") });
        expect(sb.miseRun(["dot", "save"]).code).toBe(0);
        const report = buildReport(sb);
        expect(report.mise!.outcome).toBe("blocked");
        expect(report.mise!.reason).toBe("destination-changed");
      } finally {
        sb.dispose();
      }
    },
    90_000,
  );

  test(
    "missing mise-history declaration is blocked destination-changed",
    async () => {
      const sb = makeSandbox();
      try {
        enroll(sb, { declareMise: false });
        expect(sb.miseRun(["dot", "save"]).code).toBe(0);
        const report = buildReport(sb);
        expect(report.mise!.outcome).toBe("blocked");
        expect(report.mise!.reason).toBe("destination-changed");
      } finally {
        sb.dispose();
      }
    },
    90_000,
  );

  test(
    "repeated events are idempotent",
    async () => {
      const sb = makeSandbox();
      try {
        expect(sb.miseRun(["dot", "save"]).code).toBe(0);
        expect(sb.miseRun(["dot", "sync"]).code).toBe(0);
        sb.truncateArgvLog();
        const first = buildReport(sb);
        sb.truncateArgvLog();
        const second = buildReport(sb);
        expect(first.mise!.outcome).toBe("verified");
        expect(second.mise!.outcome).toBe("verified");
        for (const line of sb.argvLogLines()) {
          expect(/^dot(files)? (pull|save|recover|bootstrap)/.test(line)).toBe(false);
        }
        const reportsDir = path.join(sb.agentState, "reports");
        expect(existsSync(reportsDir)).toBe(false); // reconcile itself writes no reports
      } finally {
        sb.dispose();
      }
    },
    90_000,
  );

  test(
    "mise absent omits the mise outcome entirely",
    async () => {
      const sb = makeSandbox();
      try {
        const envWithoutMise = { ...sb.env, PATH: "/usr/bin:/bin" };
        acp.__setDepsForTests({ env: envWithoutMise as Record<string, string | undefined> });
        const report = acp.buildTurnEndReport(sb.home);
        expect(report.mise).toBeUndefined();
      } finally {
        sb.dispose();
      }
    },
    30_000,
  );

  test("decision rules: precedence, conditions and the verified path (unit)", () => {
    const base = {
      mode: "sync",
      conflicts: [],
      lastError: null as string | null,
      failingSince: null as string | null,
      unsavedAutosave: [],
      unsavedManualSave: [],
      stamp: { present: true, ageMs: 1000 },
      manualSaveEveryMs: 86_400_000,
      pendingOperations: 0,
      pendingApplications: [],
      reconciliationQueued: false,
      declaredCanonical: "https://example.invalid/dotfiles.git",
      declaredDestinationPresent: true,
      liveOrigin: "https://example.invalid/dotfiles.git",
      originReachable: true,
    };
    // clean and clean-verified: not scheduled, verify required
    expect(acp.decideMiseOutcome(base)).toEqual({ outcome: "verify" });
    // blocked wins over pending and every blocked condition is listed
    const blocked = acp.decideMiseOutcome({
      ...base,
      mode: "fetch-only",
      unsavedAutosave: ["~/.dot-a"],
      pendingOperations: 3,
    });
    expect(blocked.outcome).toBe("blocked");
    if (blocked.outcome === "blocked") {
      expect(blocked.conditions.map((c) => c.reason)).toEqual(["fetch-only", "unsaved"]);
    }
    // pending without blocked
    const pending = acp.decideMiseOutcome({ ...base, pendingOperations: 1 });
    expect(pending).toEqual({ outcome: "pending", reason: "mise reports pending operations" });
    const queued = acp.decideMiseOutcome({ ...base, reconciliationQueued: true });
    expect(queued).toEqual({ outcome: "pending", reason: "reconciliation-queued" });
    // scheduled requires an unsaved manual-save path: no unsaved path is never scheduled
    const vacuous = acp.decideMiseOutcome(base);
    expect(vacuous.outcome).not.toBe("scheduled");
    const scheduled = acp.decideMiseOutcome({ ...base, unsavedManualSave: ["~/.gitconfig"] });
    expect(scheduled).toEqual({ outcome: "scheduled", paths: ["~/.gitconfig"] });
    // offline and failing conditions
    const offline = acp.decideMiseOutcome({ ...base, originReachable: false });
    expect(offline.outcome).toBe("blocked");
    if (offline.outcome === "blocked") expect(offline.conditions[0].reason).toBe("offline");
    const failing = acp.decideMiseOutcome({ ...base, lastError: "boom" });
    if (failing.outcome === "blocked") expect(failing.conditions[0].reason).toBe("failing");
    // conflict commands
    const conflict = acp.decideMiseOutcome({
      ...base,
      conflicts: [{ path: "~/.dot-a", reason: "both sides changed the same lines" }],
    });
    if (conflict.outcome === "blocked") {
      expect(conflict.conditions[0].commands).toContain("mise dot pull --take-remote ~/.dot-a");
    }
    // no declaration at all
    const undeclared = acp.decideMiseOutcome({ ...base, declaredCanonical: null, declaredDestinationPresent: false });
    if (undeclared.outcome === "blocked") expect(undeclared.conditions[0].reason).toBe("destination-changed");
  });

  test("verification rules: evidence, not exit codes (unit)", () => {
    const ok = {
      syncExit: 0,
      conflicts: false,
      pendingOperations: 0,
      lastError: null,
      localHead: "a".repeat(40),
      remoteHead: "a".repeat(40),
      originReachable: true,
    };
    expect(acp.verifyMiseOutcome(ok).outcome).toBe("verified");
    expect(acp.verifyMiseOutcome({ ...ok, localHead: "b".repeat(40) }).outcome).toBe("blocked");
    expect(acp.verifyMiseOutcome({ ...ok, remoteHead: null }).outcome).toBe("blocked");
    expect(acp.verifyMiseOutcome({ ...ok, localHead: null, remoteHead: null }).outcome).toBe("verified");
    expect(acp.verifyMiseOutcome({ ...ok, localHead: null }).outcome).toBe("blocked");
    expect(acp.verifyMiseOutcome({ ...ok, conflicts: true }).outcome).toBe("blocked");
    expect(acp.verifyMiseOutcome({ ...ok, pendingOperations: 2 }).outcome).toBe("pending");
    expect(acp.verifyMiseOutcome({ ...ok, originReachable: false }).outcome).toBe("blocked");
    expect(acp.verifyMiseOutcome({ ...ok, syncExit: null }).outcome).toBe("pending");
  });
});

describe("repository outcome (ZYS-9037 rebuild)", () => {
  test("ref grammar and namespace guards (unit)", () => {
    const sha = "0123456789abcdef0123456789abcdef01234567";
    const built = acp.buildCheckpointRef("dev-profile", "relay-zys-9038", "t0001", sha);
    expect(built).toEqual({
      ref: `refs/heads/agent-checkpoints/dev-profile/relay-zys-9038/t0001-${sha}`,
      short: `agent-checkpoints/dev-profile/relay-zys-9038/t0001-${sha}`,
    });
    expect(acp.refInOwnedNamespace((built as { ref: string }).ref)).toBe(true);
    expect(acp.refInOwnedNamespace("refs/heads/main")).toBe(false);
    expect("error" in acp.buildCheckpointRef("UPPER", "x", "t0001", sha)).toBe(true);
    expect("error" in acp.buildCheckpointRef("x", "y", "turn-1", sha)).toBe(true);
    expect("error" in acp.buildCheckpointRef("x", "y", "t0001", "short")).toBe(true);
    const longSlug = "a".repeat(220);
    expect("error" in acp.buildCheckpointRef(longSlug, "y", "t0001", sha)).toBe(true);
  });

  test("enrollment parsing (unit)", () => {
    const text = [
      "schema_version = 1",
      "",
      "[destinations.\"mise-history\"]",
      "kind = \"mise-dot\"",
      "canonical = \"https://example.invalid/d.git\"",
      "branch = \"history\"",
      "mode = \"fetch-only\"",
      "",
      "[repos.\"dev-profile\"]",
      "enabled = true",
      "path = \"~/Developer/Personal/dev-profile\"",
      "canonical = \"https://example.invalid/p.git\"",
      "visibility = \"private\"",
      "",
    ].join("\n");
    const parsed = acp.parseEnrollmentTOML(text)!;
    expect(parsed.schemaVersion).toBe(1);
    expect(parsed.destinations).toEqual([
      {
        name: "mise-history",
        kind: "mise-dot",
        canonical: "https://example.invalid/d.git",
        branch: "history",
        mode: "fetch-only",
      },
    ]);
    expect(parsed.repos).toEqual([
      {
        slug: "dev-profile",
        enabled: true,
        path: "~/Developer/Personal/dev-profile",
        canonical: "https://example.invalid/p.git",
        visibility: "private",
      },
    ]);
    expect(acp.parseEnrollmentTOML(text.replace("schema_version = 1", "schema_version = 2"))).toBeNull();
    expect(acp.parseEnrollmentTOML("this is not toml = = 1")).toBeNull();
    const disabled = acp.parseEnrollmentTOML(text.replace("enabled = true", "enabled = false"))!;
    expect(disabled.repos[0].enabled).toBe(false);
  });

  test("repository matching, including a worktree (F1)", () => {
    const main = makeGitRepo(path.join(suiteRoot, `repo-match-${Date.now()}`));
    const worktree = path.join(suiteRoot, `wt-match-${Date.now()}`);
    sh("git", ["-C", main, "worktree", "add", "-b", "topic", worktree], process.env);
    const common = acp.gitCommonDirOf(worktree)!;
    const enrollment = acp.parseEnrollmentTOML([
      "schema_version = 1",
      `[repos."a"]`,
      "enabled = true",
      `path = "${main}"`,
      "canonical = \"https://example.invalid/a.git\"",
      "",
      `[repos."b"]`,
      "enabled = true",
      `path = "${main}"`,
      "canonical = \"https://example.invalid/b.git\"",
      "",
    ].join("\n"))!;
    const match = acp.matchRepository(enrollment, common);
    expect(match.kind).toBe("ambiguous");
    const single = acp.parseEnrollmentTOML([
      "schema_version = 1",
      `[repos."a"]`,
      "enabled = true",
      `path = "${main}"`,
      "canonical = \"https://example.invalid/a.git\"",
      "",
    ].join("\n"))!;
    expect(acp.matchRepository(single, common)).toEqual({
      kind: "entry",
      entry: { slug: "a", enabled: true, path: main, canonical: "https://example.invalid/a.git" },
    });
    // entry pointing at the worktree resolves through its .git link to the common dir
    const viaWorktree = acp.parseEnrollmentTOML([
      "schema_version = 1",
      `[repos."w"]`,
      "enabled = true",
      `path = "${worktree}"`,
      "canonical = \"https://example.invalid/w.git\"",
      "",
    ].join("\n"))!;
    expect(acp.matchRepository(viaWorktree, common).kind).toBe("entry");
    // absent repository: not enrolled; disabled entry: not enrolled
    expect(acp.matchRepository(single, "/definitely/not/a/repo").kind).toBe("not-enrolled");
    const disabledEnrollment = acp.parseEnrollmentTOML([
      "schema_version = 1",
      `[repos."a"]`,
      "enabled = false",
      `path = "${main}"`,
      "canonical = \"https://example.invalid/a.git\"",
      "",
    ].join("\n"))!;
    expect(acp.matchRepository(disabledEnrollment, common).kind).toBe("not-enrolled");
    rmSync(worktree, { recursive: true, force: true });
  });

  test(
    "end to end: enrolled repository publishes through the spawned worker, hooks on, no remote-tracking ref (F2)",
    async () => {
      const sb = makeSandbox();
      const dest = path.join(sb.root, "dest.git");
      sh("git", ["init", "--bare", "-b", "main", dest], process.env);
      const repo = makeGitRepo(path.join(sb.root, "repo"));
      const sha = commitFile(repo, "work.txt", "turn work\n", "turn commit");
      // a pre-push hook that fires and records: hooks are on for the push (R3.1)
      const hookLog = path.join(sb.root, "pre-push.log");
      mkdirSync(path.join(repo, ".git", "hooks"), { recursive: true });
      writeFileSync(
        path.join(repo, ".git", "hooks", "pre-push"),
        `#!/usr/bin/env bash\nprintf 'fired\\n' >> "${hookLog}"\nexit 0\n`,
      );
      chmodSync(path.join(repo, ".git", "hooks", "pre-push"), 0o755);
      enroll(sb, { repos: [{ slug: "repo-a", path: repo, canonical: dest, visibility: "private" }] });
      const startedAt = Date.now();
      const report = buildReport(sb, repo, { spawnWorker: true });
      expect(report.repository!.outcome).toBe("pending");
      expect(Date.now() - startedAt).toBeLessThan(5000); // the handler enqueues and returns
      const key = report.repository!.jobKey!;
      const job = await waitUntil(
        () => {
          const record = acp.readJob(key);
          return record && (record.state === "verified" || record.state === "failed") ? record : undefined;
        },
        30_000,
        "worker verification",
      );
      expect(job.state).toBe("verified");
      expect(job.outcome).toBe("verified");
      const ref = report.repository!.ref!;
      expect(ref.startsWith("refs/heads/agent-checkpoints/repo-a/main/t0001-")).toBe(true);
      // success proved by ls-remote read-back only (R2.5): no refs/remotes write
      expect(lsRemoteOf(dest, ref).shas).toEqual([sha]);
      expect(readdirSync(path.join(repo, ".git", "refs", "remotes")).length).toBe(0);
      // the hook fired exactly once: hooks on, no skip flags, one push
      expect(readFileSync(hookLog, "utf8").trim()).toBe("fired");
      // idempotent: a rerun on verified reports verified-present, pushes nothing (R8.1)
      const again = buildReport(sb, repo);
      expect(again.repository!.outcome).toBe("verified-present");
      expect(readFileSync(hookLog, "utf8").trim()).toBe("fired");
      sb.dispose();
    },
    60_000,
  );

  test(
    "pushurl (F3) and pushInsteadOf (F4): push and read-back use the effective push URL",
    async () => {
      const sb = makeSandbox();
      const fetchDest = path.join(sb.root, "fetch.git");
      const pushDest = path.join(sb.root, "push.git");
      sh("git", ["init", "--bare", "-b", "main", fetchDest], process.env);
      sh("git", ["init", "--bare", "-b", "main", pushDest], process.env);
      const repo = makeGitRepo(path.join(sb.root, "repo"));
      commitFile(repo, "work.txt", "pushurl turn\n", "pushurl turn commit");
      sh("git", ["-C", repo, "remote", "add", "origin", fetchDest], process.env);
      sh("git", ["-C", repo, "remote", "set-url", "--push", "origin", pushDest], process.env);
      enroll(sb, { repos: [{ slug: "repo-b", path: repo, canonical: pushDest }] });
      const report = buildReport(sb, repo, { spawnWorker: true });
      const key = report.repository!.jobKey!;
      const job = await waitUntil(
        () => {
          const record = acp.readJob(key);
          return record && (record.state === "verified" || record.state === "failed") ? record : undefined;
        },
        30_000,
        "pushurl worker",
      );
      expect(job.state).toBe("verified");
      expect(lsRemoteOf(pushDest).shas.length).toBeGreaterThan(0);
      expect(lsRemoteOf(fetchDest).shas.length).toBe(0);
      sb.dispose();
    },
    60_000,
  );

  test(
    "pushInsteadOf rewrite: dry-run URL is used for push and read-back",
    async () => {
      const sb = makeSandbox();
      const dest = path.join(sb.root, "real.git");
      sh("git", ["init", "--bare", "-b", "main", dest], process.env);
      const repo = makeGitRepo(path.join(sb.root, "repo"));
      commitFile(repo, "work.txt", "insteadof turn\n", "insteadof turn commit");
      sh("git", ["-C", repo, "remote", "add", "origin", "https://rewrite.invalid/owner/repo.git"], process.env);
      sh(
        "git",
        ["-C", repo, "config", `url.${dest}.pushInsteadOf`, "https://rewrite.invalid/owner/repo.git"],
        process.env,
      );
      enroll(sb, { repos: [{ slug: "repo-c", path: repo, canonical: dest }] });
      const report = buildReport(sb, repo, { spawnWorker: true });
      const key = report.repository!.jobKey!;
      const job = await waitUntil(
        () => {
          const record = acp.readJob(key);
          return record && (record.state === "verified" || record.state === "failed") ? record : undefined;
        },
        30_000,
        "insteadOf worker",
      );
      expect(job.state).toBe("verified");
      expect(lsRemoteOf(dest).shas.length).toBeGreaterThan(0);
      sb.dispose();
    },
    60_000,
  );

  test("collision: same ref at a different SHA is blocked, never forced (F6)", async () => {
    const sb = makeSandbox();
    const dest = path.join(sb.root, "dest.git");
    sh("git", ["init", "--bare", "-b", "main", dest], process.env);
    const repo = makeGitRepo(path.join(sb.root, "repo"));
    const sha = commitFile(repo, "work.txt", "collision\n", "collision commit");
    enroll(sb, { repos: [{ slug: "repo-d", path: repo, canonical: dest }] });
    const report = buildReport(sb, repo, { spawnWorker: true });
    const key = report.repository!.jobKey!;
    await waitUntil(
      () => {
        const record = acp.readJob(key);
        return record?.state === "verified" ? record : undefined;
      },
      30_000,
      "first push",
    );
    // someone else moves the ref to a different SHA
    const other = makeGitRepo(path.join(sb.root, "other"));
    const otherSha = commitFile(other, "other.txt", "other\n", "other commit");
    sh("git", ["-C", other, "push", dest, `${otherSha}:${report.repository!.ref}`], process.env);
    // a fresh job for the same ref sees the collision
    const record = acp.readJob(key)!;
    const tampered = { ...record, state: "queued" as const, attempts: 0 };
    acp.writeJob(tampered);
    acp.__setDepsForTests({ env: sb.env as Record<string, string | undefined> });
    const outcome = acp.runCheckpointWorker(key);
    expect(outcome).toBe("blocked-collision");
    const finalJob = acp.readJob(key)!;
    expect(finalJob.state).toBe("failed");
    expect(finalJob.detail).toBe("different-sha");
    // the destination still holds the other SHA: never overwritten
    expect(lsRemoteOf(dest, report.repository!.ref!).shas).toEqual([otherSha]);
    sb.dispose();
  }, 60_000);

  test("D/F conflict with an existing ref is blocked (F7)", async () => {
    const sb = makeSandbox();
    const dest = path.join(sb.root, "dest.git");
    sh("git", ["init", "--bare", "-b", "main", dest], process.env);
    const repo = makeGitRepo(path.join(sb.root, "repo"));
    const sha = commitFile(repo, "work.txt", "df\n", "df commit");
    // an existing ref that is a directory prefix of the checkpoint ref
    const blocker = makeGitRepo(path.join(sb.root, "blocker"));
    const blockerSha = commitFile(blocker, "b.txt", "b\n", "blocker commit");
    sh("git", ["-C", blocker, "push", dest, `${blockerSha}:refs/heads/agent-checkpoints/repo-e/main`], process.env);
    enroll(sb, { repos: [{ slug: "repo-e", path: repo, canonical: dest }] });
    const report = buildReport(sb, repo);
    const key = report.repository!.jobKey!;
    acp.__setDepsForTests({ env: sb.env as Record<string, string | undefined> });
    const outcome = acp.runCheckpointWorker(key);
    expect(outcome).toBe("blocked-collision");
    expect(acp.readJob(key)!.detail).toBe("df-conflict");
    sb.dispose();
  }, 60_000);

  test("unsigned commit is blocked and never retried with signing disabled (F15)", async () => {
    const sb = makeSandbox();
    const dest = path.join(sb.root, "dest.git");
    sh("git", ["init", "--bare", "-b", "main", dest], process.env);
    const repo = makeGitRepo(path.join(sb.root, "repo"), { sign: false });
    commitFile(repo, "work.txt", "unsigned\n", "unsigned commit");
    enroll(sb, { repos: [{ slug: "repo-f", path: repo, canonical: dest }] });
    const report = buildReport(sb, repo);
    const key = report.repository!.jobKey!;
    acp.__setDepsForTests({ env: sb.env as Record<string, string | undefined> });
    const outcome = acp.runCheckpointWorker(key);
    expect(outcome).toBe("blocked-unsigned");
    const job = acp.readJob(key)!;
    expect(job.state).toBe("failed");
    expect(job.detail).toContain("not signed");
    expect(lsRemoteOf(dest).shas.length).toBe(0); // nothing was pushed
    sb.dispose();
  }, 60_000);

  test("a commit outside the recorded provenance is blocked (F11)", async () => {
    const sb = makeSandbox();
    const dest = path.join(sb.root, "dest.git");
    sh("git", ["init", "--bare", "-b", "main", dest], process.env);
    const repo = makeGitRepo(path.join(sb.root, "repo"));
    commitFile(repo, "work.txt", "prov\n", "provenance commit");
    enroll(sb, { repos: [{ slug: "repo-g", path: repo, canonical: dest }] });
    const report = buildReport(sb, repo);
    const key = report.repository!.jobKey!;
    // simulate a job recorded before the commit existed: provenance omits everything
    const job = acp.readJob(key)!;
    acp.writeJob({ ...job, provenance: [], provenanceTips: [] });
    acp.__setDepsForTests({ env: sb.env as Record<string, string | undefined> });
    const outcome = acp.runCheckpointWorker(key);
    expect(outcome).toBe("blocked-provenance");
    sb.dispose();
  }, 60_000);

  test("no advertised tip present locally is blocked-missing-baseline (F11)", async () => {
    const sb = makeSandbox();
    const dest = path.join(sb.root, "dest.git");
    sh("git", ["init", "--bare", "-b", "main", dest], process.env);
    const unrelated = makeGitRepo(path.join(sb.root, "unrelated"));
    const unrelatedSha = commitFile(unrelated, "u.txt", "u\n", "unrelated commit");
    sh("git", ["-C", unrelated, "push", dest, `${unrelatedSha}:refs/heads/main`], process.env);
    const repo = makeGitRepo(path.join(sb.root, "repo"));
    commitFile(repo, "work.txt", "baseline\n", "baseline commit");
    enroll(sb, { repos: [{ slug: "repo-h", path: repo, canonical: dest }] });
    const report = buildReport(sb, repo);
    const key = report.repository!.jobKey!;
    acp.__setDepsForTests({ env: sb.env as Record<string, string | undefined> });
    const outcome = acp.runCheckpointWorker(key);
    expect(outcome).toBe("blocked-missing-baseline");
    sb.dispose();
  }, 60_000);

  test("unrelated ancestry is blocked (F11)", async () => {
    const sb = makeSandbox();
    const dest = path.join(sb.root, "dest.git");
    sh("git", ["init", "--bare", "-b", "main", dest], process.env);
    const unrelated = makeGitRepo(path.join(sb.root, "unrelated"));
    const unrelatedSha = commitFile(unrelated, "u.txt", "u\n", "unrelated commit");
    sh("git", ["-C", unrelated, "push", dest, `${unrelatedSha}:refs/heads/main`], process.env);
    const repo = makeGitRepo(path.join(sb.root, "repo"));
    commitFile(repo, "work.txt", "orphan\n", "orphan commit");
    // the advertised tip is present locally via a fetch, but shares no ancestry
    sh("git", ["-C", repo, "fetch", dest, "refs/heads/main:refs/remotes/dest/main"], process.env);
    enroll(sb, { repos: [{ slug: "repo-i", path: repo, canonical: dest }] });
    const report = buildReport(sb, repo);
    const key = report.repository!.jobKey!;
    acp.__setDepsForTests({ env: sb.env as Record<string, string | undefined> });
    const outcome = acp.runCheckpointWorker(key);
    expect(outcome).toBe("blocked-unrelated-ancestry");
    sb.dispose();
  }, 60_000);

  test("hk pre-push rejection is blocked-hook-rejected with the section 9 report (F10)", async () => {
    const sb = makeSandbox();
    const dest = path.join(sb.root, "dest.git");
    sh("git", ["init", "--bare", "-b", "main", dest], process.env);
    const repo = makeGitRepo(path.join(sb.root, "repo"));
    commitFile(repo, "work.txt", "hook\n", "hook commit");
    mkdirSync(path.join(repo, ".git", "hooks"), { recursive: true });
    const hook = path.join(repo, ".git", "hooks", "pre-push");
    writeFileSync(
      hook,
      "#!/usr/bin/env bash\necho 'rejected by pre-push gate line 1'\nfor i in $(seq 1 40); do echo \"noise $i\"; done\nexit 1\n",
    );
    chmodSync(hook, 0o755);
    enroll(sb, { repos: [{ slug: "repo-j", path: repo, canonical: dest }] });
    const report = buildReport(sb, repo);
    const key = report.repository!.jobKey!;
    acp.__setDepsForTests({ env: sb.env as Record<string, string | undefined> });
    const outcome = acp.runCheckpointWorker(key);
    expect(outcome).toBe("blocked-hook-rejected");
    const job = acp.readJob(key)!;
    expect(job.state).toBe("failed"); // no retry on a hook rejection
    expect(job.detail).toContain("local work is intact");
    expect(job.hookOutput!.length).toBeLessThanOrEqual(20);
    expect(job.hookOutput!.some((line) => line.includes("pre-push"))).toBe(true);
    expect(lsRemoteOf(dest).shas.length).toBe(0);
    sb.dispose();
  }, 60_000);

  test("git invocations carry no skip flags, force flags or hook-disable env (F9)", async () => {
    const sb = makeSandbox();
    const dest = path.join(sb.root, "dest.git");
    sh("git", ["init", "--bare", "-b", "main", dest], process.env);
    const repo = makeGitRepo(path.join(sb.root, "repo"));
    commitFile(repo, "work.txt", "scan\n", "scan commit");
    enroll(sb, { repos: [{ slug: "repo-k", path: repo, canonical: dest }] });
    const report = buildReport(sb, repo);
    const key = report.repository!.jobKey!;
    const gitArgs: string[][] = [];
    acp.__setDepsForTests({
      env: sb.env as Record<string, string | undefined>,
      spawn: (cmd, args, opts) => {
        if (cmd === "git") gitArgs.push(args);
        const r = spawnSync(cmd, args, {
          cwd: opts?.cwd,
          env: sb.env as NodeJS.ProcessEnv,
          timeout: opts?.timeout,
          encoding: "utf8",
          maxBuffer: 16 * 1024 * 1024,
        });
        return { code: r.status, stdout: r.stdout ?? "", stderr: r.stderr ?? "", signal: r.signal };
      },
    });
    const outcome = acp.runCheckpointWorker(key);
    expect(outcome).toBe("verified");
    const flat = gitArgs.map((args) => args.join(" ")).join("\n");
    expect(flat).not.toContain("--no-verify");
    expect(flat).not.toContain("--force");
    expect(flat).not.toMatch(/\s-f\s/);
    expect(flat).not.toContain("--force-with-lease");
    for (const varName of acp.HOOK_DISABLE_ENV) {
      expect(sb.env[varName]).toBeUndefined();
    }
    sb.dispose();
  }, 60_000);

  test("willContinue and worker-env guards return without acting (F14)", async () => {
    const sb = makeSandbox();
    try {
      const registered: { event: string; handler: (event: unknown, ctx: acp.OmpContext) => unknown }[] = [];
      acp.default({ on: (event, handler) => registered.push({ event, handler }) });
      expect(registered.length).toBe(1);
      expect(registered[0].event).toBe("agent_end");
      acp.__setDepsForTests({ env: sb.env as Record<string, string | undefined> });
      registered[0].handler({ willContinue: true }, { cwd: sb.home });
      expect(existsSync(path.join(sb.agentState, "reports"))).toBe(false);
      // inside the worker: AGENT_CHECKPOINT_PUBLISH=1
      acp.__setDepsForTests({
        env: { ...sb.env, AGENT_CHECKPOINT_PUBLISH: "1" } as Record<string, string | undefined>,
      });
      registered[0].handler({ willContinue: false }, { cwd: sb.home });
      expect(existsSync(path.join(sb.agentState, "reports"))).toBe(false);
      // a real settle writes the report; history must be enabled for a mise outcome to exist
      expect(sb.miseRun(["dot", "save"]).code).toBe(0);
      acp.__setDepsForTests({ env: sb.env as Record<string, string | undefined> });
      const notifications: string[] = [];
      registered[0].handler({ willContinue: false }, {
        cwd: sb.home,
        hasUI: true,
        ui: { notify: (m) => notifications.push(m) },
      });
      const last = JSON.parse(readFileSync(path.join(sb.agentState, "reports", "last-report.json"), "utf8"));
      expect(last.schema).toBe(1);
      expect(notifications.join(" ")).toContain("mise:");
    } finally {
      sb.dispose();
    }
  }, 30_000);

  test("pending jobs report pending; past-TTL jobs report expired; three attempts fail (F13, F20)", async () => {
    const sb = makeSandbox();
    const dest = path.join(sb.root, "dest.git");
    const repo = makeGitRepo(path.join(sb.root, "repo"));
    commitFile(repo, "work.txt", "states\n", "states commit");
    enroll(sb, { repos: [{ slug: "repo-l", path: repo, canonical: dest }] });
    const sha = shOut("git", ["-C", repo, "rev-parse", "HEAD"], process.env);
    const ref = acp.buildCheckpointRef("repo-l", "main", "t0001", sha) as { ref: string };
    const key = acp.jobKey(repo, ref.ref, sha);
    const base = {
      key,
      repoCommonDir: repo,
      repoSlug: "repo-l",
      branchSlug: "main",
      ref: ref.ref,
      sha,
      canonical: dest,
      provenance: [sha],
      provenanceTips: [],
      turnId: "t0001",
      attempts: 0,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      heartbeatAt: new Date().toISOString(),
    };
    acp.__setDepsForTests({ env: sb.env as Record<string, string | undefined> });
    for (const state of ["queued", "pushing", "pushed"] as const) {
      acp.writeJob({ ...base, state });
      expect(acp.repositoryReport(repo, acp.parseEnrollmentTOML(readFileSync(sb.enrollmentPath, "utf8"))).outcome).toBe(
        "pending",
      );
    }
    // past the 24 h TTL: expired, reported not silently dropped (R5.3)
    acp.writeJob({ ...base, state: "queued", createdAt: new Date(Date.now() - 25 * 3600 * 1000).toISOString() });
    expect(acp.repositoryReport(repo, acp.parseEnrollmentTOML(readFileSync(sb.enrollmentPath, "utf8"))).outcome).toBe(
      "expired",
    );
    expect(acp.readJob(key)!.state).toBe("expired");
    // attempts exhausted: the worker fails without pushing
    acp.writeJob({ ...base, state: "queued", attempts: 3 });
    const outcome = acp.runCheckpointWorker(key);
    expect(outcome).toBe("blocked-timeout");
    expect(acp.readJob(key)!.state).toBe("failed");
    sb.dispose();
  }, 60_000);

  test("missing setsid or flock reports blocked-isolation-unavailable (ADR section 6)", async () => {
    const sb = makeSandbox();
    const dest = path.join(sb.root, "dest.git");
    const repo = makeGitRepo(path.join(sb.root, "repo"));
    commitFile(repo, "work.txt", "isolation\n", "isolation commit");
    enroll(sb, { repos: [{ slug: "repo-m", path: repo, canonical: dest }] });
    acp.__setDepsForTests({
      env: sb.env as Record<string, string | undefined>,
      which: (cmd) => (cmd === "setsid" ? undefined : "x"),
    });
    const report = acp.repositoryReport(repo, acp.parseEnrollmentTOML(readFileSync(sb.enrollmentPath, "utf8")));
    expect(report.outcome).toBe("blocked-isolation-unavailable");
    sb.dispose();
  }, 60_000);

  test("destination-changed when the effective push URL differs from canonical (R1.4)", async () => {
    const sb = makeSandbox();
    const dest = path.join(sb.root, "dest.git");
    const otherDest = path.join(sb.root, "other.git");
    sh("git", ["init", "--bare", "-b", "main", dest], process.env);
    sh("git", ["init", "--bare", "-b", "main", otherDest], process.env);
    const repo = makeGitRepo(path.join(sb.root, "repo"));
    commitFile(repo, "work.txt", "changed-dest\n", "changed dest commit");
    sh("git", ["-C", repo, "remote", "add", "origin", dest], process.env);
    // enrollment declares the wrong canonical: the real push URL is dest
    enroll(sb, { repos: [{ slug: "repo-n", path: repo, canonical: otherDest, remote: dest }] });
    const report = buildReport(sb, repo);
    const key = report.repository!.jobKey!;
    acp.__setDepsForTests({ env: sb.env as Record<string, string | undefined> });
    const outcome = acp.runCheckpointWorker(key);
    expect(outcome).toBe("blocked-destination-changed");
    expect(lsRemoteOf(dest).shas.length).toBe(0);
    sb.dispose();
  }, 60_000);
});
