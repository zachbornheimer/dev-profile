import { describe, expect, it } from "bun:test";
import installBaseTools, { ESSENTIAL_TOOLS, restrictPayloadTools } from "../../extensions/base-tools.js";
import { discoverTools } from "../../extensions/prompts/index.js";
import { renderAuditReport, runAuditRepoBranches } from "./analyze.js";
import factory from "./index.js";
import { createLiveAuditRepoPorts } from "./live_ports.js";
import { extractTicketsFromText } from "./tickets.js";
import type {
  AtaskRawTask,
  AuditRepoPorts,
  PullRequestInfo,
  RawTicketRecord,
  WtItem,
} from "./types.js";
import { loadZod } from "./zod_for_tests.js";

const BASE_SHA = "ec5c20f14747188ff1c1918950fe4b3c741049bc";
const MERGE_BASE_SHA = "1111111111111111111111111111111111111111";

interface FakeWorldOptions {
  items?: readonly WtItem[];
  prs?: readonly PullRequestInfo[];
  ataskTasks?: readonly AtaskRawTask[];
  linearTickets?: Readonly<Record<string, RawTicketRecord>>;
  baseFiles?: Readonly<Record<string, string>>;
  branchDiffs?: Readonly<
    Record<
      string,
      {
        numstat: string;
        diff: string;
        mergeConflicts?: boolean;
        conflictedPaths?: readonly string[];
        commitSubjects?: readonly string[];
        baseTouchingLog?: string;
        cherry?: string;
      }
    >
  >;
  worktreeDiffs?: Readonly<
    Record<
      string,
      {
        numstat: string;
        diff: string;
        status: string;
        untrackedFiles?: Readonly<Record<string, string>>;
      }
    >
  >;
  existingPaths?: ReadonlySet<string>;
}

function createFakePorts(opts: FakeWorldOptions = {}): AuditRepoPorts {
  const baseFiles = opts.baseFiles ?? {};
  const branchDiffs = opts.branchDiffs ?? {};
  const worktreeDiffs = opts.worktreeDiffs ?? {};
  const linearTickets = opts.linearTickets ?? {};

  return {
    async resolveRepoRoot(repo) {
      return repo === "." ? "/repo/librarian" : repo;
    },
    async fetchPrune() {
      return { status: "ok", detail: "" };
    },
    async resolveBase(_repoRoot, wtDefault) {
      return {
        defaultBranch: wtDefault ?? "main",
        baseRef: `origin/${wtDefault ?? "main"}`,
        baseSha: BASE_SHA,
      };
    },
    async listWtItems() {
      return {
        repo: {
          default_branch: "main",
          forge: { owner: "zachbornheimer", name: "librarian" },
        },
        items: opts.items ?? [],
      };
    },
    async listPullRequests() {
      return { prs: opts.prs ?? [], status: "ok", detail: "" };
    },
    async pathExists(absPath) {
      if (opts.existingPaths) return opts.existingPaths.has(absPath);
      return true;
    },
    async readWorktreeFile(worktreePath, relPath) {
      return worktreeDiffs[worktreePath]?.untrackedFiles?.[relPath] ?? null;
    },
    async listAtaskTasks() {
      return opts.ataskTasks ?? [];
    },
    async lookupLinearTicket(ticketId) {
      const found = linearTickets[ticketId.toUpperCase()];
      if (found) return found;
      return {
        id: ticketId.toUpperCase(),
        tracker: "linear",
        lookup_status: "unverified",
        title: null,
        status: null,
        status_type: "unknown",
        url: null,
        superseded_by: [],
        error_detail: `no fake entry for ${ticketId}`,
      };
    },
    async gitRun(_repoRoot, args, callOpts) {
      const cmd = args[0];
      if (cmd === "for-each-ref") {
        return { code: 0, stdout: "", stderr: "" };
      }
      if (cmd === "cat-file" && args[1] === "-e") {
        const spec = args[2] ?? "";
        const path = spec.split(":")[1] ?? "";
        return { code: path in baseFiles ? 0 : 1, stdout: "", stderr: "" };
      }
      if (cmd === "show") {
        const spec = args[1] ?? "";
        const path = spec.split(":")[1] ?? "";
        const content = baseFiles[path];
        return content !== undefined
          ? { code: 0, stdout: content, stderr: "" }
          : { code: 1, stdout: "", stderr: "not found" };
      }
      if (cmd === "merge-base") {
        if (args[1] === "--is-ancestor") {
          const sha = args[2] ?? "";
          const target = args[3] ?? "";
          return { code: sha === target || sha === BASE_SHA ? 0 : 1, stdout: "", stderr: "" };
        }
        return { code: 0, stdout: MERGE_BASE_SHA, stderr: "" };
      }
      if (cmd === "cherry") {
        const sha = args[2] ?? "";
        const cherryOut = branchDiffs[sha]?.cherry ?? "";
        return { code: 0, stdout: cherryOut, stderr: "" };
      }
      if (cmd === "merge-tree") {
        const sha = args[args.length - 1] ?? "";
        const b = branchDiffs[sha];
        if (b?.mergeConflicts) {
          const paths = (b.conflictedPaths ?? []).join("\n");
          return { code: 1, stdout: `treeoid\n${paths}\n\nconflict details`, stderr: "" };
        }
        return { code: 0, stdout: "different_tree_oid\n", stderr: "" };
      }
      if (cmd === "rev-parse" && (args[1] ?? "").endsWith("^{tree}")) {
        return { code: 0, stdout: "base_tree_oid\n", stderr: "" };
      }
      if (cmd === "diff") {
        const wtCwd = callOpts?.cwd;
        if (args[1] === "HEAD" && wtCwd && worktreeDiffs[wtCwd]) {
          const wt = worktreeDiffs[wtCwd]!;
          return {
            code: 0,
            stdout: args.includes("--numstat") ? wt.numstat : wt.diff,
            stderr: "",
          };
        }
        const sha = args[args.length - 1] ?? "";
        const b = branchDiffs[sha];
        if (b) {
          return {
            code: 0,
            stdout: args.includes("--numstat") ? b.numstat : b.diff,
            stderr: "",
          };
        }
        return { code: 0, stdout: "", stderr: "" };
      }
      if (cmd === "status" && args[1] === "--porcelain") {
        const wtCwd = callOpts?.cwd ?? "";
        return { code: 0, stdout: worktreeDiffs[wtCwd]?.status ?? "", stderr: "" };
      }
      if (cmd === "log") {
        const rangeArg = args.find((a) => a.includes("..")) ?? "";
        if (args.includes("--no-merges")) {
          const matchingBranch = Object.values(branchDiffs).find((b) => b.baseTouchingLog);
          return { code: 0, stdout: matchingBranch?.baseTouchingLog ?? "", stderr: "" };
        }
        const sha = rangeArg.split("..")[1] ?? "";
        const subjects = branchDiffs[sha]?.commitSubjects ?? [];
        return { code: 0, stdout: subjects.join("\n"), stderr: "" };
      }
      return { code: 0, stdout: "", stderr: "" };
    },
  };
}

describe("audit_repo_branches", () => {
  it("loads under omp's own pi.zod (omptype), sets hidden+discoverable, and validates parameters", async () => {
    const zod = await loadZod();
    const created = await (factory as (pi: unknown) => unknown)({
      zod,
      cwd: "/repo/librarian",
      exec: async () => ({ stdout: "", stderr: "", code: 0, killed: false }),
    });
    const tool = created as {
      name: string;
      hidden: boolean;
      loadMode: string;
      parameters: { parse: (v: unknown) => unknown };
    };
    expect(tool.name).toBe("audit_repo_branches");
    expect(tool.hidden).toBe(true);
    expect(tool.loadMode).toBe("discoverable");

    expect(tool.parameters.parse({ repo: "." })).toEqual({ repo: "." });
    expect(tool.parameters.parse({ repo: "/tmp/repo", fetch: null, check_linear: false })).toEqual({
      repo: "/tmp/repo",
      fetch: null,
      check_linear: false,
    });
    expect(() => tool.parameters.parse({})).toThrow();
    expect(() => tool.parameters.parse({ repo: "" })).toThrow();
  });

  it("is discovered by onUserPromptSubmit discoverTools with full description and required repo arg", () => {
    const candidates = discoverTools([], new Set());
    const entry = candidates.find((c) => c.bareName === "audit_repo_branches");
    expect(entry).toBeDefined();
    expect(entry?.description).toContain("Audit and analyze a repository local branches and wt worktrees");
    expect(entry?.howToCall).toContain('tool_call({ address: "omp/audit_repo_branches", args: { "repo": "<repo>" } })');
  });

  it("preserves a forced hidden tool across base-tools input, before_agent_start, and before_provider_request", async () => {
    const handlers = new Map<string, (event: unknown, ctx: unknown) => unknown>();
    let active = ["run_command", "write", "read", "tool_search", "skill_search", "tool_call", "audit_repo_branches"];
    installBaseTools({
      on: (event, fn) => {
        handlers.set(event, fn);
      },
      getAllTools: () => [
        ...Array.from(ESSENTIAL_TOOLS, (name) => ({ name })),
        { name: "audit_repo_branches", hidden: true, loadMode: "discoverable" as const },
      ],
      getActiveTools: () => active,
      setActiveTools: (next) => {
        active = [...next];
      },
    });

    await handlers.get("session_start")?.({}, {});
    expect(active).not.toContain("audit_repo_branches");

    // Pre-slash-command input hook activates audit_repo_branches BEFORE executeBuiltinSlashCommand runs /force.
    const inputRes = await handlers.get("input")?.(
      { text: "/force audit-repo-branches please audit zachbornheimer/librarian" },
      {},
    );
    expect(active).toContain("audit_repo_branches");
    expect(inputRes).toEqual({
      text: "/force audit_repo_branches please audit zachbornheimer/librarian",
    });

    // Exact canonical name does not mutate the slash command text (Gotcha #3).
    const exactRes = await handlers.get("input")?.(
      { text: "/force audit_repo_branches please audit zachbornheimer/librarian" },
      {},
    );
    expect(exactRes).toBeUndefined();

    await handlers.get("before_agent_start")?.({}, {});
    expect(active).toContain("audit_repo_branches");

    // And on the provider wire request, restrictPayloadTools keeps the forced tool in payload.tools.
    const payload = {
      tools: [{ name: "read" }, { name: "audit_repo_branches" }, { name: "unrelated_hidden_tool" }],
      tool_choice: { type: "tool", name: "audit_repo_branches" },
    };
    const restricted = restrictPayloadTools(payload, ESSENTIAL_TOOLS) as { tools: { name: string }[] };
    expect(restricted.tools.map((t) => t.name)).toEqual(["read", "audit_repo_branches"]);

    // Subsequent normal turn retires the one-off forced tool back to the 6 essentials.
    await handlers.get("before_agent_start")?.({ prompt: "thanks" }, {});
    expect(active).not.toContain("audit_repo_branches");

    // On models with supportsForcedToolChoice === false (e.g. Claude Sonnet 5.5 over gateway),
    // input rewrites /force into a direct prompt and before_provider_request enforces [forced] -> [none].
    const gwRes = await handlers.get("input")?.(
      { text: "/force audit_repo_branches Audit librarian" },
      { model: { api: "openai-completions", compat: { supportsForcedToolChoice: false } } },
    );
    expect((gwRes as { text?: string } | undefined)?.text).toContain("Call the `audit_repo_branches` tool once now");
    const step1 = handlers.get("before_provider_request")?.(
      {
        payload: {
          messages: [{ role: "user", content: "Audit librarian" }],
          tools: [{ name: "read" }, { name: "audit_repo_branches" }, { name: "write" }],
        },
      },
      {},
    ) as { tools: { name: string }[] };
    expect(step1.tools.map((t) => t.name)).toEqual(["audit_repo_branches"]);
    const step2 = handlers.get("before_provider_request")?.(
      {
        payload: {
          messages: [
            { role: "user", content: "Audit librarian" },
            { role: "assistant", tool_calls: [{ function: { name: "audit_repo_branches" } }] },
            { role: "tool", content: "report" },
          ],
          tools: [{ name: "read" }, { name: "audit_repo_branches" }, { name: "write" }],
        },
      },
      {},
    ) as { tool_choice?: string; tools: { name: string }[] };
    expect(step2.tool_choice).toBe("none");
  });

  it("extracts Linear (SAH/ZYS) and atask identifiers accurately", () => {
    const res = extractTicketsFromText(
      "branch zys-1541-stub-native-sidecar refs SAH-42, ZYS-1680 and at-4xx2tf plus AT-RF6EPS",
    );
    expect(res.linear).toEqual(["ZYS-1541", "SAH-42", "ZYS-1680"]);
    expect(res.atask).toEqual(["at-4xx2tf", "at-rf6eps"]);
  });

  it("classifies a dirty worktree whose committed HEAD is already an ancestor of main as should_land (feat/stream-labels regression)", async () => {
    const wtPath = "/worktrees/librarian-feat-stream-labels";
    const ports = createFakePorts({
      items: [
        {
          branch: "main",
          head: { sha: BASE_SHA, short_sha: "ec5c20f", subject: "main tip" },
          worktree: { path: "/repo/librarian", main: true, current: true, changes: { staged: false, modified: false, untracked: false } },
        },
        {
          branch: "feat/stream-labels",
          head: { sha: "7d7a75c3745cdcf8b0406f751357d87838f7613f", short_sha: "7d7a75c", subject: "Merge PR #57" },
          worktree: {
            path: wtPath,
            main: false,
            current: false,
            changes: {
              staged: false,
              modified: true,
              untracked: true,
              deleted: true,
              diff: { added: 2567, deleted: 453 },
            },
          },
          default_branch: {
            ahead: 0,
            behind: 20,
            integration: { reason: "ancestor" },
            merge_conflicts: true,
          },
        },
      ],
      worktreeDiffs: {
        [wtPath]: {
          numstat: "400\t120\tinternal/optimize/video_selection.go\n",
          diff: [
            "--- a/internal/optimize/video_selection.go",
            "+++ b/internal/optimize/video_selection.go",
            "+func selectLabeledAudioStreams(streams []Stream, origLang string) []Stream {",
            "+    return filterStreamsByPolicy(streams, origLang)",
          ].join("\n"),
          status: " M internal/optimize/video_selection.go\n?? cmd/librarian/relabel.go\n",
          untrackedFiles: {
            "cmd/librarian/relabel.go": "package main\nfunc runRelabelCommand(args []string) error { return nil }\n",
          },
        },
      },
      baseFiles: {
        "internal/optimize/video_selection.go": "package optimize\nfunc oldSelection() {}\n",
      },
    });

    const out = await runAuditRepoBranches({ repo: "." }, ports);
    expect(out.summary.should_land).toBe(1);
    const streamLabels = out.should_land[0]!;
    expect(streamLabels.branch).toBe("feat/stream-labels");
    expect(streamLabels.verdict).toBe("should_land");
    expect(streamLabels.reason).toContain("committed HEAD is integrated into main, but worktree has unlanded working-tree edits");
    expect(streamLabels.ticket_drift).toBe("needs_ticket_or_triage");
  });

  it("classifies ancestor, squash-merged (merge_adds_nothing), prunable worktrees, and stale conflicting wip branches, and detects ticket drift", async () => {
    const wipSha = "c0796438a8a7293dc82e869bef48672edf13b9c4";
    const activeSha = "9999999999999999999999999999999999999999";

    const ports = createFakePorts({
      items: [
        {
          branch: "main",
          head: { sha: BASE_SHA, short_sha: "ec5c20f", subject: "main" },
        },
        {
          branch: "zys-1541-stub-native-sidecar",
          head: { sha: "0e2e5652ab55196beb02e757082c47adaeedbd10", short_sha: "0e2e565", subject: "style(optimize): align stub comments" },
          worktree: {
            path: "/worktrees/librarian-zys-1541",
            changes: { staged: false, modified: false, untracked: false },
          },
          default_branch: {
            ahead: 0,
            behind: 97,
            integration: { reason: "ancestor" },
          },
        },
        {
          branch: "fix/deps-edwards25519",
          head: { sha: "ed62e39c8ea8f62c7ff7149fa6bd61bf98ba15b8", short_sha: "ed62e39", subject: "fix(deps): bump Go toolchain" },
          default_branch: {
            ahead: 2,
            behind: 4,
            integration: { reason: "merge_adds_nothing" },
          },
        },
        {
          branch: null,
          head: { sha: "05d5dca33cdf7fa738373d95032d468151dd33ae", short_sha: "05d5dca", subject: null },
          worktree: {
            path: "/bridge-worktrees/agent-stale",
            detached: true,
            prunable: { reason: "gitdir file points to non-existent location" },
          },
        },
        {
          branch: "wip/dirty-fit-first",
          head: { sha: wipSha, short_sha: "c079643", subject: "wip(fit-first): snapshot of dirty worktree" },
          default_branch: {
            ahead: 2,
            behind: 208,
            merge_conflicts: true,
          },
        },
        {
          branch: "feat/sah-77-active",
          head: { sha: activeSha, short_sha: "9999999", subject: "feat: implement SAH-77" },
          default_branch: {
            ahead: 3,
            behind: 1,
            merge_conflicts: false,
          },
        },
      ],
      branchDiffs: {
        [wipSha]: {
          numstat: "147\t0\tinternal/optimize/source_integrity.go\n30\t10\tinternal/queue/drain.go\n",
          diff: [
            "--- /dev/null",
            "+++ b/internal/optimize/source_integrity.go",
            "+func VerifySourceIntegrity(path string) error { return nil }",
            "--- a/internal/queue/drain.go",
            "+++ b/internal/queue/drain.go",
            "+if err := checkCorruptSource(job); err != nil { return err }",
            "+return recordFailureEvent(job, err)",
          ].join("\n"),
          mergeConflicts: true,
          conflictedPaths: ["internal/queue/drain.go", "cmd/librarian/optimize.go"],
          commitSubjects: ["wip(fit-first): snapshot of dirty worktree"],
          baseTouchingLog: "340498b fix: library path in failure events (Refs ZYS-1680) (#60)\n6278fd1 fix(queue): hard byte-offset damage (ZYS-1601)\n",
        },
        [activeSha]: {
          numstat: "80\t5\tinternal/newfeat/feat.go\n",
          diff: [
            "--- /dev/null",
            "+++ b/internal/newfeat/feat.go",
            "+func RunActiveFeatureForSah77() error { return executePipeline() }",
          ].join("\n"),
          mergeConflicts: false,
          commitSubjects: ["feat: implement SAH-77"],
        },
      },
      baseFiles: {
        "internal/queue/drain.go": "package queue\nreturn recordFailureEvent(job, err)\n",
      },
      linearTickets: {
        "ZYS-1541": {
          id: "ZYS-1541",
          tracker: "linear",
          lookup_status: "found",
          title: "Stub native sidecar",
          status: "In Progress",
          status_type: "open",
          url: "https://linear.app/zys/issue/ZYS-1541",
          superseded_by: [],
        },
        "SAH-77": {
          id: "SAH-77",
          tracker: "linear",
          lookup_status: "found",
          title: "Already closed prematurely",
          status: "Done",
          status_type: "completed",
          url: "https://linear.app/sah/issue/SAH-77",
          superseded_by: [],
        },
      },
      ataskTasks: [
        {
          id: "at-4xx2tf",
          title: "Prune zachbornheimer/librarian",
          status: "ready",
          key: "prune/zachbornheimer/librarian",
        },
      ],
    });

    const out = await runAuditRepoBranches({ repo: "." }, ports);
    expect(out.summary.completed_or_redundant).toBe(3);
    expect(out.summary.superseded).toBe(1);
    expect(out.summary.should_land).toBe(1);
    expect(out.summary.tickets_out_of_date).toBe(2);
    expect(out.repo_atask_tasks.map((t) => t.id)).toEqual(["at-4xx2tf"]);

    const zysEntry = out.completed_or_redundant.find((e) => e.branch === "zys-1541-stub-native-sidecar")!;
    expect(zysEntry.ticket_drift).toBe("stale_open_ticket");
    expect(zysEntry.tickets[0]?.sync_status).toBe("stale_open_ticket");

    const wipEntry = out.superseded[0]!;
    expect(wipEntry.branch).toBe("wip/dirty-fit-first");
    expect(wipEntry.reason).toContain("ZYS-1680");
    expect(wipEntry.residual?.unlanded_new_files).toEqual(["internal/optimize/source_integrity.go"]);

    const sahEntry = out.should_land[0]!;
    expect(sahEntry.branch).toBe("feat/sah-77-active");
    expect(sahEntry.ticket_drift).toBe("ticket_closed_but_work_unlanded");

    const rendered = renderAuditReport(out);
    expect(rendered).toContain("## Should Land (1)");
    expect(rendered).toContain("## Superseded (1)");
    expect(rendered).toContain("## Completed / Redundant (3)");
    expect(rendered).toContain("ZYS-1541 [In Progress; stale_open_ticket]");
  });

  it("audits remote-only refs/remotes/origin/* branches and honors custom base_ref", async () => {
    const remoteMergedSha = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    const remoteUnmergedSha = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    const customBaseSha = "cccccccccccccccccccccccccccccccccccccccc";
    const basePorts = createFakePorts({
      branchDiffs: {
        [remoteUnmergedSha]: {
          numstat: "12\t0\tsrc/feature.ts\n",
          diff: "--- /dev/null\n+++ b/src/feature.ts\n+export const activeFeatureFlag = true;\n",
          mergeConflicts: false,
          commitSubjects: ["feat: remote-only unmerged feature"],
        },
      },
    });
    const ports: AuditRepoPorts = {
      ...basePorts,
      async gitRun(repoRoot, args, callOpts) {
        if (args[0] === "for-each-ref") {
          return {
            code: 0,
            stdout: [
              `main\t${BASE_SHA}\torigin/main\t\t2026-11-12T00:00:00Z\tmain commit\trefs/heads/main`,
              `origin/HEAD\t${BASE_SHA}\t\t\t2026-11-12T00:00:00Z\tmain commit\trefs/remotes/origin/HEAD`,
              `origin/wip-merged\t${remoteMergedSha}\t\t\t2026-11-12T01:00:00Z\twip merged\trefs/remotes/origin/wip-merged`,
              `origin/feat/remote-topic\t${remoteUnmergedSha}\t\t\t2026-11-12T02:00:00Z\tfeat: remote-only unmerged feature\trefs/remotes/origin/feat/remote-topic`,
            ].join("\n"),
            stderr: "",
          };
        }
        if (args[0] === "rev-parse" && args[1] === "--verify" && args[2] === "origin/assembled") {
          return { code: 0, stdout: `${customBaseSha}\n`, stderr: "" };
        }
        if (args[0] === "merge-base" && args[1] === "--is-ancestor") {
          const sha = args[2] ?? "";
          const target = args[3] ?? "";
          return {
            code: (sha === remoteMergedSha && target === customBaseSha) || sha === target ? 0 : 1,
            stdout: "",
            stderr: "",
          };
        }
        if (args[0] === "rev-list" && args[1] === "--left-right" && args[2] === "--count") {
          const range = args[3] ?? "";
          if (range.endsWith(`...${remoteMergedSha}`)) return { code: 0, stdout: "2\t0\n", stderr: "" };
          if (range.endsWith(`...${remoteUnmergedSha}`)) return { code: 0, stdout: "0\t1\n", stderr: "" };
        }
        return basePorts.gitRun(repoRoot, args, callOpts);
      },
    };

    const out = await runAuditRepoBranches({ repo: ".", base_ref: "origin/assembled" }, ports);
    expect(out.base_ref).toBe("origin/assembled");
    expect(out.base_sha).toBe(customBaseSha);

    const mergedEntry = out.completed_or_redundant.find((e) => e.branch === "wip-merged");
    expect(mergedEntry).toBeDefined();
    expect(mergedEntry?.recommended_action).toContain("git push origin --delete wip-merged");

    const topicEntry = out.should_land.find((e) => e.branch === "feat/remote-topic");
    expect(topicEntry).toBeDefined();
    expect(topicEntry?.upstream).toBe("origin/feat/remote-topic");
  });

  it("clones an ephemeral blobless repo when repo is a GitHub slug or absent Developer/Personal path", async () => {
    const calls: { cmd: string; args: string[] }[] = [];
    const ports = createLiveAuditRepoPorts({
      exec: async (cmd, args) => {
        calls.push({ cmd, args });
        if (cmd === "git" && args[0] === "-C" && args[2] === "rev-parse") {
          return { code: 128, stdout: "", stderr: "fatal: cannot change to '/missing'", killed: false };
        }
        if (cmd === "git" && args[0] === "clone") {
          return { code: 0, stdout: "", stderr: "", killed: false };
        }
        return { code: 0, stdout: "", stderr: "", killed: false };
      },
    });
    const root = await ports.resolveRepoRoot("zachbornheimer/oh-my-pi");
    expect(root).toContain("audit-repo-branches-");
    expect(calls.some((c) => c.cmd === "git" && c.args[0] === "clone" && c.args.includes("https://github.com/zachbornheimer/oh-my-pi.git"))).toBe(true);
    await ports.cleanup?.();
  });
});
