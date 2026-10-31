/** Trimmed length below which a one-line mid-turn note is presentation noise. */
export const CALM_PRESERVE_MIN_CHARS = 240;

export interface DisplayBlock {
	type: string;
	text?: string;
	/** Native renders narration as answer text, even when reasoning is hidden. */
	narration?: boolean;
}

export interface DisplayMessage {
	timestamp?: number;
	content: readonly DisplayBlock[];
}

export interface Presentation {
	hideThinking: boolean;
	calm: boolean;
	/** `/thinking on` while calm is on. Calm on clears it. */
	showThinkingDespiteCalm: boolean;
}

export function isCalmWorkingNote(text: string): boolean {
	if (text.includes("\n")) return false;
	return text.trim().length < CALM_PRESERVE_MIN_CHARS;
}

/**
 * Model-fallback banners and advisor request failures. `showWarning` receives
 * the body; it prints `Warning: ${message}` itself.
 */
export function isCalmHiddenWarning(message: string): boolean {
	const flat = message.replace(/\s+/g, " ").trim();
	return flat.startsWith("Fallback:") || flat.startsWith("Advisor request failed");
}

export function effectiveHideThinking(presentation: Presentation): boolean {
	return presentation.hideThinking || (presentation.calm && !presentation.showThinkingDespiteCalm);
}

export function messageStoppedForTools(message: { content?: readonly { type: string }[] }): boolean {
	return message.content?.some(block => block.type === "toolCall") === true;
}

/**
 * The message as drawn. Thinking blocks drop when hidden. Short one-line notes
 * drop only when `hideNotes` is set (a settled step that stopped for tools).
 * The original message is not mutated.
 */
export function displayMessage<M extends DisplayMessage>(
	message: M,
	options: { hideThinking: boolean; hideNotes: boolean },
): M {
	if (!options.hideThinking && !options.hideNotes) return message;
	let changed = false;
	const content = message.content.filter(block => {
		if (options.hideThinking && block.type === "thinking" && block.narration !== true) {
			changed = true;
			return false;
		}
		if (
			options.hideNotes &&
			block.type === "text" &&
			block.text !== undefined &&
			isCalmWorkingNote(block.text)
		) {
			changed = true;
			return false;
		}
		return true;
	});
	if (!changed) return message;
	return { ...message, content };
}

export function thinkingStatus(presentation: Presentation): string {
	if (presentation.calm && !presentation.showThinkingDespiteCalm && !presentation.hideThinking) {
		return "Thinking blocks: hidden while calm is on";
	}
	return `Thinking blocks: ${effectiveHideThinking(presentation) ? "hidden" : "visible"}`;
}

export function parseThinking(args: string): "on" | "off" | "status" | "bad" {
	const verb = args.trim().toLowerCase();
	if (verb === "" || verb === "status") return "status";
	if (verb === "on" || verb === "off") return verb;
	return "bad";
}

export function parseCalm(
	args: string,
	current: boolean,
): { enabled: boolean } | { status: true } | { error: string } {
	const verb = args.trim().toLowerCase();
	if (verb === "status") return { status: true };
	if (verb === "") return { enabled: !current };
	if (verb === "on") return { enabled: true };
	if (verb === "off") return { enabled: false };
	return { error: "Usage: /calm [on|off|status]" };
}
