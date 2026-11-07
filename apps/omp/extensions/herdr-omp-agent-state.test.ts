// The remote omp extension has to tell the Mac's Herdr how to reattach a remote
// session: a Herdr restart re-runs that command in the restored pane, and the
// box's own `omp --resume <path>` names a /home path the Mac cannot open.
//
// These tests drive the real extension export against a fake Herdr socket.
import { afterAll, expect, test } from "bun:test";
import net from "node:net";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

const SESSION_ID = "01a1a3d7-875b-71b2-9785-71c116141a8f";
const SESSION_PATH = `/home/zbornheimer/.omp/agent/sessions/-home-zbornheimer-D-P-dev-env/2026-11-03T23-56-13-531Z_${SESSION_ID}.jsonl`;
const PANE_ID = "w9:p9";
// dev-env's vps:* tasks report through the Mac's socket under the local fg
// hook's source; that is the only producer of this value.
const FORWARDED_SOURCE = "zsh-fg";

const dir = await mkdtemp(path.join(tmpdir(), "herdr-fake-"));
const socketPath = path.join(dir, "herdr.sock");
const reports: { method: string; params: Record<string, any> }[] = [];

const server = net.createServer((socket) => {
  socket.on("data", (chunk) => {
    for (const line of String(chunk).split("\n")) {
      if (!line.trim()) continue;
      const request = JSON.parse(line);
      reports.push({ method: request.method, params: request.params ?? {} });
    }
    socket.end('{"ok":true}\n');
  });
});
await new Promise<void>((resolve) => server.listen(socketPath, resolve));

process.env.HERDR_ENV = "1";
process.env.HERDR_PANE_ID = PANE_ID;
process.env.HERDR_SOCKET_PATH = socketPath;
process.env.HERDR_AGENT_SOURCE = FORWARDED_SOURCE;
delete process.env.OMPCODE;

const extension = await import("./herdr-omp-agent-state.ts");

/** Wait until no new report has arrived for a beat. */
async function settle(timeoutMs = 3000) {
  const deadline = Date.now() + timeoutMs;
  let seen = reports.length;
  while (Date.now() < deadline) {
    await Bun.sleep(50);
    if (reports.length === seen) return;
    seen = reports.length;
  }
}

function sessionContext(withSession: boolean) {
  return {
    hasUI: true,
    isIdle: () => true,
    sessionManager: withSession
      ? { getSessionId: () => SESSION_ID, getSessionFile: () => SESSION_PATH }
      : undefined,
  };
}

const resumeArgv = (report: { params: Record<string, any> }) => report.params.resume_argv;

async function driveAgentStart(withSession: boolean) {
  const handlers = new Map<string, (event: unknown, ctx: unknown) => void>();
  extension.default({
    on: (name: string, handler: any) => handlers.set(name, handler),
    events: { on: (name: string, handler: any) => handlers.set(name, handler) },
  });
  const from = reports.length;
  handlers.get("agent_start")!({}, sessionContext(withSession));
  await settle();
  return reports.slice(from);
}

test("reports the Mac reattach command for a session it knows", async () => {
  const beforeSession = await driveAgentStart(false);
  expect(beforeSession.length).toBeGreaterThan(0);
  for (const report of beforeSession) {
    expect(resumeArgv(report)).toBeUndefined();
  }

  const withSession = await driveAgentStart(true);
  const carrying = withSession.filter((report) => resumeArgv(report) !== undefined);
  expect([...new Set(carrying.map((report) => report.method))].sort()).toEqual([
    "pane.report_agent",
    "pane.report_agent_session",
  ]);
  for (const report of carrying) {
    expect(report.params.pane_id).toBe(PANE_ID);
    expect(report.params.source).toBe(FORWARDED_SOURCE);
    expect(report.params.agent).toBe("omp");
    expect(resumeArgv(report)).toEqual(["ompr", "--resume", SESSION_ID]);
  }
  for (const report of withSession) {
    if (resumeArgv(report) === undefined) continue;
    expect(report.params.agent).toBe("omp");
  }
});

test("leaves every other source to Herdr's built-in omp resume", () => {
  expect(extension.resumeArgvForSource(FORWARDED_SOURCE, SESSION_ID)).toEqual([
    "ompr",
    "--resume",
    SESSION_ID,
  ]);
  expect(extension.resumeArgvForSource(FORWARDED_SOURCE, undefined)).toBeUndefined();
  expect(extension.resumeArgvForSource("herdr:omp", SESSION_ID)).toBeUndefined();
});

afterAll(async () => {
  server.close();
  await rm(dir, { recursive: true, force: true });
});
