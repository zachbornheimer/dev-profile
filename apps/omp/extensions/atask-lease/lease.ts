import { type Registration, Registry, runtimeRegistry } from "./registry";

export type LeaseOwner = Readonly<{ session: string; cwd: string }>;
export type LeaseTimer = Timer;
export interface LeaseContext {
  hasUI: boolean;
  cwd: string;
  agent: { kind: string };
  sessionManager: { getSessionId(): string | undefined };
  setInterval(callback: () => void, intervalMs: number): LeaseTimer;
  clearTimer(timer: LeaseTimer): void;
}
export interface LeaseHost {
  on(event: string, handler: (event: unknown, ctx: LeaseContext) => void): void;
}
export type LeaseReport =
  | { kind: "renewed"; count: number }
  | { kind: "failed"; reason: "registration" | "renewal" | "cleanup" };
export interface LeaseOptions {
  intervalMs?: number;
  renew(owner: LeaseOwner, root: string): Promise<number>;
  report(event: LeaseReport): void;
  registry?: Registry;
}
const RENEW_INTERVAL_MS = 60_000;
type Activation = {
  owner: LeaseOwner;
  registration: Registration;
  ctx: LeaseContext;
  timer?: LeaseTimer;
  busy: boolean;
};

export function ownLease(host: LeaseHost, options: LeaseOptions): () => void {
  const registry = options.registry ?? runtimeRegistry;
  const intervalMs = options.intervalMs ?? RENEW_INTERVAL_MS;
  let active: Activation | undefined;
  let failedSession: string | undefined;
  let stopped = false;

  function cleanup(): void {
    const previous = active;
    active = undefined;
    if (!previous) return;
    if (previous.timer !== undefined) previous.ctx.clearTimer(previous.timer);
    try {
      registry.revoke(previous.registration);
    } catch {
      options.report({ kind: "failed", reason: "cleanup" });
    }
  }

  async function tick(activation: Activation): Promise<void> {
    if (active !== activation || activation.busy) return;
    activation.busy = true;
    try {
      const count = await options.renew(activation.owner, registry.root);
      if (active !== activation) return;
      if (!Number.isSafeInteger(count) || count < 0) throw new Error("Invalid renewal count");
      if (count > 0) options.report({ kind: "renewed", count });
    } catch {
      if (active !== activation) return;
      failedSession = activation.owner.session;
      cleanup();
      options.report({ kind: "failed", reason: "renewal" });
    } finally {
      activation.busy = false;
    }
  }

  function start(ctx: LeaseContext): void {
    if (stopped) return;
    if (ctx.hasUI !== true || ctx.agent?.kind !== "main") {
      cleanup();
      return;
    }
    const session = ctx.sessionManager.getSessionId();
    if (!session) {
      cleanup();
      return;
    }
    if (active?.owner.session === session || failedSession === session) return;
    cleanup();
    failedSession = undefined;
    try {
      const registration = registry.activate(session);
      if (!registration) return;
      const activation: Activation = {
        owner: Object.freeze({ session, cwd: ctx.cwd }),
        registration,
        ctx,
        busy: false,
      };
      active = activation;
      process.env.ATASK_RUNTIME_ROOT = registry.root;
      activation.timer = ctx.setInterval(() => {
        void tick(activation);
      }, intervalMs);
    } catch {
      failedSession = session;
      cleanup();
      options.report({ kind: "failed", reason: "registration" });
    }
  }

  host.on("session_start", (_event, ctx) => start(ctx));
  for (const event of ["session_switch", "session_branch"]) {
    host.on(event, (_event, ctx) => {
      cleanup();
      failedSession = undefined;
      start(ctx);
    });
  }
  const stop = () => {
    stopped = true;
    cleanup();
  };
  host.on("session_shutdown", stop);
  return stop;
}
