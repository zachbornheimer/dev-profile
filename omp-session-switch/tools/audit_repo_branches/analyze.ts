import { basename } from "node:path";
import {
  discoverTicketRefsForEntry,
  evaluateTicketSync,
  extractTicketsFromText,
  rawTicketFromAtask,
  summarizeTicketDrift,
} from "./tickets.js";
import type {
  AnalyzedEntry,
  AtaskRawTask,
  AuditRepoBranchesOutput,
  AuditRepoPorts,
  BaseTouchingCommit,
  BranchVerdict,
  DirtyWorktreeStats,
  MissingLineSample,
  PullRequestInfo,
  RawTicketRecord,
  RepoAtaskSummary,
  ResidualStats,
  WorktreeInfo,
  WtItem,
} from "./types.js";

const NOISE_PATH_MARKERS = [
  ".terraform.lock.hcl",
  "node_modules/",
  ".DS_Store",
  "/dist/",
  "/bin/",
  "/.venv/",
  "__pycache__",
  ".ruff_cache/",
] as const;

const MIN_DISTINCTIVE_LINE_LEN = 12;
const MISSING_SAMPLE_LIMIT = 8;
const COMMIT_SUBJECT_LIMIT = 15;
const PATH_LIMIT = 40;
const SUPERSEDED_LANDED_RATIO = 0.85;
const SUPERSEDED_MAX_MISSING_LINES = 50;
const STALE_BEHIND_COMMITS = 20;
const STALE_PARTIAL_OVERLAP_RATIO = 0.25;

export function isNoisePath(path: string): boolean {
  return NOISE_PATH_MARKERS.some((marker) => path.includes(marker));
}

export function isDistinctiveLine(stripped: string): boolean {
  return stripped.length >= MIN_DISTINCTIVE_LINE_LEN && /[A-Za-z0-9]/.test(stripped);
}

export interface NumstatSummary {
  readonly files: number;
  readonly added: number;
  readonly removed: number;
  readonly paths: string[];
}

export function parseNumstat(text: string): NumstatSummary {
  let files = 0;
  let added = 0;
  let removed = 0;
  const paths: string[] = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    const parts = raw.split("\t");
    if (parts.length < 3) continue;
    const addNum = Number.parseInt(parts[0]!, 10);
    const remNum = Number.parseInt(parts[1]!, 10);
    const filePath = parts.slice(2).join("\t").trim();
    files++;
    if (Number.isFinite(addNum)) added += addNum;
    if (Number.isFinite(remNum)) removed += remNum;
    if (filePath) paths.push(filePath);
  }
  return { files, added, removed, paths };
}

export interface ParsedDiffLines {
  readonly addedByPath: Map<string, string[]>;
  readonly deletedByPath: Map<string, string[]>;
  readonly addedFiles: string[];
}

export function parseUnifiedDiff(diffText: string): ParsedDiffLines {
  const addedByPath = new Map<string, string[]>();
  const deletedByPath = new Map<string, string[]>();
  const addedFiles = new Set<string>();
  let addPath: string | null = null;
  let delPath: string | null = null;
  let prevWasDevNull = false;

  for (const line of diffText.split(/\r?\n/)) {
    if (line.startsWith("--- ")) {
      const target = line.slice(4).trim();
      prevWasDevNull = target === "/dev/null";
      delPath = prevWasDevNull || isNoisePath(target) ? null : target.replace(/^a\//, "");
      continue;
    }
    if (line.startsWith("+++ ")) {
      const target = line.slice(4).trim();
      addPath = target === "/dev/null" || isNoisePath(target) ? null : target.replace(/^b\//, "");
      if (prevWasDevNull && addPath) {
        addedFiles.add(addPath);
      }
      prevWasDevNull = false;
      continue;
    }
    if (line.startsWith("+") && !line.startsWith("+++") && addPath) {
      const stripped = line.slice(1).trim();
      if (isDistinctiveLine(stripped)) {
        const list = addedByPath.get(addPath) ?? [];
        list.push(stripped);
        addedByPath.set(addPath, list);
      }
    } else if (line.startsWith("-") && !line.startsWith("---") && delPath) {
      const stripped = line.slice(1).trim();
      if (isDistinctiveLine(stripped)) {
        const list = deletedByPath.get(delPath) ?? [];
        list.push(stripped);
        deletedByPath.set(delPath, list);
      }
    }
  }

  return { addedByPath, deletedByPath, addedFiles: [...addedFiles] };
}

export class BaseContentCache {
  private readonly existsCache = new Map<string, Promise<boolean>>();
  private readonly linesCache = new Map<string, Promise<ReadonlySet<string>>>();

  constructor(
    private readonly repoRoot: string,
    private readonly baseSha: string,
    private readonly ports: Pick<AuditRepoPorts, "gitRun">,
    private readonly signal?: AbortSignal,
  ) {}

  exists(path: string): Promise<boolean> {
    const existing = this.existsCache.get(path);
    if (existing) return existing;
    const promise = this.ports
      .gitRun(this.repoRoot, ["cat-file", "-e", `${this.baseSha}:${path}`], { signal: this.signal })
      .then((res) => res.code === 0);
    this.existsCache.set(path, promise);
    return promise;
  }

  strippedLines(path: string): Promise<ReadonlySet<string>> {
    const existing = this.linesCache.get(path);
    if (existing) return existing;
    const promise = this.ports
      .gitRun(this.repoRoot, ["show", `${this.baseSha}:${path}`], { signal: this.signal })
      .then((res) => {
        if (res.code !== 0) return new Set<string>();
        const set = new Set<string>();
        for (const line of res.stdout.split(/\r?\n/)) {
          const s = line.trim();
          if (s) set.add(s);
        }
        return set;
      });
    this.linesCache.set(path, promise);
    return promise;
  }
}

async function measureAddedLinePresence(
  addedByPath: ReadonlyMap<string, readonly string[]>,
  cache: BaseContentCache,
): Promise<{
  considered: number;
  present: number;
  missing: MissingLineSample[];
}> {
  let considered = 0;
  let present = 0;
  const missing: MissingLineSample[] = [];

  let pathsChecked = 0;
  for (const [path, lines] of addedByPath.entries()) {
    if (pathsChecked++ >= PATH_LIMIT) break;
    const inBase = await cache.exists(path);
    const baseLines = inBase ? await cache.strippedLines(path) : new Set<string>();
    for (const stripped of lines) {
      considered++;
      if (baseLines.has(stripped)) {
        present++;
      } else if (missing.length < MISSING_SAMPLE_LIMIT) {
        missing.push({ path, line: stripped });
      }
    }
  }

  return { considered, present, missing };
}

async function measureDeletedLinePresence(
  deletedByPath: ReadonlyMap<string, readonly string[]>,
  cache: BaseContentCache,
): Promise<{
  considered: number;
  present: number;
  missing: MissingLineSample[];
}> {
  let considered = 0;
  let present = 0;
  const missing: MissingLineSample[] = [];

  let pathsChecked = 0;
  for (const [path, lines] of deletedByPath.entries()) {
    if (pathsChecked++ >= PATH_LIMIT) break;
    const inBase = await cache.exists(path);
    if (!inBase) {
      considered += lines.length;
      present += lines.length;
      continue;
    }
    const baseLines = await cache.strippedLines(path);
    for (const stripped of lines) {
      considered++;
      if (!baseLines.has(stripped)) {
        present++;
      } else if (missing.length < MISSING_SAMPLE_LIMIT) {
        missing.push({ path, line: stripped });
      }
    }
  }

  return { considered, present, missing };
}

export async function measureDirtyWorktree(
  repoRoot: string,
  worktreePath: string,
  cache: BaseContentCache,
  ports: Pick<AuditRepoPorts, "gitRun" | "readWorktreeFile">,
  signal?: AbortSignal,
  headSha?: string,
  baseSha?: string,
): Promise<DirtyWorktreeStats> {
  const [numstatRes, diffRes, statusRes] = await Promise.all([
    ports.gitRun(repoRoot, ["diff", "HEAD", "--numstat"], { cwd: worktreePath, signal }),
    ports.gitRun(repoRoot, ["diff", "HEAD"], { cwd: worktreePath, signal }),
    ports.gitRun(repoRoot, ["status", "--porcelain"], { cwd: worktreePath, signal }),
  ]);

  const numstat = parseNumstat(numstatRes.stdout);
  const parsedDiff = parseUnifiedDiff(diffRes.stdout);

  const trackedNonNoise = numstat.paths.filter((p) => !isNoisePath(p)).slice(0, PATH_LIMIT);
  let baseOverlappingPaths: string[] = [];
  if (headSha && baseSha && headSha !== baseSha && trackedNonNoise.length > 0) {
    const overlapRes = await ports.gitRun(
      repoRoot,
      ["diff", "--name-only", `${headSha}..${baseSha}`, "--", ...trackedNonNoise],
      { signal },
    );
    if (overlapRes.code === 0 && overlapRes.stdout.trim()) {
      baseOverlappingPaths = overlapRes.stdout
        .split(/\r?\n/)
        .map((l) => l.trim())
        .filter(Boolean);
    }
  }

  const untrackedPaths: string[] = [];
  for (const raw of statusRes.stdout.split(/\r?\n/)) {
    if (raw.startsWith("?? ")) {
      const p = raw.slice(3).trim();
      if (p) untrackedPaths.push(p);
    }
  }

  // Also sample distinctive lines from untracked files (excluding directories and noise paths).
  const combinedAdded = new Map<string, string[]>(parsedDiff.addedByPath);
  let untrackedAddedLines = 0;
  for (const untracked of untrackedPaths) {
    if (isNoisePath(untracked) || untracked.endsWith("/")) continue;
    const content = await ports.readWorktreeFile(worktreePath, untracked);
    if (!content) continue;
    const lines: string[] = [];
    for (const rawLine of content.split(/\r?\n/)) {
      untrackedAddedLines++;
      const stripped = rawLine.trim();
      if (isDistinctiveLine(stripped)) lines.push(stripped);
    }
    if (lines.length > 0) {
      combinedAdded.set(untracked, lines);
    }
  }

  const allPaths = [...numstat.paths, ...untrackedPaths];
  const realPaths = allPaths.filter((p) => !isNoisePath(p)).slice(0, PATH_LIMIT);
  const noisePaths = allPaths.filter((p) => isNoisePath(p)).slice(0, PATH_LIMIT);

  let considered = 0;
  let present = 0;
  let missing: MissingLineSample[] = [];
  if (combinedAdded.size > 0) {
    const res = await measureAddedLinePresence(combinedAdded, cache);
    considered = res.considered;
    present = res.present;
    missing = res.missing;
  } else if (parsedDiff.deletedByPath.size > 0) {
    const res = await measureDeletedLinePresence(parsedDiff.deletedByPath, cache);
    considered = res.considered;
    present = res.present;
    missing = res.missing;
  }

  return {
    tracked_files: numstat.files,
    untracked_files: untrackedPaths.length,
    lines_added: numstat.added + untrackedAddedLines,
    lines_removed: numstat.removed,
    real_paths: realPaths,
    noise_paths: noisePaths,
    base_overlapping_paths: baseOverlappingPaths,
    lines_considered: considered,
    lines_missing_from_base: considered - present,
    landed_ratio: considered > 0 ? Number((present / considered).toFixed(4)) : null,
    missing_sample: missing,
  };
}

export async function measureBranchResidual(
  repoRoot: string,
  baseSha: string,
  branchSha: string,
  wtMergeConflicts: boolean | null | undefined,
  cache: BaseContentCache,
  ports: Pick<AuditRepoPorts, "gitRun">,
  signal?: AbortSignal,
): Promise<ResidualStats> {
  const mbRes = await ports.gitRun(repoRoot, ["merge-base", baseSha, branchSha], { signal });
  const mergeBase = mbRes.code === 0 && mbRes.stdout.trim() ? mbRes.stdout.trim() : baseSha;

  const mtRes = await ports.gitRun(
    repoRoot,
    ["merge-tree", "--write-tree", "--name-only", baseSha, branchSha],
    { signal },
  );
  const mergeConflicts = wtMergeConflicts ?? mtRes.code !== 0;
  const conflictedPaths: string[] = [];
  if (mtRes.code === 1) {
    const firstBlock = mtRes.stdout.split("\n\n")[0] ?? "";
    for (const line of firstBlock.split(/\r?\n/).slice(1)) {
      const p = line.trim();
      if (p && !/^[0-9a-f]{40}$/i.test(p)) conflictedPaths.push(p);
    }
  }

  const [numstatRes, diffRes] = await Promise.all([
    ports.gitRun(repoRoot, ["diff", "--numstat", mergeBase, branchSha], { signal }),
    ports.gitRun(repoRoot, ["diff", mergeBase, branchSha], { signal }),
  ]);

  const numstat = parseNumstat(numstatRes.stdout);
  const parsedDiff = parseUnifiedDiff(diffRes.stdout);

  let considered = 0;
  let present = 0;
  let missing: MissingLineSample[] = [];
  if (parsedDiff.addedByPath.size > 0) {
    const res = await measureAddedLinePresence(parsedDiff.addedByPath, cache);
    considered = res.considered;
    present = res.present;
    missing = res.missing;
  } else if (parsedDiff.deletedByPath.size > 0) {
    const res = await measureDeletedLinePresence(parsedDiff.deletedByPath, cache);
    considered = res.considered;
    present = res.present;
    missing = res.missing;
  }

  const unlandedNewFiles: string[] = [];
  for (const addedFile of parsedDiff.addedFiles.slice(0, PATH_LIMIT)) {
    const inBase = await cache.exists(addedFile);
    if (!inBase) unlandedNewFiles.push(addedFile);
  }

  // Find commits on base (mergeBase..baseSha) that modified the same non-noise paths.
  const queryPaths = numstat.paths.filter((p) => !isNoisePath(p)).slice(0, 20);
  const baseTouchingCommits: BaseTouchingCommit[] = [];
  if (queryPaths.length > 0 && mergeBase !== baseSha) {
    const logRes = await ports.gitRun(
      repoRoot,
      ["log", "--oneline", "--no-merges", "-n", "12", `${mergeBase}..${baseSha}`, "--", ...queryPaths],
      { signal },
    );
    if (logRes.code === 0 && logRes.stdout.trim()) {
      for (const rawLine of logRes.stdout.split(/\r?\n/)) {
        const line = rawLine.trim();
        if (!line) continue;
        const spaceIdx = line.indexOf(" ");
        const sha = spaceIdx > 0 ? line.slice(0, spaceIdx) : line;
        const subject = spaceIdx > 0 ? line.slice(spaceIdx + 1).trim() : "";
        const extracted = extractTicketsFromText(subject);
        baseTouchingCommits.push({
          sha,
          subject,
          tickets: [...extracted.linear, ...extracted.atask],
        });
      }
    }
  }

  return {
    files_changed: numstat.files,
    lines_added: numstat.added,
    lines_removed: numstat.removed,
    merge_conflicts: mergeConflicts,
    conflicted_paths: conflictedPaths,
    lines_considered: considered,
    lines_missing_from_base: considered - present,
    landed_ratio: considered > 0 ? Number((present / considered).toFixed(4)) : null,
    unlanded_new_files: unlandedNewFiles,
    base_touching_commits: baseTouchingCommits,
    missing_sample: missing,
  };
}

async function checkDeterministicIntegration(
  repoRoot: string,
  baseSha: string,
  branchSha: string,
  wtIntegrationReason: string | null | undefined,
  ports: Pick<AuditRepoPorts, "gitRun">,
  signal?: AbortSignal,
  aheadCount?: number,
): Promise<string | null> {
  if (wtIntegrationReason === "ancestor" || wtIntegrationReason === "same_commit") {
    return `already integrated into default branch (${wtIntegrationReason})`;
  }
  if (wtIntegrationReason === "merge_adds_nothing") {
    return "squash-merged or tree-equivalent in default branch (merge_adds_nothing)";
  }

  const anc = await ports.gitRun(repoRoot, ["merge-base", "--is-ancestor", branchSha, baseSha], { signal });
  if (anc.code === 0) {
    return "commit is an ancestor of the default branch";
  }

  const mt = await ports.gitRun(repoRoot, ["merge-tree", "--write-tree", baseSha, branchSha], { signal });
  if (mt.code === 0) {
    const treeOid = mt.stdout.trim().split(/\s+/)[0] ?? "";
    const baseTree = await ports.gitRun(repoRoot, ["rev-parse", `${baseSha}^{tree}`], { signal });
    if (treeOid && baseTree.code === 0 && treeOid === baseTree.stdout.trim()) {
      return "merging into the default branch changes nothing (squash-landed)";
    }
  }

  if (aheadCount === undefined || aheadCount <= 30) {
    const cherry = await ports.gitRun(repoRoot, ["cherry", baseSha, branchSha], { signal });
    if (cherry.code === 0 && cherry.stdout.trim()) {
      const lines = cherry.stdout.trim().split(/\r?\n/);
      if (lines.length > 0 && lines.every((l) => l.startsWith("-"))) {
        return "every commit is patch-equivalent in the default branch (git cherry)";
      }
    }
  }

  return null;
}

function isWipOrSnapshotBranch(branch: string | null, subject: string | null): boolean {
  const b = (branch ?? "").toLowerCase();
  const s = (subject ?? "").toLowerCase();
  return (
    b === "wip"
    || b.startsWith("wip/")
    || b.startsWith("wip-")
    || b.startsWith("backup/")
    || b.startsWith("tmp/")
    || b.startsWith("scratch/")
    || b.includes("snapshot")
    || s.startsWith("wip(")
    || s.startsWith("wip:")
    || s.includes("snapshot of dirty worktree")
  );
}

export function hasRealUnlandedDirtyWork(dirty: DirtyWorktreeStats | null): boolean {
  if (!dirty || dirty.real_paths.length === 0) return false;
  if (
    dirty.lines_considered > 0
    && dirty.landed_ratio !== null
    && dirty.landed_ratio >= SUPERSEDED_LANDED_RATIO
    && dirty.lines_missing_from_base <= 20
  ) {
    return false;
  }
  return dirty.lines_added + dirty.lines_removed > 0 || dirty.untracked_files > 0;
}

export function classifyEntryVerdict(input: {
  branch: string | null;
  defaultBranch: string;
  ahead: number;
  behind: number;
  subject: string | null;
  worktree: WorktreeInfo | null;
  pr: PullRequestInfo | null;
  integrationEvidence: string | null;
  duplicateOf: string | null;
  residual: ResidualStats | null;
  rawTickets: readonly RawTicketRecord[];
  remoteOnly?: boolean;
}): { verdict: BranchVerdict; reason: string; recommended_action: string } {
  const {
    branch,
    defaultBranch,
    ahead,
    behind,
    subject,
    worktree,
    pr,
    integrationEvidence,
    duplicateOf,
    residual,
    rawTickets,
    remoteOnly,
  } = input;
  const pruneBranchCmd = (b: string | null, force = false): string => {
    if (!b) return "wt step prune --foreground --yes";
    if (remoteOnly) return `git push origin --delete ${b}`;
    return force ? `wt remove --foreground -D --yes ${b}` : `wt remove --foreground --yes ${b}`;
  };

  // 1. Default branch itself.
  if (branch === defaultBranch) {
    if (worktree && hasRealUnlandedDirtyWork(worktree.dirty)) {
      return {
        verdict: "protected",
        reason: `default branch (${defaultBranch}) with working-tree edits (+${worktree.dirty!.lines_added}/-${worktree.dirty!.lines_removed} across ${worktree.dirty!.real_paths.length} path(s))`,
        recommended_action: `move working-tree edits out of ${defaultBranch} into a wt worktree (wt tree-for-changes <slug>)`,
      };
    }
    return {
      verdict: "protected",
      reason: `default branch (${defaultBranch})`,
      recommended_action: "keep",
    };
  }

  // 2. Missing or unreadable worktrees.
  if (worktree && (worktree.state === "missing" || worktree.state === "unknown")) {
    return {
      verdict: "unsure",
      reason: `worktree at ${worktree.path} is ${worktree.state}; safety checks cannot confirm cleanliness`,
      recommended_action: `inspect ${worktree.path} before pruning`,
    };
  }
  if (worktree?.state === "prunable") {
    if (integrationEvidence || ahead === 0) {
      return {
        verdict: "completed_or_redundant",
        reason: `prunable detached worktree (${worktree.prunable_reason ?? "missing gitdir target"}) whose HEAD is already in ${defaultBranch}`,
        recommended_action: "wt step prune --foreground --yes",
      };
    }
    return {
      verdict: "unsure",
      reason: `prunable worktree at ${worktree.path} points at unmerged commit (${ahead} ahead of ${defaultBranch})`,
      recommended_action: `verify commit ${input.branch ?? worktree.path} before running wt step prune --foreground --yes`,
    };
  }

  const canceledOrSupersededTicket = rawTickets.find(
    (t) => t.lookup_status === "found" && (t.status_type === "canceled" || t.superseded_by.length > 0),
  );

  // 3. Worktree has real working-tree edits whose content is not on the default branch.
  if (worktree && hasRealUnlandedDirtyWork(worktree.dirty)) {
    const dirty = worktree.dirty!;
    if (canceledOrSupersededTicket) {
      const by = canceledOrSupersededTicket.superseded_by.length > 0
        ? `superseded by ${canceledOrSupersededTicket.superseded_by.join(", ")}`
        : `marked ${canceledOrSupersededTicket.status ?? "Canceled"}`;
      return {
        verdict: "superseded",
        reason: `worktree has working-tree edits (+${dirty.lines_added}/-${dirty.lines_removed}), but linked ticket ${canceledOrSupersededTicket.id} is ${by}`,
        recommended_action: `archive or discard superseded dirty worktree at ${worktree.path} after preserving a backup`,
      };
    }
    const overlapPaths = dirty.base_overlapping_paths ?? [];
    const overlapNote = overlapPaths.length > 0
      ? `; ${overlapPaths.length} modified file(s) also changed on ${defaultBranch} across ${behind} newer commit(s) (${overlapPaths.slice(0, 5).join(", ")}${overlapPaths.length > 5 ? ", ..." : ""})`
      : "";
    const baseNote = integrationEvidence
      ? `committed HEAD is integrated into ${defaultBranch}, but worktree has unlanded working-tree edits`
      : `branch is ${ahead} commit(s) ahead and worktree has unlanded working-tree edits`;
    const action = overlapPaths.length > 0
      ? `reconcile ${overlapPaths.length} base-overlapping file(s) (${overlapPaths.slice(0, 4).join(", ")}${overlapPaths.length > 4 ? ", ..." : ""}) against ${defaultBranch} in ${worktree.path} and land via PR`
      : `package working-tree edits in ${worktree.path}, rebase onto ${defaultBranch}, and open a PR`;
    return {
      verdict: "should_land",
      reason: `${baseNote} (+${dirty.lines_added}/-${dirty.lines_removed} across ${dirty.tracked_files} tracked and ${dirty.untracked_files} untracked file(s)${overlapNote})`,
      recommended_action: action,
    };
  }

  // 4. Dirty worktree whose edits ARE already on the default branch (or noise-only).
  const dirtyAlreadyInBase = Boolean(
    worktree?.state === "dirty"
      && worktree.dirty
      && !hasRealUnlandedDirtyWork(worktree.dirty),
  );

  // 5. Open PR on this branch.
  if (pr?.state === "OPEN") {
    if (canceledOrSupersededTicket) {
      return {
        verdict: "superseded",
        reason: `open PR #${pr.number} (${pr.url}) belongs to ticket ${canceledOrSupersededTicket.id} (${canceledOrSupersededTicket.status ?? "superseded"})`,
        recommended_action: `close open PR #${pr.number} and remove branch ${branch}`,
      };
    }
    if (integrationEvidence) {
      return {
        verdict: "completed_or_redundant",
        reason: `open PR #${pr.number} (${pr.url}) is already integrated in ${defaultBranch}: ${integrationEvidence}`,
        recommended_action: `close redundant PR #${pr.number} and prune ${branch ?? "worktree"}`,
      };
    }
    return {
      verdict: "should_land",
      reason: `active open PR #${pr.number} (${pr.url}), ${ahead} commit(s) ahead of ${defaultBranch}`,
      recommended_action: `land PR #${pr.number} (${pr.url}) via make_pr_mergable`,
    };
  }

  // 6. Deterministically integrated into the default branch (ancestor, cherry-equivalent, merge-tree-equivalent, merged PR, or 100% line presence).
  if (integrationEvidence) {
    const prNote = pr?.state === "MERGED" ? ` via merged PR #${pr.number}` : "";
    const dirtyNote = dirtyAlreadyInBase ? " (dirty worktree files contain only noise or lines already on base)" : "";
    const action = worktree
      ? branch
        ? `wt remove --foreground --yes ${branch}`
        : `wt remove --foreground --no-delete-branch --yes ${worktree.path}`
      : pruneBranchCmd(branch, false);
    return {
      verdict: "completed_or_redundant",
      reason: `${integrationEvidence}${prNote}${dirtyNote}`,
      recommended_action: action,
    };
  }

  if (pr?.state === "MERGED") {
    const action = branch ? pruneBranchCmd(branch, true) : "wt step prune --foreground --yes";
    return {
      verdict: "completed_or_redundant",
      reason: `PR #${pr.number} (${pr.url}) merged into ${defaultBranch}`,
      recommended_action: action,
    };
  }

  if (duplicateOf) {
    return {
      verdict: "completed_or_redundant",
      reason: `duplicate branch pointing at the exact same commit as ${duplicateOf}`,
      recommended_action: pruneBranchCmd(branch, true),
    };
  }

  if (residual && residual.lines_considered > 0 && residual.lines_missing_from_base === 0) {
    return {
      verdict: "completed_or_redundant",
      reason: `all ${residual.lines_considered} distinctive added/deleted line(s) are already present in ${defaultBranch}`,
      recommended_action: pruneBranchCmd(branch, true),
    };
  }

  // 7. Unintegrated commits: distinguish superseded vs should_land.
  if (canceledOrSupersededTicket) {
    const by = canceledOrSupersededTicket.superseded_by.length > 0
      ? `superseded by ${canceledOrSupersededTicket.superseded_by.join(", ")}`
      : `marked ${canceledOrSupersededTicket.status ?? "Canceled"}`;
    return {
      verdict: "superseded",
      reason: `linked ticket ${canceledOrSupersededTicket.id} is ${by}`,
      recommended_action: `remove superseded branch ${branch} after confirming no salvageable code remains`,
    };
  }

  if (
    residual
    && residual.landed_ratio !== null
    && residual.landed_ratio >= SUPERSEDED_LANDED_RATIO
    && residual.lines_missing_from_base <= SUPERSEDED_MAX_MISSING_LINES
  ) {
    const pct = Math.round(residual.landed_ratio * 100);
    return {
      verdict: "superseded",
      reason: `${pct}% of distinctive lines (${residual.lines_considered - residual.lines_missing_from_base}/${residual.lines_considered}) already landed in ${defaultBranch}; only ${residual.lines_missing_from_base} line(s) differ`,
      recommended_action: `prune superseded branch ${branch} (${pruneBranchCmd(branch, true)})`,
    };
  }

  if (
    residual
    && residual.merge_conflicts
    && behind >= STALE_BEHIND_COMMITS
    && residual.base_touching_commits.length > 0
    && (isWipOrSnapshotBranch(branch, subject)
      || (residual.landed_ratio !== null && residual.landed_ratio >= STALE_PARTIAL_OVERLAP_RATIO))
  ) {
    const baseTickets = [...new Set(residual.base_touching_commits.flatMap((c) => c.tickets))];
    const ticketClause = baseTickets.length > 0 ? ` (including ${baseTickets.join(", ")})` : "";
    const pct = residual.landed_ratio !== null ? `${Math.round(residual.landed_ratio * 100)}% line overlap, ` : "";
    const newFilesClause = residual.unlanded_new_files.length > 0
      ? `; standalone unmerged files to review before deleting: ${residual.unlanded_new_files.slice(0, 6).join(", ")}`
      : "";
    return {
      verdict: "superseded",
      reason: `stale conflicting branch (${behind} commits behind ${defaultBranch}, ${pct}conflicts on ${residual.conflicted_paths.length || "multiple"} path(s)) overtaken by ${residual.base_touching_commits.length} newer commit(s) on ${defaultBranch}${ticketClause}${newFilesClause}`,
      recommended_action: residual.unlanded_new_files.length > 0
        ? `inspect standalone files (${residual.unlanded_new_files.slice(0, 4).join(", ")}) for anything still needed, then remove ${branch}`
        : `remove superseded branch ${branch} (${pruneBranchCmd(branch, true)})`,
    };
  }

  if (pr?.state === "CLOSED") {
    return {
      verdict: "superseded",
      reason: `PR #${pr.number} (${pr.url}) was closed without merging`,
      recommended_action: `remove closed-PR branch ${branch} or reopen if still needed`,
    };
  }

  if (ahead > 0) {
    const conflictNote = residual?.merge_conflicts
      ? ` (has merge conflicts with ${defaultBranch} on ${residual.conflicted_paths.length || "touched"} path(s))`
      : " (merges cleanly)";
    const diffNote = residual ? `, +${residual.lines_added}/-${residual.lines_removed} across ${residual.files_changed} file(s)` : "";
    return {
      verdict: "should_land",
      reason: `${ahead} unmerged commit(s) ahead of ${defaultBranch}${diffNote}${conflictNote}`,
      recommended_action: `rebase ${branch ?? "HEAD"} onto ${defaultBranch}, run verification, and open/land a PR`,
    };
  }

  return {
    verdict: "unsure",
    reason: "insufficient evidence to classify branch or worktree safely",
    recommended_action: `inspect ${branch ?? worktree?.path ?? "entry"} manually`,
  };
}

export async function runAuditRepoBranches(
  input: { repo: string; fetch?: boolean; check_linear?: boolean; include_remote?: boolean; base_ref?: string },
  ports: AuditRepoPorts,
  signal?: AbortSignal,
): Promise<AuditRepoBranchesOutput> {
  if (!input.repo || input.repo.trim() === "") {
    throw new Error("audit_repo_branches: repo is required");
  }
  const repoRoot = await ports.resolveRepoRoot(input.repo.trim(), signal);
  const fetchResult = input.fetch === false
    ? { status: "skipped" as const, detail: "fetch disabled by caller" }
    : await ports.fetchPrune(repoRoot, signal);

  const [wtEnvelope, prList, ataskTasks, refsRes] = await Promise.all([
    ports.listWtItems(repoRoot, signal),
    ports.listPullRequests(repoRoot, signal),
    ports.listAtaskTasks(signal),
    ports.gitRun(
      repoRoot,
      [
        "for-each-ref",
        "refs/heads",
        ...(input.include_remote === false ? [] : ["refs/remotes/origin"]),
        "--format=%(refname:short)%09%(objectname)%09%(upstream:short)%09%(upstream:track)%09%(committerdate:iso-strict)%09%(subject)%09%(refname)",
      ],
      { signal },
    ),
  ]);

  let baseInfo = await ports.resolveBase(repoRoot, wtEnvelope.repo?.default_branch, signal);
  if (input.base_ref && input.base_ref.trim()) {
    const customRef = input.base_ref.trim();
    const ver = await ports.gitRun(repoRoot, ["rev-parse", "--verify", customRef], { signal });
    if (ver.code === 0 && ver.stdout.trim()) {
      const defaultBranch = customRef.startsWith("origin/") ? customRef.slice("origin/".length) : customRef;
      baseInfo = { defaultBranch, baseRef: customRef, baseSha: ver.stdout.trim() };
    }
  }
  const { defaultBranch, baseRef, baseSha } = baseInfo;
  const forge = wtEnvelope.repo?.forge;
  const forgeSlug = forge?.owner && forge?.name ? `${forge.owner}/${forge.name}` : null;

  // Map git for-each-ref metadata by branch name so upstream [gone], any local branch omitted by wt, and remote-only origin/* branches are captured.
  const refMetaByBranch = new Map<
    string,
    {
      sha: string;
      upstream: string | null;
      gone: boolean;
      committedAt: string | null;
      subject: string | null;
      remoteOnly: boolean;
    }
  >();
  if (refsRes.code === 0) {
    for (const rawLine of refsRes.stdout.split(/\r?\n/)) {
      if (!rawLine.trim()) continue;
      const [name, sha, upstream, track, date, subject, fullRef] = rawLine.split("\t");
      if (!name || !sha) continue;
      const isRemoteRef = Boolean(
        (fullRef && fullRef.startsWith("refs/remotes/origin/"))
          || (!fullRef && name.startsWith("origin/")),
      );
      if (isRemoteRef) {
        if (input.include_remote === false) continue;
        if (name === "origin" || name === "origin/HEAD" || fullRef === "refs/remotes/origin/HEAD") continue;
        const branchName = name.startsWith("origin/") ? name.slice("origin/".length) : name;
        if (!branchName || refMetaByBranch.has(branchName)) continue;
        refMetaByBranch.set(branchName, {
          sha,
          upstream: `origin/${branchName}`,
          gone: false,
          committedAt: date || null,
          subject: subject || null,
          remoteOnly: true,
        });
      } else {
        refMetaByBranch.set(name, {
          sha,
          upstream: upstream || null,
          gone: Boolean(track && track.includes("gone")),
          committedAt: date || null,
          subject: subject || null,
          remoteOnly: false,
        });
      }
    }
  }

  // Ensure every local branch in refs/heads is represented in items even if wt list omitted it.
  const items: WtItem[] = [...wtEnvelope.items];
  const seenBranches = new Set<string>(items.map((i) => i.branch).filter((b): b is string => Boolean(b)));
  for (const [branchName, meta] of refMetaByBranch.entries()) {
    if (!seenBranches.has(branchName)) {
      items.push({
        branch: branchName,
        head: {
          sha: meta.sha,
          short_sha: meta.sha.slice(0, 7),
          subject: meta.subject,
          committed_at: meta.committedAt,
        },
      });
    }
  }

  // Index PRs by headRefName and by PR number.
  const prsByHead = new Map<string, PullRequestInfo[]>();
  const prsByNumber = new Map<number, PullRequestInfo>();
  for (const pr of prList.prs) {
    prsByNumber.set(pr.number, pr);
    if (pr.head_ref) {
      const list = prsByHead.get(pr.head_ref) ?? [];
      list.push(pr);
      prsByHead.set(pr.head_ref, list);
    }
  }

  const ataskById = new Map<string, AtaskRawTask>();
  for (const task of ataskTasks) {
    ataskById.set(task.id.toLowerCase(), task);
  }

  // First pass: determine ahead/behind, integration evidence, and matched PR for each item.
  const cache = new BaseContentCache(repoRoot, baseSha, ports, signal);

  interface PreItem {
    item: WtItem;
    id: string;
    branch: string | null;
    sha: string;
    shortSha: string;
    subject: string | null;
    committedAt: string | null;
    upstream: string | null;
    upstreamGone: boolean;
    ahead: number;
    behind: number;
    commitSubjects: string[];
    matchedPr: PullRequestInfo | null;
    integrationEvidence: string | null;
    worktree: WorktreeInfo | null;
  }

  const preItems: PreItem[] = [];
  for (const item of items) {
    if (!item.head?.sha) continue;
    const branch = item.branch ?? null;
    const sha = item.head.sha;
    const shortSha = item.head.short_sha ?? sha.slice(0, 7);
    const refMeta = branch ? refMetaByBranch.get(branch) : undefined;
    const subject = item.head.subject ?? refMeta?.subject ?? null;
    const committedAt = item.head.committed_at ?? refMeta?.committedAt ?? null;
    const upstream = refMeta?.upstream
      ?? (item.upstream?.remote && item.upstream?.branch ? `${item.upstream.remote}/${item.upstream.branch}` : null);
    const upstreamGone = refMeta?.gone ?? false;

    let ahead = item.default_branch?.ahead ?? null;
    let behind = item.default_branch?.behind ?? null;
    if ((ahead === null || behind === null) && sha) {
      const countsRes = await ports.gitRun(
        repoRoot,
        ["rev-list", "--left-right", "--count", `${baseSha}...${sha}`],
        { signal },
      );
      if (countsRes.code === 0) {
        const parts = countsRes.stdout.trim().split(/\s+/);
        if (parts.length === 2) {
          behind = Number.parseInt(parts[0]!, 10) || 0;
          ahead = Number.parseInt(parts[1]!, 10) || 0;
        }
      }
    }
    const resolvedAhead = ahead ?? 0;
    const resolvedBehind = behind ?? 0;

    let commitSubjects: string[] = [];
    if (resolvedAhead > 0) {
      const logRes = await ports.gitRun(
        repoRoot,
        ["log", `--max-count=${COMMIT_SUBJECT_LIMIT}`, "--format=%s", `${baseSha}..${sha}`],
        { signal },
      );
      if (logRes.code === 0 && logRes.stdout.trim()) {
        commitSubjects = logRes.stdout.trim().split(/\r?\n/);
      }
    }

    // Match strongest PR for this branch.
    let matchedPr: PullRequestInfo | null = null;
    if (branch) {
      const candidates = prsByHead.get(branch) ?? [];
      const openPr = candidates.find((p) => p.state === "OPEN");
      if (openPr) {
        matchedPr = openPr;
      } else {
        for (const p of candidates) {
          if (p.state === "MERGED") {
            if (p.head_sha === sha) {
              matchedPr = p;
              break;
            }
            const anc = await ports.gitRun(repoRoot, ["merge-base", "--is-ancestor", sha, p.head_sha], { signal });
            if (anc.code === 0) {
              matchedPr = p;
              break;
            }
          }
        }
        if (!matchedPr && candidates.length > 0) {
          matchedPr = candidates[0]!;
        }
      }
    }

    const integrationEvidence = branch === defaultBranch
      ? null
      : await checkDeterministicIntegration(
          repoRoot,
          baseSha,
          sha,
          item.default_branch?.integration?.reason,
          ports,
          signal,
          resolvedAhead,
        );

    let worktree: WorktreeInfo | null = null;
    if (item.worktree?.path) {
      const wtPath = item.worktree.path;
      const prunableReason = item.worktree.prunable?.reason ?? null;
      const exists = prunableReason ? false : await ports.pathExists(wtPath);
      if (prunableReason) {
        worktree = {
          path: wtPath,
          state: "prunable",
          main: Boolean(item.worktree.main),
          current: Boolean(item.worktree.current),
          detached: Boolean(item.worktree.detached || branch === null),
          prunable_reason: prunableReason,
          dirty: null,
        };
      } else if (!exists) {
        worktree = {
          path: wtPath,
          state: "missing",
          main: Boolean(item.worktree.main),
          current: Boolean(item.worktree.current),
          detached: Boolean(item.worktree.detached || branch === null),
          prunable_reason: null,
          dirty: null,
        };
      } else {
        const ch = item.worktree.changes;
        const isDirtyFromWt = Boolean(
          ch && (ch.staged || ch.modified || ch.untracked || ch.renamed || ch.deleted || ch.conflicted),
        );
        if (isDirtyFromWt) {
          const dirty = await measureDirtyWorktree(repoRoot, wtPath, cache, ports, signal, sha, baseSha);
          worktree = {
            path: wtPath,
            state: "dirty",
            main: Boolean(item.worktree.main),
            current: Boolean(item.worktree.current),
            detached: Boolean(item.worktree.detached || branch === null),
            prunable_reason: null,
            dirty,
          };
        } else {
          const statusCheck = await ports.gitRun(repoRoot, ["status", "--porcelain"], { cwd: wtPath, signal });
          if (statusCheck.code !== 0) {
            worktree = {
              path: wtPath,
              state: "unknown",
              main: Boolean(item.worktree.main),
              current: Boolean(item.worktree.current),
              detached: Boolean(item.worktree.detached || branch === null),
              prunable_reason: null,
              dirty: null,
            };
          } else if (statusCheck.stdout.trim() !== "") {
            const dirty = await measureDirtyWorktree(repoRoot, wtPath, cache, ports, signal, sha, baseSha);
            worktree = {
              path: wtPath,
              state: "dirty",
              main: Boolean(item.worktree.main),
              current: Boolean(item.worktree.current),
              detached: Boolean(item.worktree.detached || branch === null),
              prunable_reason: null,
              dirty,
            };
          } else {
            worktree = {
              path: wtPath,
              state: "clean",
              main: Boolean(item.worktree.main),
              current: Boolean(item.worktree.current),
              detached: Boolean(item.worktree.detached || branch === null),
              prunable_reason: null,
              dirty: null,
            };
          }
        }
      }
    }

    const id = branch ?? `detached:${item.worktree?.path ?? shortSha}`;
    preItems.push({
      item,
      id,
      branch,
      sha,
      shortSha,
      subject,
      committedAt,
      upstream,
      upstreamGone,
      ahead: resolvedAhead,
      behind: resolvedBehind,
      commitSubjects,
      matchedPr,
      integrationEvidence,
      worktree,
    });
  }

  // Detect duplicate unintegrated branch tips.
  const duplicateOfByBranch = new Map<string, string>();
  const unintegratedBySha = new Map<string, PreItem[]>();
  for (const pre of preItems) {
    if (!pre.branch || pre.branch === defaultBranch || pre.integrationEvidence) continue;
    const group = unintegratedBySha.get(pre.sha) ?? [];
    group.push(pre);
    unintegratedBySha.set(pre.sha, group);
  }
  for (const group of unintegratedBySha.values()) {
    if (group.length < 2) continue;
    group.sort((a, b) => {
      const aOpen = a.matchedPr?.state === "OPEN" ? 0 : 1;
      const bOpen = b.matchedPr?.state === "OPEN" ? 0 : 1;
      if (aOpen !== bOpen) return aOpen - bOpen;
      const aWt = a.worktree ? 0 : 1;
      const bWt = b.worktree ? 0 : 1;
      if (aWt !== bWt) return aWt - bWt;
      return (a.branch ?? "").length - (b.branch ?? "").length;
    });
    const keeper = group[0]!;
    for (const dup of group.slice(1)) {
      if (dup.branch && !dup.worktree) {
        duplicateOfByBranch.set(dup.branch, keeper.branch!);
      }
    }
  }

  // Second pass: measure branch residual for unintegrated branches, resolve tickets, and classify.
  const linearCache = new Map<string, Promise<RawTicketRecord>>();
  const getLinearTicket = (ticketId: string): Promise<RawTicketRecord> => {
    if (input.check_linear === false) {
      return Promise.resolve({
        id: ticketId,
        tracker: "linear",
        lookup_status: "unverified",
        title: null,
        status: null,
        status_type: "unknown",
        url: null,
        superseded_by: [],
        error_detail: "check_linear disabled by caller",
      });
    }
    const existing = linearCache.get(ticketId);
    if (existing) return existing;
    const p = ports.lookupLinearTicket(ticketId, signal);
    linearCache.set(ticketId, p);
    return p;
  };

  const entries: AnalyzedEntry[] = [];
  for (const pre of preItems) {
    const duplicateOf = pre.branch ? (duplicateOfByBranch.get(pre.branch) ?? null) : null;
    const needsResidual = pre.branch !== defaultBranch && !pre.integrationEvidence && !duplicateOf && pre.ahead > 0;
    const residual = needsResidual
      ? await measureBranchResidual(
          repoRoot,
          baseSha,
          pre.sha,
          pre.item.default_branch?.merge_conflicts,
          cache,
          ports,
          signal,
        )
      : null;

    const discoveredRefs = discoverTicketRefsForEntry({
      branch: pre.branch,
      worktreePath: pre.worktree?.path ?? null,
      subject: pre.subject,
      commitSubjects: pre.commitSubjects,
      matchedPr: pre.matchedPr,
      allPrsByNumber: prsByNumber,
      ataskTasks,
    });

    const rawTickets: RawTicketRecord[] = await Promise.all(
      discoveredRefs.map((ref) =>
        ref.tracker === "atask" ? Promise.resolve(rawTicketFromAtask(ref.id, ataskById)) : getLinearTicket(ref.id)),
    );

    const classified = classifyEntryVerdict({
      branch: pre.branch,
      defaultBranch,
      ahead: pre.ahead,
      behind: pre.behind,
      subject: pre.subject,
      worktree: pre.worktree,
      pr: pre.matchedPr,
      integrationEvidence: pre.integrationEvidence,
      duplicateOf,
      residual,
      rawTickets,
      remoteOnly: pre.branch ? Boolean(refMetaByBranch.get(pre.branch)?.remoteOnly) : false,
    });

    const tickets = discoveredRefs.map((ref, idx) =>
      evaluateTicketSync(classified.verdict, rawTickets[idx]!, ref.sources));
    const ticketDrift = summarizeTicketDrift(classified.verdict, tickets);

    entries.push({
      id: pre.id,
      branch: pre.branch,
      sha: pre.sha,
      short_sha: pre.shortSha,
      subject: pre.subject,
      committed_at: pre.committedAt,
      upstream: pre.upstream,
      upstream_gone: pre.upstreamGone,
      ahead: pre.ahead,
      behind: pre.behind,
      commit_subjects: pre.commitSubjects,
      worktree: pre.worktree,
      pr: pre.matchedPr
        ? {
            number: pre.matchedPr.number,
            state: pre.matchedPr.state,
            title: pre.matchedPr.title,
            url: pre.matchedPr.url,
            head_sha: pre.matchedPr.head_sha,
            merged_at: pre.matchedPr.merged_at,
          }
        : null,
      verdict: classified.verdict,
      reason: classified.reason,
      recommended_action: classified.recommended_action,
      residual,
      tickets,
      ticket_drift: ticketDrift,
    });
  }

  const shouldLand = entries.filter((e) => e.verdict === "should_land");
  const superseded = entries.filter((e) => e.verdict === "superseded");
  const completedOrRedundant = entries.filter((e) => e.verdict === "completed_or_redundant");
  const protectedOrUnsure = entries.filter((e) => e.verdict === "protected" || e.verdict === "unsure");

  // Collect repo-level open tracker tasks that reference this repo and reconcile them against branch verdicts.
  const repoBaseName = basename(repoRoot).toLowerCase();
  const repoAtaskTasks: RepoAtaskSummary[] = [];
  for (const task of ataskTasks) {
    const statusNorm = task.status.toLowerCase();
    if (statusNorm === "complete" || statusNorm === "completed" || statusNorm === "verified" || statusNorm === "archived") {
      continue;
    }
    const workspace = task.workspace ?? task.attempt?.workspace ?? null;
    const branch = task.branch ?? task.attempt?.branch ?? null;
    const matchesRepo = Boolean(
      (workspace && workspace.includes(repoBaseName))
        || (task.created_cwd && task.created_cwd === repoRoot)
        || (task.project && task.project.toLowerCase() === repoBaseName)
        || (forgeSlug && (task.title.toLowerCase().includes(forgeSlug.toLowerCase()) || (task.key ?? "").toLowerCase().includes(forgeSlug.toLowerCase())))
        || task.title.toLowerCase().includes(repoBaseName),
    );
    if (matchesRepo) {
      const isPruneTask =
        (task.key ?? "").toLowerCase().startsWith("prune/")
        || /\bprune\b/i.test(task.title);
      const matchedEntry = entries.find(
        (e) =>
          (branch && e.branch === branch)
          || (workspace && e.worktree?.path === workspace)
          || e.tickets.some((t) => t.id.toLowerCase() === task.id.toLowerCase()),
      );
      let reconciliationNote: string;
      if (matchedEntry) {
        reconciliationNote = `linked to ${matchedEntry.id} (${matchedEntry.verdict})`;
      } else if (isPruneTask) {
        reconciliationNote = completedOrRedundant.length > 0
          ? `actionable: ${completedOrRedundant.length} completed_or_redundant entry/entries ready to prune`
          : "stale: 0 redundant branches/worktrees remain";
      } else {
        reconciliationNote = "no active branch or worktree in repo";
      }
      repoAtaskTasks.push({
        id: task.id,
        title: task.title,
        status: task.status,
        key: task.key ?? null,
        branch,
        workspace,
        reconciliation_note: reconciliationNote,
      });
    }
  }

  const allTickets = entries.flatMap((e) => e.tickets);
  const uniqueTicketIds = new Set([
    ...allTickets.map((t) => t.id),
    ...repoAtaskTasks.map((t) => t.id),
  ]);
  const outOfDateTicketIds = new Set(
    allTickets
      .filter((t) => t.sync_status === "stale_open_ticket" || t.sync_status === "ticket_closed_but_work_unlanded")
      .map((t) => t.id),
  );

  const summary = {
    total: entries.length,
    should_land: shouldLand.length,
    superseded: superseded.length,
    completed_or_redundant: completedOrRedundant.length,
    protected: entries.filter((e) => e.verdict === "protected").length,
    unsure: entries.filter((e) => e.verdict === "unsure").length,
    worktrees_total: entries.filter((e) => e.worktree !== null).length,
    worktrees_dirty: entries.filter((e) => e.worktree?.state === "dirty").length,
    tickets_checked: uniqueTicketIds.size,
    tickets_out_of_date: outOfDateTicketIds.size,
    needs_ticket_or_triage: entries.filter((e) => e.ticket_drift === "needs_ticket_or_triage").length,
  };

  return {
    repo: repoRoot,
    forge_slug: forgeSlug,
    default_branch: defaultBranch,
    base_ref: baseRef,
    base_sha: baseSha,
    fetch: fetchResult,
    pr_lookup: { status: prList.status, detail: prList.detail },
    summary,
    should_land: shouldLand,
    superseded,
    completed_or_redundant: completedOrRedundant,
    protected_or_unsure: protectedOrUnsure,
    repo_atask_tasks: repoAtaskTasks,
    entries,
  };
}

function formatTicketsCell(entry: AnalyzedEntry): string {
  if (entry.tickets.length === 0) {
    return entry.ticket_drift === "needs_ticket_or_triage" ? "none (needs ticket)" : "none";
  }
  return entry.tickets
    .map((t) => {
      const state = t.lookup_status === "found" ? (t.status ?? t.status_type) : t.lookup_status;
      if (state === t.sync_status) {
        const prNote = entry.pr?.state === "MERGED" ? `; landed via PR #${entry.pr.number}` : "";
        return `${t.id} [${state}${prNote}]`;
      }
      return `${t.id} [${state}; ${t.sync_status}]`;
    })
    .join(", ");
}

export function renderAuditReport(output: AuditRepoBranchesOutput): string {
  const lines: string[] = [];
  lines.push(
    `# Branch & Worktree Audit: ${output.forge_slug ?? output.repo} (base: ${output.default_branch} @ ${output.base_sha.slice(0, 7)})`,
  );
  lines.push(
    `Total: ${output.summary.total} (${output.summary.worktrees_total} worktrees, ${output.summary.worktrees_dirty} dirty) | `
      + `should_land: ${output.summary.should_land} | superseded: ${output.summary.superseded} | `
      + `completed_or_redundant: ${output.summary.completed_or_redundant} | protected: ${output.summary.protected} | unsure: ${output.summary.unsure}`,
  );
  lines.push(
    `Tickets checked: ${output.summary.tickets_checked} | out_of_date: ${output.summary.tickets_out_of_date} | `
      + `unlanded without ticket: ${output.summary.needs_ticket_or_triage}`,
  );

  const renderSection = (title: string, items: readonly AnalyzedEntry[]) => {
    if (items.length === 0) return;
    lines.push("", `## ${title} (${items.length})`);
    for (const e of items) {
      const wtLabel = e.worktree ? ` [worktree: ${e.worktree.state} @ ${e.worktree.path}]` : " [branch only]";
      lines.push(
        `- **${e.id}** (\`${e.short_sha}\`, ↑${e.ahead} ↓${e.behind})${wtLabel}: ${e.reason}`,
      );
      lines.push(`  - Tickets: ${formatTicketsCell(e)}`);
      for (const t of e.tickets) {
        if (t.drift_reason) lines.push(`  - Ticket note (${t.id}): ${t.drift_reason}`);
      }
      lines.push(`  - Action: ${e.recommended_action}`);
    }
  };

  renderSection("Should Land", output.should_land);
  renderSection("Superseded", output.superseded);
  renderSection("Completed / Redundant", output.completed_or_redundant);
  renderSection("Protected / Unsure", output.protected_or_unsure);

  if (output.repo_atask_tasks.length > 0) {
    lines.push("", `## Open Repo Tracker Tasks (${output.repo_atask_tasks.length})`);
    for (const t of output.repo_atask_tasks) {
      const note = t.reconciliation_note ? ` — ${t.reconciliation_note}` : "";
      lines.push(`- **${t.id}** [${t.status}]: ${t.title}${note}`);
    }
  }

  return lines.join("\n");
}
