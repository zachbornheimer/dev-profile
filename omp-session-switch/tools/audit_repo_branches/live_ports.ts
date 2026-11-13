import { existsSync, mkdtempSync, readFileSync, rmSync, statSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";
import { classifyLinearStatusType } from "./tickets.js";
import type {
  AtaskRawTask,
  AuditRepoPorts,
  PullRequestInfo,
  RawTicketRecord,
  WtListEnvelope,
} from "./types.js";

export type ExecFn = (
  command: string,
  args: string[],
  options?: { signal?: AbortSignal; timeout?: number; cwd?: string },
) => Promise<{ stdout: string; stderr: string; code: number; killed: boolean }>;

const GIT_TIMEOUT_MS = 30_000;
const WT_TIMEOUT_MS = 45_000;
const GH_TIMEOUT_MS = 45_000;
const ATASK_TIMEOUT_MS = 20_000;
const LINEAR_TIMEOUT_MS = 15_000;
const MAX_UNTRACKED_FILE_BYTES = 512 * 1024;
const DEFAULT_GATEWAY_URL = "http://mcp-gateway.tail158749.ts.net:4600/mcp";

function readKeyFromEnvFile(filePath: string, keyName: string): string | undefined {
  try {
    const raw = readFileSync(filePath, "utf8");
    for (const line of raw.split(/\r?\n/)) {
      const m = new RegExp(`^(?:export\\s+)?${keyName}=(.+)$`).exec(line.trim());
      if (m?.[1]) {
        const val = m[1].trim().replace(/^["']|["']$/g, "");
        if (val && !val.startsWith("op://")) return val;
      }
    }
  } catch {
    // Ignore absent file.
  }
  return undefined;
}

function resolveLinearApiKey(team: string, env: Readonly<Record<string, string | undefined>>): string | undefined {
  const teamKey = `LINEAR_API_KEY_${team.toUpperCase()}`;
  const direct = env[teamKey]?.trim() || env.LINEAR_API_KEY?.trim();
  if (direct) return direct;
  const home = homedir();
  for (const file of [
    join(home, ".cache", "ai", "keys.env"),
    join(home, ".config", "linear-triage", ".env"),
  ]) {
    const k = readKeyFromEnvFile(file, teamKey) ?? readKeyFromEnvFile(file, "LINEAR_API_KEY");
    if (k) return k;
  }
  return undefined;
}

async function queryLinearGraphql(
  apiKey: string,
  ticketId: string,
  fetchImpl: typeof fetch,
  signal?: AbortSignal,
): Promise<RawTicketRecord> {
  const auth = /^bearer\s/i.test(apiKey)
    ? apiKey
    : apiKey.startsWith("lin_oauth_")
    ? `Bearer ${apiKey}`
    : apiKey;
  const timeoutSignal = signal
    ? AbortSignal.any([signal, AbortSignal.timeout(LINEAR_TIMEOUT_MS)])
    : AbortSignal.timeout(LINEAR_TIMEOUT_MS);
  const res = await fetchImpl("https://api.linear.app/graphql", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: auth,
    },
    body: JSON.stringify({
      query: `query($id: String!) { issue(id: $id) { identifier title url state { name type } relations { nodes { type relatedIssue { identifier } } } } }`,
      variables: { id: ticketId },
    }),
    signal: timeoutSignal,
  });
  const text = await res.text();
  if (!res.ok) {
    throw new Error(`Linear GraphQL HTTP ${res.status}: ${text.slice(0, 200)}`);
  }
  const parsed = JSON.parse(text) as {
    data?: {
      issue?: {
        identifier?: string;
        title?: string;
        url?: string;
        state?: { name?: string; type?: string };
        relations?: { nodes?: { type?: string; relatedIssue?: { identifier?: string } }[] };
      } | null;
    };
    errors?: { message?: string }[];
  };
  if (parsed.errors && parsed.errors.length > 0) {
    throw new Error(parsed.errors.map((e) => e.message ?? "error").join("; "));
  }
  const issue = parsed.data?.issue;
  if (!issue) {
    return {
      id: ticketId,
      tracker: "linear",
      lookup_status: "not_found",
      title: null,
      status: null,
      status_type: "unknown",
      url: null,
      superseded_by: [],
      error_detail: `Linear issue ${ticketId} not found`,
    };
  }
  const supersededBy = (issue.relations?.nodes ?? [])
    .filter((r) => r.type === "duplicate" && r.relatedIssue?.identifier)
    .map((r) => r.relatedIssue!.identifier!);
  const stateName = issue.state?.name ?? null;
  const stateType = issue.state?.type ?? null;
  return {
    id: issue.identifier ?? ticketId,
    tracker: "linear",
    lookup_status: "found",
    title: issue.title ?? null,
    status: stateName,
    status_type: classifyLinearStatusType(stateType, stateName),
    url: issue.url ?? null,
    superseded_by: supersededBy,
  };
}

async function queryLinearViaMcpGateway(
  team: string,
  ticketId: string,
  exec: ExecFn,
  fetchImpl: typeof fetch,
  env: Readonly<Record<string, string | undefined>>,
  signal?: AbortSignal,
): Promise<RawTicketRecord> {
  const server = team.toUpperCase() === "SAH" ? "linear-sah" : "linear-personal";
  const opItem = team.toUpperCase() === "SAH" ? "MCP: Linear SAH" : "MCP: Linear Personal";
  let token = env.CAPABILITY_GATEWAY_TOKEN?.trim();
  if (!token) {
    const kc = await exec(
      "/usr/bin/security",
      ["find-generic-password", "-s", "capability-gateway", "-a", "token", "-w"],
      { timeout: 5_000, signal },
    );
    if (kc.code === 0 && kc.stdout.trim()) token = kc.stdout.trim();
  }
  if (!token) {
    throw new Error(`no Linear API key or capability-gateway token for ${ticketId}`);
  }
  const gatewayUrl = env.CAPABILITY_GATEWAY_URL?.trim() || DEFAULT_GATEWAY_URL;
  const timeoutSignal = signal
    ? AbortSignal.any([signal, AbortSignal.timeout(LINEAR_TIMEOUT_MS)])
    : AbortSignal.timeout(LINEAR_TIMEOUT_MS);
  const res = await fetchImpl(gatewayUrl, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      Accept: "application/json, text/event-stream",
    },
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: 1,
      method: "tools/call",
      params: {
        name: `${server}_get_issue`,
        arguments: { id: ticketId },
      },
    }),
    signal: timeoutSignal,
  });
  const raw = await res.text();
  if (!res.ok) {
    const detail = raw.trim().slice(0, 140);
    throw new Error(
      `Linear workspace ${team.toUpperCase()} (${server}) returned HTTP ${res.status}${detail ? `: ${detail}` : ""}; check op://Agent Gateway/${opItem}/credential`,
    );
  }
  const dataLine = raw.trim().startsWith("{")
    ? raw.trim()
    : raw
        .split("\n")
        .map((l) => l.trim())
        .find((l) => l.startsWith("data:"))
        ?.slice(5)
        .trim();
  if (!dataLine) throw new Error(`empty MCP gateway response for ${ticketId}`);
  const rpc = JSON.parse(dataLine) as {
    error?: { message?: string };
    result?: { isError?: boolean; content?: { type?: string; text?: string }[]; structuredContent?: unknown };
  };
  if (rpc.error) {
    const msg = rpc.error.message ?? `MCP error for ${ticketId}`;
    if (/HTTP 401/i.test(msg)) {
      throw new Error(
        `${server} upstream token on mcp-gateway returned HTTP 401; check op://Agent Gateway/${opItem}/credential`,
      );
    }
    throw new Error(msg);
  }
  if (rpc.result?.isError) {
    const errText = rpc.result.content?.find((c) => c.type === "text")?.text ?? "MCP tool error";
    throw new Error(errText);
  }
  const bodyText = rpc.result?.content?.find((c) => c.type === "text")?.text ?? "";
  const issue = (rpc.result?.structuredContent ?? (bodyText ? JSON.parse(bodyText) : null)) as Record<string, unknown> | null;
  if (!issue || typeof issue !== "object") {
    throw new Error(`no issue data returned for ${ticketId}`);
  }
  const stateObj = typeof issue.state === "object" && issue.state !== null
    ? (issue.state as Record<string, unknown>)
    : null;
  const status = typeof issue.status === "string"
    ? issue.status
    : typeof stateObj?.name === "string"
    ? stateObj.name
    : null;
  const statusTypeRaw = typeof issue.statusType === "string"
    ? issue.statusType
    : typeof stateObj?.type === "string"
    ? stateObj.type
    : null;
  return {
    id: typeof issue.identifier === "string" ? issue.identifier : ticketId,
    tracker: "linear",
    lookup_status: "found",
    title: typeof issue.title === "string" ? issue.title : null,
    status,
    status_type: classifyLinearStatusType(statusTypeRaw, status),
    url: typeof issue.url === "string" ? issue.url : null,
    superseded_by: [],
  };
}

export function createLiveAuditRepoPorts(options: {
  exec: ExecFn;
  cwd?: string;
  env?: Readonly<Record<string, string | undefined>>;
  fetchImpl?: typeof fetch;
}): AuditRepoPorts {
  const { exec, cwd } = options;
  const env = options.env ?? process.env;
  const fetchImpl = options.fetchImpl ?? fetch;
  const tempDirs: string[] = [];

  function inferRemoteUrl(target: string): string | null {
    if (/^(?:https?:\/\/|git@|ssh:\/\/)/.test(target)) return target;
    if (/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(target) && !existsSync(target)) {
      return `https://github.com/${target.replace(/\.git$/, "")}.git`;
    }
    const personalMatch = /\/Developer\/Personal\/([A-Za-z0-9_.-]+)\/?$/.exec(target);
    if (personalMatch?.[1]) {
      return `https://github.com/zachbornheimer/${personalMatch[1]}.git`;
    }
    const sahMatch = /\/Developer\/Software-Automation-Holdings\/([A-Za-z0-9_.-]+)\/?$/.exec(target);
    if (sahMatch?.[1]) {
      return `https://github.com/Software-Automation-Holdings/${sahMatch[1]}.git`;
    }
    return null;
  }

  return {
    async resolveRepoRoot(repo, signal) {
      const rawTarget = repo === "." && cwd ? cwd : repo.trim();
      const target = rawTarget.startsWith("~/") ? join(homedir(), rawTarget.slice(2)) : rawTarget;
      const res = await exec("git", ["-C", target, "rev-parse", "--show-toplevel"], {
        timeout: GIT_TIMEOUT_MS,
        signal,
      });
      if (res.code === 0 && res.stdout.trim()) {
        return res.stdout.trim();
      }
      const remoteUrl = inferRemoteUrl(target);
      if (remoteUrl) {
        const tempDir = mkdtempSync(join(tmpdir(), "audit-repo-branches-"));
        tempDirs.push(tempDir);
        const cloneRes = await exec(
          "git",
          ["clone", "--quiet", "--no-checkout", "--filter=blob:none", remoteUrl, tempDir],
          { timeout: 60_000, signal },
        );
        if (cloneRes.code === 0) {
          const headSym = await exec("git", ["-C", tempDir, "symbolic-ref", "--short", "HEAD"], {
            timeout: GIT_TIMEOUT_MS,
            signal,
          });
          await exec("git", ["-C", tempDir, "symbolic-ref", "HEAD", "refs/heads/__ephemeral_audit__"], {
            timeout: GIT_TIMEOUT_MS,
            signal,
          });
          if (headSym.code === 0 && headSym.stdout.trim()) {
            await exec("git", ["-C", tempDir, "branch", "-D", headSym.stdout.trim()], {
              timeout: GIT_TIMEOUT_MS,
              signal,
            });
          }
          return tempDir;
        }
        throw new Error(`cannot clone remote repository "${remoteUrl}": ${cloneRes.stderr.trim() || `exit ${cloneRes.code}`}`);
      }
      throw new Error(`cannot resolve git repository at "${target}": ${res.stderr.trim() || `exit ${res.code}`}`);
    },

    async cleanup() {
      while (tempDirs.length > 0) {
        const dir = tempDirs.pop();
        if (dir) {
          try {
            rmSync(dir, { recursive: true, force: true });
          } catch {
            // Ignore cleanup failure.
          }
        }
      }
    },

    async fetchPrune(repoRoot, signal) {
      const res = await exec("git", ["-C", repoRoot, "fetch", "--prune", "--quiet"], {
        timeout: GIT_TIMEOUT_MS,
        signal,
      });
      if (res.code === 0) return { status: "ok", detail: "" };
      return { status: "failed", detail: res.stderr.trim() || `exit ${res.code}` };
    },

    async resolveBase(repoRoot, wtDefaultBranch, signal) {
      const sym = await exec(
        "git",
        ["-C", repoRoot, "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
        { timeout: GIT_TIMEOUT_MS, signal },
      );
      if (sym.code === 0 && sym.stdout.trim()) {
        const ref = sym.stdout.trim();
        const ver = await exec("git", ["-C", repoRoot, "rev-parse", "--verify", ref], {
          timeout: GIT_TIMEOUT_MS,
          signal,
        });
        if (ver.code === 0 && ver.stdout.trim()) {
          const defaultBranch = ref.includes("/") ? ref.split("/").slice(1).join("/") : ref;
          return { defaultBranch, baseRef: ref, baseSha: ver.stdout.trim() };
        }
      }

      const candidates = [
        ...(wtDefaultBranch ? [`origin/${wtDefaultBranch}`, wtDefaultBranch] : []),
        "origin/main",
        "origin/master",
        "main",
        "master",
      ];
      for (const candidate of candidates) {
        const ver = await exec("git", ["-C", repoRoot, "rev-parse", "--verify", candidate], {
          timeout: GIT_TIMEOUT_MS,
          signal,
        });
        if (ver.code === 0 && ver.stdout.trim()) {
          const defaultBranch = candidate.startsWith("origin/") ? candidate.slice("origin/".length) : candidate;
          return { defaultBranch, baseRef: candidate, baseSha: ver.stdout.trim() };
        }
      }
      throw new Error(`cannot resolve default branch for repository ${repoRoot}`);
    },

    async listWtItems(repoRoot, signal) {
      const res = await exec("wt", ["-C", repoRoot, "list", "--branches", "--format=json"], {
        timeout: WT_TIMEOUT_MS,
        signal,
      });
      if (res.code === 0 && res.stdout.trim()) {
        const parsed = JSON.parse(res.stdout) as WtListEnvelope | WtListEnvelope["items"];
        if (Array.isArray(parsed)) {
          return { items: parsed };
        }
        return parsed;
      }
      return { items: [] };
    },

    async listPullRequests(repoRoot, signal) {
      const res = await exec(
        "gh",
        [
          "pr",
          "list",
          "--state",
          "all",
          "--limit",
          "300",
          "--json",
          "number,title,body,state,headRefName,headRefOid,url,mergedAt",
        ],
        { cwd: repoRoot, timeout: GH_TIMEOUT_MS, signal },
      );
      if (res.code !== 0) {
        return {
          prs: [],
          status: "unavailable",
          detail: res.stderr.trim() || `gh pr list exited ${res.code}`,
        };
      }
      try {
        const raw = JSON.parse(res.stdout) as Record<string, unknown>[];
        if (!Array.isArray(raw)) {
          return { prs: [], status: "unavailable", detail: "gh pr list returned non-array JSON" };
        }
        const prs: PullRequestInfo[] = raw.map((r) => ({
          number: typeof r.number === "number" ? r.number : 0,
          state: r.state === "OPEN" || r.state === "MERGED" || r.state === "CLOSED" ? r.state : "CLOSED",
          title: typeof r.title === "string" ? r.title : "",
          body: typeof r.body === "string" ? r.body : "",
          url: typeof r.url === "string" ? r.url : "",
          head_ref: typeof r.headRefName === "string" ? r.headRefName : "",
          head_sha: typeof r.headRefOid === "string" ? r.headRefOid : "",
          merged_at: typeof r.mergedAt === "string" ? r.mergedAt : null,
        }));
        return { prs, status: "ok", detail: "" };
      } catch (err) {
        return {
          prs: [],
          status: "unavailable",
          detail: `invalid JSON from gh pr list: ${(err as Error).message}`,
        };
      }
    },

    async gitRun(repoRoot, args, opts) {
      const targetCwd = opts?.cwd ?? repoRoot;
      const res = await exec("git", ["-C", targetCwd, ...args], {
        timeout: GIT_TIMEOUT_MS,
        signal: opts?.signal,
      });
      return { code: res.code, stdout: res.stdout, stderr: res.stderr };
    },

    async readWorktreeFile(worktreePath, relPath) {
      try {
        const full = join(worktreePath, relPath);
        const st = statSync(full);
        if (!st.isFile() || st.size > MAX_UNTRACKED_FILE_BYTES) return null;
        return await readFile(full, "utf8");
      } catch {
        return null;
      }
    },

    async pathExists(absPath) {
      return existsSync(absPath);
    },

    async listAtaskTasks(signal) {
      const res = await exec("atask", ["list", "--json"], {
        timeout: ATASK_TIMEOUT_MS,
        signal,
      });
      if (res.code !== 0 || !res.stdout.trim()) return [];
      try {
        const parsed = JSON.parse(res.stdout) as {
          ok?: boolean;
          result?: { tasks?: AtaskRawTask[] };
        };
        return Array.isArray(parsed.result?.tasks) ? parsed.result.tasks : [];
      } catch {
        return [];
      }
    },

    async lookupLinearTicket(ticketId, signal) {
      const team = ticketId.split("-")[0]?.toUpperCase() ?? "";
      const apiKey = resolveLinearApiKey(team, env);
      if (apiKey) {
        try {
          return await queryLinearGraphql(apiKey, ticketId, fetchImpl, signal);
        } catch {
          // Fall through to MCP gateway lookup.
        }
      }
      try {
        return await queryLinearViaMcpGateway(team, ticketId, exec, fetchImpl, env, signal);
      } catch (err) {
        return {
          id: ticketId,
          tracker: "linear",
          lookup_status: "unverified",
          title: null,
          status: null,
          status_type: "unknown",
          url: null,
          superseded_by: [],
          error_detail: err instanceof Error ? err.message : String(err),
        };
      }
    },
  };
}
