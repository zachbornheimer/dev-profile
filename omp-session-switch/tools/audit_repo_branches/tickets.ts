import type {
  AtaskRawTask,
  BranchVerdict,
  PullRequestInfo,
  RawTicketRecord,
  TicketCheck,
  TicketDriftKind,
  TicketTracker,
} from "./types.js";

const LINEAR_ID_RE = /\b(SAH|ZYS)-(\d+)\b/gi;
const ATASK_ID_RE = /\bat-([a-z0-9]{6})\b/gi;
const PR_REF_RE = /(?:PR\s*#|\(#|#)(\d+)\b/gi;

/** Extract normalized Linear (`SAH-123`, `ZYS-1541`) and atask (`at-xxxxxx`) IDs from free text. */
export function extractTicketsFromText(text: string | null | undefined): { linear: string[]; atask: string[] } {
  if (!text) return { linear: [], atask: [] };
  const linearSet = new Set<string>();
  const ataskSet = new Set<string>();
  for (const match of text.matchAll(LINEAR_ID_RE)) {
    linearSet.add(`${match[1]!.toUpperCase()}-${match[2]!}`);
  }
  for (const match of text.matchAll(ATASK_ID_RE)) {
    ataskSet.add(`at-${match[1]!.toLowerCase()}`);
  }
  return {
    linear: [...linearSet],
    atask: [...ataskSet],
  };
}

/** Extract PR numbers (`#58`, `PR #57`, `(#63)`) mentioned in commit or branch text. */
export function extractPrNumbersFromText(text: string | null | undefined): number[] {
  if (!text) return [];
  const nums = new Set<number>();
  for (const match of text.matchAll(PR_REF_RE)) {
    const n = Number.parseInt(match[1]!, 10);
    if (Number.isFinite(n) && n > 0) nums.add(n);
  }
  return [...nums];
}

export interface DiscoveredTicketRef {
  readonly id: string;
  readonly tracker: TicketTracker;
  readonly sources: string[];
}

export function discoverTicketRefsForEntry(input: {
  branch: string | null;
  worktreePath: string | null;
  subject: string | null;
  commitSubjects: readonly string[];
  matchedPr: PullRequestInfo | null;
  allPrsByNumber: ReadonlyMap<number, PullRequestInfo>;
  ataskTasks: readonly AtaskRawTask[];
}): DiscoveredTicketRef[] {
  const map = new Map<string, { id: string; tracker: TicketTracker; sources: Set<string> }>();
  const add = (id: string, tracker: TicketTracker, source: string) => {
    const existing = map.get(id);
    if (existing) {
      existing.sources.add(source);
    } else {
      map.set(id, { id, tracker, sources: new Set([source]) });
    }
  };
  const scan = (text: string | null | undefined, source: string) => {
    const found = extractTicketsFromText(text);
    for (const id of found.linear) add(id, "linear", source);
    for (const id of found.atask) add(id, "atask", source);
  };

  scan(input.branch, "branch");
  scan(input.worktreePath, "worktree");
  scan(input.subject, "commit");
  for (const line of input.commitSubjects) {
    scan(line, "commit");
  }
  if (input.matchedPr) {
    scan(input.matchedPr.title, "pr");
    scan(input.matchedPr.body, "pr");
  }

  // Also resolve PR numbers referenced in HEAD or commit subjects (e.g. "Merge PR #58") against loaded PRs.
  const referencedPrNumbers = new Set<number>(extractPrNumbersFromText(input.subject));
  for (const line of input.commitSubjects) {
    for (const n of extractPrNumbersFromText(line)) referencedPrNumbers.add(n);
  }
  for (const num of referencedPrNumbers) {
    const pr = input.allPrsByNumber.get(num);
    if (pr) {
      scan(pr.title, `pr#${num}`);
      scan(pr.body, `pr#${num}`);
    }
  }

  // Match atask tasks whose branch or workspace points to this branch/worktree.
  for (const task of input.ataskTasks) {
    const taskBranches = [task.branch, task.attempt?.branch].filter((b): b is string => Boolean(b));
    const taskWorkspaces = [task.workspace, task.attempt?.workspace].filter((w): w is string => Boolean(w));
    if (input.branch && taskBranches.includes(input.branch)) {
      add(task.id.toLowerCase(), "atask", "atask");
    }
    if (input.worktreePath && taskWorkspaces.includes(input.worktreePath)) {
      add(task.id.toLowerCase(), "atask", "atask");
    }
  }

  return [...map.values()].map((item) => ({
    id: item.id,
    tracker: item.tracker,
    sources: [...item.sources],
  }));
}

export function classifyAtaskStatusType(status: string | null | undefined): "open" | "completed" | "canceled" | "unknown" {
  if (!status) return "unknown";
  const norm = status.trim().toLowerCase();
  if (norm === "complete" || norm === "completed" || norm === "verified" || norm === "done") return "completed";
  if (norm === "archived" || norm === "canceled" || norm === "cancelled") return "canceled";
  if (
    norm === "ready"
    || norm === "open"
    || norm === "in_progress"
    || norm === "claimed"
    || norm === "blocked"
    || norm === "interrupted"
    || norm === "draft"
  ) {
    return "open";
  }
  return "unknown";
}

export function classifyLinearStatusType(
  stateType: string | null | undefined,
  stateName: string | null | undefined,
): "open" | "completed" | "canceled" | "unknown" {
  const normType = (stateType ?? "").trim().toLowerCase();
  if (normType === "completed") return "completed";
  if (normType === "canceled" || normType === "cancelled") return "canceled";
  if (normType === "backlog" || normType === "unstarted" || normType === "started" || normType === "triage") {
    return "open";
  }
  const normName = (stateName ?? "").trim().toLowerCase();
  if (normName === "done" || normName === "completed" || normName === "complete") return "completed";
  if (normName === "canceled" || normName === "cancelled" || normName === "duplicate") return "canceled";
  if (
    normName === "triage"
    || normName === "unreviewed"
    || normName === "ready for dev"
    || normName === "ready for development"
    || normName === "initial ticket review"
    || normName === "in progress"
    || normName === "in review"
    || normName === "pull request"
    || normName === "todo"
    || normName === "backlog"
  ) {
    return "open";
  }
  return "unknown";
}

export function rawTicketFromAtask(id: string, tasksById: ReadonlyMap<string, AtaskRawTask>): RawTicketRecord {
  const norm = id.toLowerCase();
  const task = tasksById.get(norm);
  if (!task) {
    return {
      id: norm,
      tracker: "atask",
      lookup_status: "not_found",
      title: null,
      status: null,
      status_type: "unknown",
      url: null,
      superseded_by: [],
      error_detail: `atask task ${norm} not found`,
    };
  }
  return {
    id: norm,
    tracker: "atask",
    lookup_status: "found",
    title: task.title,
    status: task.status,
    status_type: classifyAtaskStatusType(task.status),
    url: null,
    superseded_by: [],
  };
}

/** Compare a branch/worktree's verdict against a ticket's state to determine if the ticket is up to date. */
export function evaluateTicketSync(
  verdict: BranchVerdict,
  raw: RawTicketRecord,
  sources: readonly string[],
): TicketCheck {
  if (raw.lookup_status !== "found") {
    return {
      id: raw.id,
      tracker: raw.tracker,
      sources,
      lookup_status: raw.lookup_status,
      title: raw.title,
      status: raw.status,
      status_type: raw.status_type,
      url: raw.url,
      superseded_by: raw.superseded_by,
      sync_status: "unverified",
      drift_reason: raw.error_detail ?? `could not verify ${raw.id}`,
    };
  }

  if (raw.superseded_by.length > 0 && raw.status_type === "open") {
    return {
      id: raw.id,
      tracker: raw.tracker,
      sources,
      lookup_status: "found",
      title: raw.title,
      status: raw.status,
      status_type: raw.status_type,
      url: raw.url,
      superseded_by: raw.superseded_by,
      sync_status: "stale_open_ticket",
      drift_reason: `ticket ${raw.id} is still open (${raw.status ?? "open"}) despite being superseded by ${raw.superseded_by.join(", ")}`,
    };
  }

  if (verdict === "completed_or_redundant") {
    if (raw.status_type === "open") {
      return {
        id: raw.id,
        tracker: raw.tracker,
        sources,
        lookup_status: "found",
        title: raw.title,
        status: raw.status,
        status_type: raw.status_type,
        url: raw.url,
        superseded_by: raw.superseded_by,
        sync_status: "stale_open_ticket",
        drift_reason: `branch work is already integrated on the default branch, but ticket ${raw.id} is still open (${raw.status ?? "open"})`,
      };
    }
    return {
      id: raw.id,
      tracker: raw.tracker,
      sources,
      lookup_status: "found",
      title: raw.title,
      status: raw.status,
      status_type: raw.status_type,
      url: raw.url,
      superseded_by: raw.superseded_by,
      sync_status: "up_to_date",
      drift_reason: null,
    };
  }

  if (verdict === "superseded") {
    if (raw.status_type === "open") {
      return {
        id: raw.id,
        tracker: raw.tracker,
        sources,
        lookup_status: "found",
        title: raw.title,
        status: raw.status,
        status_type: raw.status_type,
        url: raw.url,
        superseded_by: raw.superseded_by,
        sync_status: "stale_open_ticket",
        drift_reason: `branch work was superseded, but ticket ${raw.id} is still open (${raw.status ?? "open"})`,
      };
    }
    return {
      id: raw.id,
      tracker: raw.tracker,
      sources,
      lookup_status: "found",
      title: raw.title,
      status: raw.status,
      status_type: raw.status_type,
      url: raw.url,
      superseded_by: raw.superseded_by,
      sync_status: "up_to_date",
      drift_reason: null,
    };
  }

  if (verdict === "should_land") {
    if (raw.status_type === "completed" || raw.status_type === "canceled") {
      return {
        id: raw.id,
        tracker: raw.tracker,
        sources,
        lookup_status: "found",
        title: raw.title,
        status: raw.status,
        status_type: raw.status_type,
        url: raw.url,
        superseded_by: raw.superseded_by,
        sync_status: "ticket_closed_but_work_unlanded",
        drift_reason: `branch/worktree still has unlanded work, but ticket ${raw.id} is already marked ${raw.status ?? raw.status_type}`,
      };
    }
    return {
      id: raw.id,
      tracker: raw.tracker,
      sources,
      lookup_status: "found",
      title: raw.title,
      status: raw.status,
      status_type: raw.status_type,
      url: raw.url,
      superseded_by: raw.superseded_by,
      sync_status: "up_to_date",
      drift_reason: null,
    };
  }

  return {
    id: raw.id,
    tracker: raw.tracker,
    sources,
    lookup_status: "found",
    title: raw.title,
    status: raw.status,
    status_type: raw.status_type,
    url: raw.url,
    superseded_by: raw.superseded_by,
    sync_status: "up_to_date",
    drift_reason: null,
  };
}

export function summarizeTicketDrift(verdict: BranchVerdict, tickets: readonly TicketCheck[]): TicketDriftKind {
  if (tickets.some((t) => t.sync_status === "stale_open_ticket")) return "stale_open_ticket";
  if (tickets.some((t) => t.sync_status === "ticket_closed_but_work_unlanded")) return "ticket_closed_but_work_unlanded";
  if (tickets.some((t) => t.sync_status === "unverified")) return "unverified";
  if (tickets.length > 0) return "in_sync";
  if (verdict === "should_land") return "needs_ticket_or_triage";
  return "none";
}
