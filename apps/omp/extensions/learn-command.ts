// /learn [source] [reason] runs the @zab-ai/ai learn-from-transcript workflow on a session, then
// files and delegates its tickets when --dispatch is set.
//
// Imported directly from @zab-ai/ai so omp and Mastra / Mastra MCP share the same workflow definitions,
// role constants (@audit / @audit+advisor), and ticket schemas.
// Inline constants and ticket interfaces from @zab-ai/ai so the extension is 100%
// self-contained and never fails to load on a remote VPS, fresh container, or any
// machine without ~/.omp/agent/node_modules/@zab-ai/ai.
const LEARN_FROM_TRANSCRIPT_ID = "learn-from-transcript";
const STAGE1_FORENSICS_MODEL_ID = "@audit";
const STAGE2_PM_MODEL_ID = "@audit+advisor";

interface DelegatedTicket {
	title: string;
	project?: string;
	atask_id?: string;
	linear_link?: string;
	status: string;
	warning?: string;
	error?: string;
	delegated?: {
		task_id: string;
		status: "settled" | "failed" | "running" | "refused";
		branch?: string;
		workspace?: string;
		summary?: string;
		error?: string;
	};
	skip?: string;
}
import { spawn } from "node:child_process";
import { homedir } from "node:os";
import { join } from "node:path";

interface Ui {
	notify(message: string, type?: "info" | "warning" | "error"): void;
}
interface CommandContext {
	cwd: string;
	ui: Ui;
	sessionManager: { getSessionFile(): string | undefined };
}
interface Pi {
	registerCommand(
		name: string,
		spec: { description: string; handler: (args: string, ctx: CommandContext) => Promise<void> | void },
	): void;
}

const LAUNCHER = join(homedir(), ".agents", "bin", "learn-launch");
const OMP_SESSION_NAME = /_([0-9a-f]{8}-[0-9a-f-]{27})\.jsonl$/;
const SOURCE =
	/^(?:omp|claude|codex|grok|cursor|copilot|opencode|pi|hermes|agentmux):[A-Za-z0-9._-]+$|^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$|^mastra:thread:\S+$|^https?:\/\/\S+\/agents\/\S+\/threads\/\S+$/;

export default function (pi: Pi) {
	pi.registerCommand("learn", {
		description:
			`Learn from a session via @zab-ai/ai (${STAGE1_FORENSICS_MODEL_ID} -> ${STAGE2_PM_MODEL_ID}): /learn [<harness>:<id> | mastra thread URL] (default: this session)`,
		handler: (args, ctx) => {
			const words = args.trim().split(/\s+/).filter(Boolean);
			const named = words[0] !== undefined && SOURCE.test(words[0]) ? words[0] : undefined;
			const reason = (named ? words.slice(1) : words).join(" ") || "manual /learn";
			const file = ctx.sessionManager.getSessionFile() ?? process.env.PI_SESSION_FILE;
			const id = file ? OMP_SESSION_NAME.exec(file)?.[1] : undefined;
			if (!named && (!file || !id)) {
				ctx.ui.notify("/learn needs a saved session, or an explicit <harness>:<id> or Mastra thread URL", "warning");
				return;
			}
			const source = named ?? `omp:${id}`;
			ctx.ui.notify(`Running ${LEARN_FROM_TRANSCRIPT_ID} (${STAGE1_FORENSICS_MODEL_ID} -> ${STAGE2_PM_MODEL_ID}) on ${source}…`, "info");
			const child = spawn(LAUNCHER, [source, "--dispatch", "--reason", reason], {
				stdio: ["ignore", "pipe", "pipe"],
			});
			let stdout = "";
			let stderr = "";
			child.stdout.on("data", (chunk: Buffer) => (stdout += String(chunk)));
			child.stderr.on("data", (chunk: Buffer) => (stderr += String(chunk)));
			child.on("error", (error: Error) => ctx.ui.notify(`/learn failed to start: ${error.message}`, "error"));
			child.on("close", (code: number) => {
				if (code !== 0) {
					ctx.ui.notify(`/learn failed: ${stderr.trim() || `exit ${code}`}`, "error");
					return;
				}
				try {
					const tickets = JSON.parse(stdout) as DelegatedTicket[];
					const started = tickets.filter(ticket => ticket.delegated !== undefined).length;
					const failed = tickets.filter(ticket => ticket.delegated?.status === "failed").length;
					const waiting = tickets.filter(ticket => ticket.delegated?.status === "running").length;
					const filed = tickets.length === 0 ? "nothing to file" : `${tickets.length} ticket(s)`;
					const delegated = started === 0
						? "nothing delegated"
						: `${started} delegated${failed === 0 ? "" : `, ${failed} failed`}${waiting === 0 ? "" : `, ${waiting} still running`}`;
					ctx.ui.notify(`${LEARN_FROM_TRANSCRIPT_ID} on ${source}: ${filed}, ${delegated}`, failed === 0 ? "info" : "warning");
				} catch {
					ctx.ui.notify(`${LEARN_FROM_TRANSCRIPT_ID} on ${source} finished`, "info");
				}
			});
		},
	});
}
