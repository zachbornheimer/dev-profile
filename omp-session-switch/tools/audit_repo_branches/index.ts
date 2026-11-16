import type { CustomToolFactory } from "@oh-my-pi/pi-coding-agent";
import { renderAuditReport, runAuditRepoBranches } from "./analyze.js";
import { applyPrune, planPrune, renderApply } from "./apply.js";
import { createLiveAuditRepoPorts } from "./live_ports.js";

export const DESCRIPTION = [
  "Audit and analyze a repository local branches and wt worktrees to see what should land, what should be superseded, and what is completed or redundant, and cross-check linked Linear (SAH/ZYS) and atask tickets to verify they are up to date.",
  "Use when reconciling or triaging a repository branches and worktrees, checking which branches still need to land vs. were already squash-merged or overtaken on the default branch, or verifying that tickets match git state.",
  "Measures ancestry, patch/tree equivalence (git cherry, git merge-tree), dirty worktree edits and untracked files against the default branch, GitHub pull request state, and linked Linear/atask ticket state.",
  "Read-only: never deletes branches, worktrees, or modifies tickets. Returns structured categories (should_land, superseded, completed_or_redundant, protected_or_unsure), per-entry ticket sync verdicts, and open repo atask tasks.",
].join(" ");

const factory: CustomToolFactory = (pi) => {
  const z = pi.zod;
  return {
    name: "audit_repo_branches",
    label: "Audit repo branches",
    description: DESCRIPTION,
    hidden: true,
    loadMode: "discoverable" as const,
    parameters: z.object({
      repo: z.string().min(1).describe("Repository path to analyze (use . for session cwd)."),
      fetch: z.boolean().nullable().optional().describe("Run git fetch --prune first. Default true."),
      check_linear: z.boolean().nullable().optional().describe("Look up linked Linear tickets (SAH/ZYS). Default true."),
      include_remote: z
        .boolean()
        .nullable()
        .optional()
        .describe("Include remote-only refs/remotes/origin/* branches that have no local refs/heads/* branch. Default true."),
      base_ref: z
        .string()
        .nullable()
        .optional()
        .describe("Optional base ref override to audit against (e.g. origin/assembled or origin/main)."),
      prune: z
        .enum(["plan", "apply"])
        .nullable()
        .optional()
        .describe(
          "Act on completed_or_redundant entries: `plan` lists the removals, `apply` runs them (wt remove -D for local branches and worktrees, one batched git push origin --delete for remote-only refs). Skips the base branch, open PRs and dirty worktrees. Omit to audit only.",
        ),
    }),

    async execute(_toolCallId, params, onUpdate, _ctx, signal) {
      const beat = setInterval(() => {
        onUpdate?.({
          content: [{ type: "text", text: "audit_repo_branches is analyzing branches, worktrees, and tickets" }],
          details: { status: "running" },
        });
      }, 10_000);
      const ports = createLiveAuditRepoPorts({ exec: pi.exec, cwd: pi.cwd });
      try {
        const output = await runAuditRepoBranches(
          {
            repo: params.repo,
            fetch: params.fetch ?? undefined,
            check_linear: params.check_linear ?? undefined,
            include_remote: params.include_remote ?? undefined,
            base_ref: params.base_ref ?? undefined,
          },
          ports,
          signal,
        );
        let text = renderAuditReport(output);
        if (params.prune) {
          text = `${text}\n\n${renderApply(await applyPrune(ports, output.repo, planPrune(output), params.prune === "apply", signal))}`;
        }
        return {
          content: [{ type: "text", text }],
          details: output,
        };
      } finally {
        clearInterval(beat);
        await ports.cleanup?.();
      }
    },
  };
};

export default factory;
