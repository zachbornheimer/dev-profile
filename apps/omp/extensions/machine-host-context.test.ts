import { stripVTControlCharacters } from "node:util";
import { describe, expect, it } from "bun:test";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Dynamic imports below resolve the sibling oh-my-pi checkout from `os.homedir()`
// so this test runs from both `~/Developer/Personal/dev-profile` and git worktrees
// under `~/Developer/Personal/.worktrees/<slug>` (where `../` depth differs).
const ompRoot = path.join(os.homedir(), "Developer/Personal/oh-my-pi/packages");
const extPath = fileURLToPath(new URL("./machine-host-context.ts", import.meta.url));

describe("machine-host-context footer status", () => {
  it("renders the Mac icon with an additional space inline with the other footer items on one line", async () => {
    const { resetSettingsForTest, Settings } = await import(
      path.join(ompRoot, "coding-agent/src/config/settings.ts")
    );
    const { StatusLineComponent } = await import(path.join(ompRoot, "tui/src/status-line/index.ts"));
    const { statusLineHost } = await import(
      path.join(ompRoot, "coding-agent/src/modes/status-line-host.ts")
    );
    const { initTheme } = await import(path.join(ompRoot, "tui/src/theme/index.ts"));
    const { loadExtensions } = await import(
      path.join(ompRoot, "coding-agent/src/extensibility/extensions/loader.ts")
    );

    resetSettingsForTest();
    await Settings.init({ inMemory: true });
    await initTheme(false, "nerd");

    const loaded = await loadExtensions([extPath], process.cwd());
    expect(loaded.errors).toEqual([]);
    expect(loaded.extensions).toHaveLength(1);

    const messages: never[] = [];
    const model = {
      id: "gemini-4-argon",
      name: "Gemini 4 Argon",
      provider: "google-antigravity",
      api: "google-antigravity" as const,
      baseUrl: "https://example.invalid",
      reasoning: true,
      thinking: { minLevel: "low" as const, maxLevel: "high" as const },
      input: ["text" as const],
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
      contextWindow: 1_000_000,
      maxTokens: 32_000,
    };
    const session = {
      state: { messages, model },
      messages,
      model,
      isStreaming: false,
      isAutoThinking: true,
      autoResolvedThinkingLevel: () => undefined,
      isFastModeActive: () => false,
      getAdvisorStatusOverview: () => ({ configured: false, advisors: [] }),
      getAsyncJobSnapshot: () => ({ running: [] }),
      settings: Settings.instance,
      modelRegistry: { isUsingOAuth: () => false },
      sessionManager: {
        getSessionName: () => undefined,
        getSessionId: () => "test-session",
        getUsageStatistics: () => ({
          input: 0,
          output: 0,
          cacheRead: 0,
          cacheWrite: 0,
          totalTokens: 0,
          orchestrationInput: 0,
          orchestrationOutput: 0,
          orchestrationCacheRead: 0,
          premiumRequests: 0,
          cost: 0,
        }),
      },
      getContextUsage: () => ({ tokens: 30_000, contextWindow: 1_000_000, percent: 3 }),
    };

    const statusLine = new StatusLineComponent(session, statusLineHost);
    statusLine.setComposerStyle({
      statusAttachment: "top-rule-chip",
      bottomBar: "left",
      bottomBarGap: false,
    });

    try {
      const ext = loaded.extensions[0]!;
      const startHandlers = ext.handlers.get("session_start") ?? [];
      let statusValue: string | undefined;
      // Minimal ExtensionContext double for session_start handler dispatch.
      const fakeCtx = {
        cwd: process.cwd(),
        hasUI: true,
        ui: {
          setStatus: (key: string, text: string | undefined) => {
            if (key === "host") statusValue = text;
            statusLine.setHookStatus(key, text);
          },
        },
      } as unknown as Parameters<(typeof startHandlers)[number]>[1];

      for (const handler of startHandlers) {
        await handler({ type: "session_start" }, fakeCtx);
      }

      statusLine.updateSettings(statusLineHost.getSettings());

      expect(statusValue).toBeDefined();
      const lines = statusLine.render(160).map((line: string) => stripVTControlCharacters(line));
      expect(lines).toHaveLength(1);
      expect(lines[0]).toContain("Gemini 4 Argon");
      expect(lines[0]).toMatch(/🖥 \u00a0Mac \(/);
    } finally {
      statusLine.dispose();
      resetSettingsForTest();
    }
  });
});
