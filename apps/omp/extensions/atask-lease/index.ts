import { execFile } from "node:child_process";
import { type LeaseHost, type LeaseOptions, type LeaseOwner, type LeaseReport, ownLease } from "./lease";

export type { LeaseContext, LeaseHost, LeaseOptions, LeaseOwner, LeaseReport, LeaseTimer } from "./lease";

const RENEW_TIMEOUT_MS = 10_000;
const MAX_OUTPUT_BYTES = 64 * 1024;

export function renewRuntime(owner: LeaseOwner, root: string): Promise<number> {
  const { promise, resolve, reject } = Promise.withResolvers<number>();
  execFile("atask", ["--json", "claim", "renew", "--runtime"], {
    cwd: owner.cwd,
    env: { ...process.env, ATASK_RUNTIME_ROOT: root, PI_SESSION_ID: owner.session, ATASK_SESSION: "" },
    timeout: RENEW_TIMEOUT_MS,
    killSignal: "SIGKILL",
    maxBuffer: MAX_OUTPUT_BYTES,
    encoding: "utf8",
  }, (error, stdout) => {
    if (error) {
      reject(new Error("atask runtime renewal failed"));
      return;
    }
    try {
      const response: unknown = JSON.parse(stdout);
      if (
        !response || typeof response !== "object" || !("ok" in response) || response.ok !== true
        || !("result" in response) || !response.result || typeof response.result !== "object"
        || !("renewed" in response.result) || typeof response.result.renewed !== "number"
        || !Number.isSafeInteger(response.result.renewed) || response.result.renewed < 0
      ) {
        throw new Error("Invalid atask runtime renewal response");
      }
      resolve(response.result.renewed);
    } catch {
      reject(new Error("Invalid atask runtime renewal response"));
    }
  });
  return promise;
}

function report(event: LeaseReport): void {
  if (event.kind === "failed") console.error(`[atask-lease] stopped: ${event.reason}`);
  else console.error(`[atask-lease] renewed ${event.count}`);
}

export function registerLease(host: LeaseHost, options: Partial<LeaseOptions> = {}): () => void {
  return ownLease(host, { ...options, renew: options.renew ?? renewRuntime, report: options.report ?? report });
}

export default registerLease;
