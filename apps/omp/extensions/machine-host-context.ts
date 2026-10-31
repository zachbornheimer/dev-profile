import os from "node:os";

type OmpUIContext = {
  notify?: (message: string, type?: "info" | "warning" | "error") => void;
  setStatus?: (key: string, text: string | undefined) => void;
};

type OmpContext = {
  hasUI?: boolean;
  ui?: OmpUIContext;
  cwd?: string;
  sessionManager?: {
    getSessionId?: () => string;
    getSessionFile?: () => string | undefined;
  };
};

type SessionSwitchEvent = {
  reason?: string;
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

export default function machineHostContext(pi: ExtensionAPI): void {
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
    const label = platform === "darwin" ? `🖥 Mac (${hostname})` : `☁️ Fleet (${hostname})`;

    return { hostname, platform, arch, homedir, role, label };
  }

  function updateFooterStatus(ctx?: OmpContext): void {
    const { label } = getHostInfo();
    ctx?.ui?.setStatus?.("host", label);
  }

  pi.on("session_start", (_event: unknown, ctx: OmpContext) => {
    updateFooterStatus(ctx);
  });

  pi.on("session_switch", (_event: unknown, ctx: OmpContext) => {
    updateFooterStatus(ctx);
  });

  pi.on("turn_start", (_event: unknown, ctx: OmpContext) => {
    updateFooterStatus(ctx);
  });

  pi.on("agent_end", (_event: unknown, ctx: OmpContext) => {
    updateFooterStatus(ctx);
  });

  pi.on("before_agent_start", (event: unknown, ctx: OmpContext) => {
    updateFooterStatus(ctx);

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
