import { describe, expect, it } from "bun:test";
import { applyPrune, planPrune } from "./apply.js";
import type { AnalyzedEntry, AuditRepoBranchesOutput, AuditRepoPorts } from "./types.js";

const entry = (over: Partial<AnalyzedEntry> & { branch: string | null }): AnalyzedEntry =>
  ({
    id: over.branch ?? "detached",
    sha: "a",
    short_sha: "a",
    reason: "ancestor of base",
    recommended_action: `wt remove --foreground -D --yes ${over.branch}`,
    worktree: null,
    pr: null,
    verdict: "completed_or_redundant",
    ...over,
  }) as AnalyzedEntry;

const output = (entries: AnalyzedEntry[]): AuditRepoBranchesOutput =>
  ({ repo: "/r", default_branch: "main", base_ref: "origin/assembled", completed_or_redundant: entries }) as unknown as AuditRepoBranchesOutput;

describe("planPrune", () => {
  it("removes redundant local and remote branches but never the base, open-PR, dirty or nameless entries", () => {
    const plan = planPrune(output([
      entry({ branch: "feat/done" }),
      entry({ branch: "old", recommended_action: "git push origin --delete old" }),
      entry({ branch: "main" }),
      entry({ branch: "assembled" }),
      entry({ branch: "feat/pr", pr: { state: "OPEN", number: 7 } as AnalyzedEntry["pr"] }),
      entry({ branch: "feat/dirty", worktree: { path: "/w", main: false, dirty: { real_paths: ["a.ts"] } } as AnalyzedEntry["worktree"] }),
      entry({ branch: null }),
    ]));
    expect(plan.actions.map((a) => `${a.kind}:${a.branch}`)).toEqual(["remove_local:feat/done", "delete_remote:old"]);
    expect(plan.skipped.map((s) => s.id)).toEqual(["main", "assembled", "feat/pr", "feat/dirty", "detached"]);
  });
});

describe("applyPrune", () => {
  const fake = () => {
    const calls: string[] = [];
    const ports = {
      wtRemove: async (_r: string, b: string) => {
        calls.push(`wt ${b}`);
        return b === "bad" ? { code: 1, stdout: "", stderr: "locked" } : { code: 0, stdout: "", stderr: "" };
      },
      gitRun: async (_r: string, args: readonly string[]) => {
        calls.push(`git ${args.join(" ")}`);
        return { code: 0, stdout: "", stderr: "" };
      },
    } as unknown as AuditRepoPorts;
    return { ports, calls };
  };
  const plan = planPrune(output([
    entry({ branch: "a" }),
    entry({ branch: "bad" }),
    entry({ branch: "r1", recommended_action: "git push origin --delete r1" }),
    entry({ branch: "r2", recommended_action: "git push origin --delete r2" }),
  ]));

  it("does nothing unless apply is set", async () => {
    const { ports, calls } = fake();
    const res = await applyPrune(ports, "/r", plan, false);
    expect(res.applied).toBe(false);
    expect(calls).toEqual([]);
  });

  it("removes locals one by one, batches remote deletes into one push, and reports failures", async () => {
    const { ports, calls } = fake();
    const res = await applyPrune(ports, "/r", plan, true);
    expect(calls).toEqual(["wt a", "wt bad", "git push --no-verify origin --delete r1 r2"]);
    expect(res.done).toEqual(["removed a", "deleted origin/r1", "deleted origin/r2"]);
    expect(res.failed).toEqual([{ id: "bad", why: "locked" }]);
  });
});
