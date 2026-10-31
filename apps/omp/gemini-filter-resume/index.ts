import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";
import { isFilterBlock, nextResume, PLEASE_CONTINUE, resumeText } from "./rule";

function textsOf(value: unknown): string[] {
	if (typeof value === "string") return [value];
	if (Array.isArray(value)) return value.flatMap(textsOf);
	if (!value || typeof value !== "object") return [];
	const record = value as Record<string, unknown>;
	return [
		...textsOf(record.text),
		...textsOf(record.thinking),
		...textsOf(record.content),
		...textsOf(record.errorMessage),
	];
}

export default function geminiFilterResume(pi: ExtensionAPI): void {
	let count = 0;
	let lastUser = "";

	const rememberUser = (text: string) => {
		const clean = text.trim();
		if (!clean || clean === PLEASE_CONTINUE || isFilterBlock(clean)) return;
		lastUser = clean;
	};

	pi.on("session_start", () => {
		count = 0;
		lastUser = "";
	});
	pi.on("session_switch", () => {
		count = 0;
		lastUser = "";
	});
	pi.on("input", event => {
		rememberUser(event.text);
	});
	pi.on("message_end", event => {
		if (event.message.role !== "user") return;
		for (const text of textsOf(event.message)) rememberUser(text);
	});
	pi.on("agent_end", (event, ctx) => {
		if (event.willContinue || event.awaitingAsyncWork || ctx.hasPendingMessages()) return;
		const blocked = event.messages.some(message => textsOf(message).some(isFilterBlock));
		const next = nextResume(count, blocked);
		count = next.count;
		const content = resumeText(next.step, lastUser);
		if (!content) return;
		pi.sendMessage(
			{
				customType: "gemini-filter-resume",
				content,
				display: false,
				attribution: "agent",
			},
			{ deliverAs: "nextTurn", triggerTurn: true },
		);
	});
}
