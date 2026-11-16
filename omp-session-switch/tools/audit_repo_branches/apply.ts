import type { AnalyzedEntry, AuditRepoBranchesOutput, AuditRepoPorts } from "./types.js";

/** One safe cleanup the audit proved redundant. */
export type PruneAction =
  | { readonly kind: "remove_local"; readonly branch: string; readonly worktree: string | null; readonly reason: string }
  | { readonly kind: "delete_remote"; readonly branch: string; readonly reason: string };

export interface SkippedEntry {
  readonly id: string;
  readonly why: string;
}

export interface PrunePlan {
  readonly actions: readonly PruneAction[];
  readonly skipped: readonly SkippedEntry[];
}

export interface ApplyResult {
  readonly applied: boolean;
  readonly plan: PrunePlan;
  readonly done: readonly string[];
  readonly failed: readonly SkippedEntry[];
}

const REMOTE_DELETE_PREFIX = "git push origin --delete ";

/**
 * Turns the audit's `completed_or_redundant` entries into a prune plan. Only entries whose commits already live
 * in the base are acted on; anything with an open PR, real uncommitted work, no branch name, or the base
 * branch itself is skipped with the reason, so a plan never destroys unlanded work.
 */
export function planPrune(output: AuditRepoBranchesOutput): PrunePlan {
  const actions: PruneAction[] = [];
  const skipped: SkippedEntry[] = [];
  const baseBranch = output.base_ref.replace(/^(?:refs\/remotes\/)?origin\//, "");
  const protectedNames = new Set([output.default_branch, baseBranch]);
  for (const entry of output.completed_or_redundant) {
    const why = refusal(entry, protectedNames);
    if (why !== null) {
      skipped.push({ id: entry.id, why });
      continue;
    }
    const branch = entry.branch as string;
    if (entry.recommended_action.startsWith(REMOTE_DELETE_PREFIX)) {
      actions.push({ kind: "delete_remote", branch, reason: entry.reason });
    } else {
      actions.push({ kind: "remove_local", branch, worktree: entry.worktree?.path ?? null, reason: entry.reason });
    }
  }
  return { actions, skipped };
}

function refusal(entry: AnalyzedEntry, protectedNames: ReadonlySet<string>): string | null {
  if (!entry.branch) return "no branch name (detached worktree); inspect by hand";
  if (protectedNames.has(entry.branch)) return "base branch";
  if (entry.pr?.state === "OPEN") return `open PR #${entry.pr.number}; close it first`;
  if (entry.worktree?.main) return "main checkout";
  const dirty = entry.worktree?.dirty;
  if (dirty && (dirty.real_paths?.length ?? 0) > 0) return "worktree has uncommitted work";
  return null;
}

/** Runs the plan. Remote deletes are one `git push origin --delete` per batch of branches. Dry run unless `apply`. */
export async function applyPrune(
  ports: AuditRepoPorts,
  repoRoot: string,
  plan: PrunePlan,
  apply: boolean,
  signal?: AbortSignal,
): Promise<ApplyResult> {
  if (!apply) return { applied: false, plan, done: [], failed: [] };
  const done: string[] = [];
  const failed: SkippedEntry[] = [];
  for (const action of plan.actions) {
    if (action.kind !== "remove_local") continue;
    const res = await ports.wtRemove(repoRoot, action.branch, signal);
    if (res.code === 0) done.push(`removed ${action.branch}`);
    else failed.push({ id: action.branch, why: res.stderr.trim() || `wt remove exit ${res.code}` });
  }
  const remote = plan.actions.filter((a) => a.kind === "delete_remote").map((a) => a.branch);
  for (let i = 0; i < remote.length; i += 50) {
    const batch = remote.slice(i, i + 50);
    const res = await ports.gitRun(repoRoot, ["push", "--no-verify", "origin", "--delete", ...batch], { signal });
    if (res.code === 0) done.push(...batch.map((b) => `deleted origin/${b}`));
    else for (const b of batch) failed.push({ id: b, why: res.stderr.trim() || `git push exit ${res.code}` });
  }
  return { applied: true, plan, done, failed };
}

export function renderApply(result: ApplyResult): string {
  const lines: string[] = [];
  const { plan } = result;
  lines.push(result.applied ? "## Prune applied" : "## Prune plan (dry run; pass prune: apply to execute)");
  for (const a of plan.actions) {
    lines.push(a.kind === "remove_local"
      ? `- remove local ${a.branch}${a.worktree ? ` (worktree ${a.worktree})` : ""}: ${a.reason}`
      : `- delete origin/${a.branch}: ${a.reason}`);
  }
  for (const s of plan.skipped) lines.push(`- skipped ${s.id}: ${s.why}`);
  for (const d of result.done) lines.push(`- done: ${d}`);
  for (const f of result.failed) lines.push(`- FAILED ${f.id}: ${f.why}`);
  return lines.join("\n");
}
