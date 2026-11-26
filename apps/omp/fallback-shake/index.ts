import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";
import {
  MAX_THINKING_SUFFIX_OPTIONS,
  parseModelString,
  splitUpstreamRouting,
} from "@oh-my-pi/pi-tui/overlays/model-selector";
import { fallbackNotice, shouldShakeFallback } from "./rule";

/** Retry delivery must never wait for artifact I/O or the persisted history rewrite. */
export default function fallbackShake(pi: ExtensionAPI): void {
  let pending: AbortController | undefined;
  let cancelScheduled: (() => void) | undefined;
  const reports: Array<{ message: string; level: "info" | "warning" }> = [];
  pi.on("agent_start", (_event, ctx) => {
    for (const report of reports.splice(0)) ctx.ui?.notify?.(report.message, report.level);
  });
  pi.on("session_shutdown", () => {
    cancelScheduled?.();
    cancelScheduled = undefined;
    pending?.abort();
    pending = undefined;
    reports.length = 0;
  });
  pi.on("retry_fallback_applied", (event, ctx) => {
    const parseOptions = {
      ...MAX_THINKING_SUFFIX_OPTIONS,
      isLiteralModelId: (provider: string, id: string) => ctx.modelRegistry.find(provider, id) !== undefined,
    };
    const resolveIdentity = (selector: string) => {
      const parsed = parseModelString(selector, parseOptions);
      return (
        (parsed && ctx.modelRegistry.find(parsed.provider, parsed.id))
          ?? ctx.models.resolve(selector)
          ?? parseModelString(splitUpstreamRouting(selector)?.base ?? selector, parseOptions)
      );
    };
    const from = resolveIdentity(event.from);
    const to = resolveIdentity(event.to);
    const observation = { agentKind: ctx.agent.kind, target: event.target, from, to, current: ctx.model };
    const notice = fallbackNotice(from, to);
    if (notice) ctx.ui?.notify?.(notice, "warning");
    if (!shouldShakeFallback(observation) || pending) return;

    const controller = new AbortController();
    pending = controller;
    // A macrotask also moves shake's synchronous token-counting prefix outside
    // the handler. The host guards the rewrite against leaf/model changes.
    const timer = ctx.setTimeout(() => {
      cancelScheduled = undefined;
      void (async () => {
        try {
          if (controller.signal.aborted) return;
          if (!shouldShakeFallback({ ...observation, current: ctx.model })) {
            reports.push({
              message: "fallback shake skipped: model changed before background work started",
              level: "warning",
            });
            return;
          }
          const result = await ctx.shake({ protectTurns: 6, signal: controller.signal });
          reports.push({ message: `fallback shake completed: ${result.tokensFreed} tokens freed`, level: "info" });
        } catch (error) {
          if (!controller.signal.aborted) {
            reports.push({
              message: `fallback shake failed: ${error instanceof Error ? error.message : String(error)}`,
              level: "warning",
            });
          }
        } finally {
          if (pending === controller) pending = undefined;
        }
      })();
    }, 0);
    cancelScheduled = () => ctx.clearTimer(timer);
  });
}
