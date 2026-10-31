import { describe, expect, it } from "bun:test";
import {
	CALM_PRESERVE_MIN_CHARS,
	displayMessage,
	effectiveHideThinking,
	isCalmWorkingNote,
	isCalmHiddenWarning,
	parseCalm,
	parseThinking,
	thinkingStatus,
} from "./display";

const thinking = { type: "thinking", text: "secret" };
const note = { type: "text", text: "Reading the file." };
const reply = { type: "text", text: "The file exports compile.\nIt is ready." };

describe("thinking presentation", () => {
	it("hides a one-line note under 240 characters and keeps a newline or a long block", () => {
		expect(isCalmWorkingNote("Reading the file.")).toBe(true);
		expect(isCalmWorkingNote("first line\nsecond")).toBe(false);
		expect(isCalmWorkingNote("x".repeat(CALM_PRESERVE_MIN_CHARS - 1))).toBe(true);
		expect(isCalmWorkingNote("x".repeat(CALM_PRESERVE_MIN_CHARS))).toBe(false);
	});

	it("strips thinking already in the message and leaves the reply", () => {
		const message = { content: [thinking, reply] };
		const shown = displayMessage(message, { hideThinking: true, hideNotes: false });
		expect(shown.content).toEqual([reply]);
		expect(message.content).toEqual([thinking, reply]);
	});

	it("strips a settled working note and keeps a longer reply in the same message", () => {
		const message = { content: [note, reply] };
		expect(displayMessage(message, { hideThinking: false, hideNotes: true }).content).toEqual([reply]);
	});

	it("preserves thinking blocks marked as narration because native rendering treats them as the answer", () => {
		const narration = { type: "thinking", narration: true, thinking: "The answer." };
		expect(displayMessage({ content: [thinking, narration] }, { hideThinking: true, hideNotes: true }).content).toEqual([narration]);
	});
	it("hides thinking while calm is on unless /thinking on overrides it", () => {
		expect(effectiveHideThinking({ hideThinking: false, calm: true, showThinkingDespiteCalm: false })).toBe(true);
		expect(effectiveHideThinking({ hideThinking: false, calm: true, showThinkingDespiteCalm: true })).toBe(false);
		expect(thinkingStatus({ hideThinking: false, calm: true, showThinkingDespiteCalm: false })).toBe(
			"Thinking blocks: hidden while calm is on",
		);
	});

	it("parses /thinking and /calm", () => {
		expect(parseThinking("off")).toBe("off");
		expect(parseThinking("")).toBe("status");
		expect(parseThinking("high")).toBe("bad");
		expect(parseCalm("", false)).toEqual({ enabled: true });
		expect(parseCalm("off", true)).toEqual({ enabled: false });
		expect(parseCalm("status", true)).toEqual({ status: true });
		expect(parseCalm("boat", false)).toEqual({ error: "Usage: /calm [on|off|status]" });
	});

	it("hides fallback warnings and advisor request failures, not other warnings", () => {
		const fallback = [
			"Fallback: openrouter/z-ai/glm-5.3:max -> anthropic/claude-sonnet-5-5:high",
			"Advisor request failed: 402 Insufficient credits. Add more using https://openrouter.ai/settings/credits",
		].join("\n");
		expect(isCalmHiddenWarning(fallback)).toBe(true);
		expect(isCalmHiddenWarning("Advisor request failed: 402 Insufficient credits")).toBe(true);
		expect(isCalmHiddenWarning("  Fallback: a -> b")).toBe(true);
		expect(isCalmHiddenWarning("No todos to copy.")).toBe(false);
		expect(isCalmHiddenWarning("Could not restore model openai/gpt-5")).toBe(false);
	});
});
