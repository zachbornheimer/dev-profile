export const AUDIT_REPO_BRANCHES_NAME = "audit_repo_branches";

export type BranchVerdict =
  | "should_land"
  | "superseded"
  | "completed_or_redundant"
  | "protected"
  | "unsure";

export type TicketTracker = "linear" | "atask";

export type TicketSyncStatus =
  | "up_to_date"
  | "stale_open_ticket"
  | "ticket_closed_but_work_unlanded"
  | "unverified";

export interface TicketCheck {
  readonly id: string;
  readonly tracker: TicketTracker;
  readonly sources: readonly string[];
  readonly lookup_status: "found" | "not_found" | "unverified";
  readonly title: string | null;
  readonly status: string | null;
  readonly status_type: "open" | "completed" | "canceled" | "unknown";
  readonly url: string | null;
  readonly superseded_by: readonly string[];
  readonly sync_status: TicketSyncStatus;
  readonly drift_reason: string | null;
}

export interface MissingLineSample {
  readonly path: string;
  readonly line: string;
}

export interface DirtyWorktreeStats {
  readonly tracked_files: number;
  readonly untracked_files: number;
  readonly lines_added: number;
  readonly lines_removed: number;
  readonly real_paths: readonly string[];
  readonly noise_paths: readonly string[];
  readonly base_overlapping_paths?: readonly string[];
  readonly lines_considered: number;
  readonly lines_missing_from_base: number;
  readonly landed_ratio: number | null;
  readonly missing_sample: readonly MissingLineSample[];
}

export interface BaseTouchingCommit {
  readonly sha: string;
  readonly subject: string;
  readonly tickets: readonly string[];
}

export interface ResidualStats {
  readonly files_changed: number;
  readonly lines_added: number;
  readonly lines_removed: number;
  readonly merge_conflicts: boolean;
  readonly conflicted_paths: readonly string[];
  readonly lines_considered: number;
  readonly lines_missing_from_base: number;
  readonly landed_ratio: number | null;
  readonly unlanded_new_files: readonly string[];
  readonly base_touching_commits: readonly BaseTouchingCommit[];
  readonly missing_sample: readonly MissingLineSample[];
}

export interface WorktreeInfo {
  readonly path: string;
  readonly state: "clean" | "dirty" | "prunable" | "missing" | "unknown";
  readonly main: boolean;
  readonly current: boolean;
  readonly detached: boolean;
  readonly prunable_reason: string | null;
  readonly dirty: DirtyWorktreeStats | null;
}

export interface PullRequestInfo {
  readonly number: number;
  readonly state: "OPEN" | "MERGED" | "CLOSED";
  readonly title: string;
  readonly body: string;
  readonly url: string;
  readonly head_ref: string;
  readonly head_sha: string;
  readonly merged_at: string | null;
}

export type TicketDriftKind =
  | "in_sync"
  | "stale_open_ticket"
  | "ticket_closed_but_work_unlanded"
  | "needs_ticket_or_triage"
  | "unverified"
  | "none";

export interface AnalyzedEntry {
  readonly id: string;
  readonly branch: string | null;
  readonly sha: string;
  readonly short_sha: string;
  readonly subject: string | null;
  readonly committed_at: string | null;
  readonly upstream: string | null;
  readonly upstream_gone: boolean;
  readonly ahead: number;
  readonly behind: number;
  readonly commit_subjects: readonly string[];
  readonly worktree: WorktreeInfo | null;
  readonly pr: Omit<PullRequestInfo, "body" | "head_ref"> | null;
  readonly verdict: BranchVerdict;
  readonly reason: string;
  readonly recommended_action: string;
  readonly residual: ResidualStats | null;
  readonly tickets: readonly TicketCheck[];
  readonly ticket_drift: TicketDriftKind;
}

export interface RepoAtaskSummary {
  readonly id: string;
  readonly title: string;
  readonly status: string;
  readonly key: string | null;
  readonly branch: string | null;
  readonly workspace: string | null;
  readonly reconciliation_note?: string;
}

export interface AuditRepoBranchesSummary {
  readonly total: number;
  readonly should_land: number;
  readonly superseded: number;
  readonly completed_or_redundant: number;
  readonly protected: number;
  readonly unsure: number;
  readonly worktrees_total: number;
  readonly worktrees_dirty: number;
  readonly tickets_checked: number;
  readonly tickets_out_of_date: number;
  readonly needs_ticket_or_triage: number;
}

export interface AuditRepoBranchesOutput {
  readonly repo: string;
  readonly forge_slug: string | null;
  readonly default_branch: string;
  readonly base_ref: string;
  readonly base_sha: string;
  readonly fetch: { readonly status: "ok" | "skipped" | "failed"; readonly detail: string };
  readonly pr_lookup: { readonly status: "ok" | "unavailable"; readonly detail: string };
  readonly summary: AuditRepoBranchesSummary;
  readonly should_land: readonly AnalyzedEntry[];
  readonly superseded: readonly AnalyzedEntry[];
  readonly completed_or_redundant: readonly AnalyzedEntry[];
  readonly protected_or_unsure: readonly AnalyzedEntry[];
  readonly repo_atask_tasks: readonly RepoAtaskSummary[];
  readonly entries: readonly AnalyzedEntry[];
}

export interface WtItem {
  readonly branch: string | null;
  readonly head: {
    readonly sha: string;
    readonly short_sha?: string;
    readonly subject?: string | null;
    readonly committed_at?: string | null;
  };
  readonly worktree?: {
    readonly path: string;
    readonly main?: boolean;
    readonly current?: boolean;
    readonly detached?: boolean;
    readonly prunable?: { readonly reason?: string } | null;
    readonly changes?: {
      readonly staged?: boolean;
      readonly modified?: boolean;
      readonly untracked?: boolean;
      readonly renamed?: boolean;
      readonly deleted?: boolean;
      readonly conflicted?: boolean;
      readonly diff?: { readonly added?: number; readonly deleted?: number };
    } | null;
  } | null;
  readonly default_branch?: {
    readonly ahead?: number | null;
    readonly behind?: number | null;
    readonly diff?: { readonly added?: number; readonly deleted?: number } | null;
    readonly orphan?: boolean | null;
    readonly integration?: { readonly reason?: string | null } | null;
    readonly merge_conflicts?: boolean | null;
  } | null;
  readonly upstream?: {
    readonly remote?: string | null;
    readonly branch?: string | null;
    readonly ahead?: number | null;
    readonly behind?: number | null;
  } | null;
  readonly display?: {
    readonly state?: string | null;
    readonly symbols?: string | null;
  } | null;
}

export interface WtListEnvelope {
  readonly repo?: {
    readonly default_branch?: string;
    readonly forge?: {
      readonly owner?: string;
      readonly name?: string;
      readonly url?: string;
    } | null;
  };
  readonly items: readonly WtItem[];
}

export interface RawTicketRecord {
  readonly id: string;
  readonly tracker: TicketTracker;
  readonly lookup_status: "found" | "not_found" | "unverified";
  readonly title: string | null;
  readonly status: string | null;
  readonly status_type: "open" | "completed" | "canceled" | "unknown";
  readonly url: string | null;
  readonly superseded_by: readonly string[];
  readonly error_detail?: string;
}

export interface AtaskRawTask {
  readonly id: string;
  readonly title: string;
  readonly status: string;
  readonly key?: string | null;
  readonly project?: string | null;
  readonly projects?: readonly string[];
  readonly branch?: string | null;
  readonly workspace?: string | null;
  readonly created_cwd?: string | null;
  readonly attempt?: {
    readonly workspace?: string | null;
    readonly branch?: string | null;
  } | null;
}

export interface AuditRepoPorts {
  resolveRepoRoot(repo: string, signal?: AbortSignal): Promise<string>;
  cleanup?(): Promise<void>;
  fetchPrune(repoRoot: string, signal?: AbortSignal): Promise<{ status: "ok" | "failed"; detail: string }>;
  resolveBase(repoRoot: string, wtDefaultBranch?: string, signal?: AbortSignal): Promise<{ defaultBranch: string; baseRef: string; baseSha: string }>;
  listWtItems(repoRoot: string, signal?: AbortSignal): Promise<WtListEnvelope>;
  listPullRequests(repoRoot: string, signal?: AbortSignal): Promise<{ prs: readonly PullRequestInfo[]; status: "ok" | "unavailable"; detail: string }>;
  gitRun(repoRoot: string, args: readonly string[], options?: { cwd?: string; signal?: AbortSignal }): Promise<{ code: number; stdout: string; stderr: string }>;
  readWorktreeFile(worktreePath: string, relPath: string): Promise<string | null>;
  pathExists(absPath: string): Promise<boolean>;
  listAtaskTasks(signal?: AbortSignal): Promise<readonly AtaskRawTask[]>;
  lookupLinearTicket(ticketId: string, signal?: AbortSignal): Promise<RawTicketRecord>;
}
