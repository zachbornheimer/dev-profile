import os from "node:os";
import path from "node:path";
import { findScopedSettings, settings } from "@oh-my-pi/pi-coding-agent/config/settings";
import {
  cfgStatusLineLeftSegments,
  cfgStatusLinePreset,
  cfgStatusLineRightSegments,
  cfgStatusLineShowHookStatus,
} from "@oh-my-pi/pi-coding-agent/modes/settings";
import { STATUS_LINE_PRESETS } from "@oh-my-pi/pi-tui/status-line/presets";

type OmpUIContext = {
  notify?: (message: string, type?: "info" | "warning" | "error") => void;
  setStatus?: (key: string, text: string | undefined) => void;
  setTitle?: (title: string) => void;
};
type OmpContext = {
  hasUI?: boolean;
  ui?: OmpUIContext;
  cwd?: string;
  sessionManager?: {
    getSessionId?: () => string;
    getSessionFile?: () => string | undefined;
    getSessionName?: () => string | undefined;
    getCwd?: () => string | undefined;
  };
};

type BeforeAgentStartEvent = {
  type?: string;
  prompt?: string;
  images?: unknown[];
  systemPrompt?: string[];
};

type ExtensionAPI = {
  on: (
    event: string,
    handler: (event: unknown, ctx: OmpContext) => unknown,
  ) => void;
};

// Space + NBSP keeps two visible columns between the icon and label after
// omp's `sanitizeStatusText` collapses consecutive ASCII spaces.
export const ICON_GAP = " \u00a0";

export interface InlinePresetTarget {
  leftSegments: string[];
  rightSegments: string[];
}

export interface InlineSettingsHandle<T> {
  get(scope: unknown): T;
  override(scope: unknown, value: T): void;
  isConfigured?(scope: unknown): boolean;
}

export interface InlineFooterConfigDeps {
  presets: Record<string, InlinePresetTarget>;
  scope: unknown;
  preset: InlineSettingsHandle<string>;
  leftSegments: InlineSettingsHandle<readonly string[]>;
  rightSegments: InlineSettingsHandle<readonly string[]>;
  showHookStatus: InlineSettingsHandle<boolean> & { isConfigured(scope: unknown): boolean };
}

export function applyInlineFooterConfig(deps: InlineFooterConfigDeps): void {
  for (const preset of Object.values(deps.presets)) {
    if (!preset.leftSegments.includes("status") && !preset.rightSegments.includes("status")) {
      preset.leftSegments = [...preset.leftSegments, "status"];
    }
  }
  const activePreset = deps.preset.get(deps.scope);
  if (!deps.showHookStatus.isConfigured(deps.scope)) {
    deps.showHookStatus.override(deps.scope, false);
  }
  if (activePreset === "custom") {
    const left = deps.leftSegments.get(deps.scope);
    const right = deps.rightSegments.get(deps.scope);
    if (!left.includes("status") && !right.includes("status")) {
      deps.leftSegments.override(deps.scope, [...left, "status"]);
    }
  }
}

function ensureInlineFooterSettings(cwd?: string): void {
  try {
    const scope = findScopedSettings(cwd) ?? settings;
    applyInlineFooterConfig({
      presets: STATUS_LINE_PRESETS,
      scope,
      preset: cfgStatusLinePreset,
      leftSegments: cfgStatusLineLeftSegments,
      rightSegments: cfgStatusLineRightSegments,
      showHookStatus: cfgStatusLineShowHookStatus,
    });
  } catch {
    // Settings not initialized yet; presets still receive the inline status segment.
    for (const preset of Object.values(STATUS_LINE_PRESETS)) {
      if (!preset.leftSegments.includes("status") && !preset.rightSegments.includes("status")) {
        preset.leftSegments = [...preset.leftSegments, "status"];
      }
    }
  }
}

export function formatHostLabel(hostname = os.hostname(), platform = os.platform()): string {
  return platform === "darwin"
    ? `🖥${ICON_GAP}Mac (${hostname})`
    : `☁️π${ICON_GAP}Fleet (${hostname})`;
}

export function isComputeArm(platform = os.platform(), env = process.env): boolean {
  if (env.FORCE_FLEET_TITLE === "1" || env.FLEET_ARM === "1") {
    return true;
  }
  return platform === "linux" || Boolean(env.SESSIONS_DB_URL && platform === "linux");
}

export function formatTitlePrefix(platform = os.platform(), env = process.env): string {
  return isComputeArm(platform, env) ? "☁️π" : "π";
}

export function cleanTitleTask(task?: string): string | undefined {
  if (!task) return undefined;
  const stripped = task
    .replace(/^(?:☁️\s*π|π\s*☁️?|π(?:\S*|\s*\([^)]+\)))\s*[>:]\s*/u, "")
    .replace(/^🫧\s*(?:HOST:\s*)?/u, "")
    .trim();
  return stripped || undefined;
}

export function formatTerminalTitle(
  task?: string,
  platform = os.platform(),
  env = process.env,
  separator = ">"
): string {
  const prefix = formatTitlePrefix(platform, env);
  const clean = cleanTitleTask(task);
  return clean ? `${prefix} ${separator} ${clean}` : `${prefix} ${separator}`;
}

export function applyTerminalTitle(
  ctx?: OmpContext,
  platform = os.platform(),
  env = process.env
): string | undefined {
  if (!ctx?.ui?.setTitle) return undefined;
  if (!isComputeArm(platform, env)) return undefined;
  const sessionName = ctx?.sessionManager?.getSessionName?.();
  const cwd = ctx?.cwd ?? ctx?.sessionManager?.getCwd?.();
  const rawTask = sessionName || (cwd ? path.basename(path.resolve(cwd)) : undefined);
  const title = formatTerminalTitle(rawTask, platform, env);
  ctx.ui.setTitle(title);
  return title;
}

export default function machineHostContext(pi: ExtensionAPI): void {
  ensureInlineFooterSettings();

  let lastAnnouncedHost: string | undefined;

  function getHostInfo(): {
    hostname: string;
    platform: string;
    arch: string;
    homedir: string;
    role: string;
    label: string;
  } {
    const hostname = os.hostname();
    const platform = os.platform();
    const arch = os.arch();
    const homedir = os.homedir();
    const isVps = Boolean(process.env.SESSIONS_DB_URL) && platform === "linux";
    const role = isVps ? "remote-compute-arm (VPS)" : "local-front-end (Mac)";
    const label = formatHostLabel(hostname, platform);

    return { hostname, platform, arch, homedir, role, label };
  }

  function updateFooterStatus(ctx?: OmpContext): void {
    ensureInlineFooterSettings(ctx?.cwd);
    const { label } = getHostInfo();
    ctx?.ui?.setStatus?.("host", label);
  }
  function updateTitle(ctx?: OmpContext): void {
    applyTerminalTitle(ctx);
  }


  pi.on("session_start", (_event: unknown, ctx: OmpContext) => {
    updateFooterStatus(ctx);
    updateTitle(ctx);
  });

  pi.on("session_switch", (_event: unknown, ctx: OmpContext) => {
    updateFooterStatus(ctx);
    updateTitle(ctx);
  });

  pi.on("turn_start", (_event: unknown, ctx: OmpContext) => {
    updateFooterStatus(ctx);
    updateTitle(ctx);
  });

  pi.on("agent_start", (_event: unknown, ctx: OmpContext) => {
    updateTitle(ctx);
  });

  pi.on("agent_end", (_event: unknown, ctx: OmpContext) => {
    updateFooterStatus(ctx);
    updateTitle(ctx);
  });

  pi.on("before_agent_start", (event: unknown, ctx: OmpContext) => {
    updateFooterStatus(ctx);
    updateTitle(ctx);
    const { hostname, platform, arch, homedir, role } = getHostInfo();
    const hostChanged = lastAnnouncedHost !== undefined && lastAnnouncedHost !== hostname;
    const isFirstAnnouncement = lastAnnouncedHost === undefined;

    if (!isFirstAnnouncement && !hostChanged) {
      return;
    }

    const prevHost = lastAnnouncedHost;
    lastAnnouncedHost = hostname;

    const notice = `[Host Context] Running on ${hostname} (${platform}/${arch}, home=${homedir}, role=${role})${
      prevHost ? ` — switched from ${prevHost}` : ""
    }`;

    ctx.ui?.notify?.(notice, "info");

    const hostContextXml =
      `<machine_host hostname="${hostname}" platform="${platform}" arch="${arch}" homedir="${homedir}" role="${role}">\n` +
      `${notice}\n` +
      `</machine_host>`;

    const evt = event as BeforeAgentStartEvent | undefined;
    const existingSystemPrompt = Array.isArray(evt?.systemPrompt)
      ? evt?.systemPrompt
      : typeof evt?.systemPrompt === "string"
        ? [evt.systemPrompt]
        : [];

    return {
      message: notice,
      systemPrompt: [...existingSystemPrompt, hostContextXml],
    };
  });
}
