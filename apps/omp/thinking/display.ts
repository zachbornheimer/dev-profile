/** Trimmed length below which a one-line mid-turn note is presentation noise. */
export const CALM_PRESERVE_MIN_CHARS = 240;

export interface DisplayBlock {
	type: string;
	text?: string;
	thinking?: string;
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

/**
 * Gemini 4 Argon sometimes streams its reasoning inside a `"text"` block
 * prefixed by `thought\n` or `🫧thought\n` instead of a `"thinking"` part.
 */
const LEAKED_THOUGHT_HEADER_RE = /^\s*(?:🫧\s*)?thought\r?\n/;

export interface SplitLeakedThought {
	/** Leading reaction emoji (`🫧`) when present before `thought\n`. */
	reactionPrefix: string;
	/** Extracted reasoning body (without the `thought\n` header). */
	thinking: string;
	/** Visible answer text following the reasoning, if any. */
	answer?: string;
}

/**
 * Find the zero-space transition where a closing self-talk sentence (`Let's …!`)
 * runs directly into the visible reply (`Let's run those now!Doing all three…`).
 * Ignores punctuation inside inline backtick code spans.
 */
function findInlineAnswerSeam(body: string): number | undefined {
	let offset = 0;
	for (const line of body.split(/(?<=\n)/)) {
		const letsMatch = /\blet's\b/i.exec(line);
		if (letsMatch) {
			let inCode = false;
			for (let i = 0; i < line.length - 1; i++) {
				const ch = line[i]!;
				if (ch === "`") {
					inCode = !inCode;
				} else if (
					!inCode &&
					i > letsMatch.index &&
					(ch === "." || ch === "!" || ch === "?") &&
					/[A-Z`"'*]/.test(line[i + 1]!)
				) {
					return offset + i + 1;
				}
			}
		}
		offset += line.length;
	}
	return undefined;
}

/**
 * Parse a `text` block that starts with `thought\n` or `🫧thought\n` into its
 * `thinking` body and optional trailing visible `answer`.
 */
export function splitLeakedThoughtText(
	text: string,
	options?: { hasFollowingBlocks?: boolean },
): SplitLeakedThought | undefined {
	const match = LEAKED_THOUGHT_HEADER_RE.exec(text);
	if (!match) return undefined;
	const reactionPrefix = text.slice(0, match.index) + (match[0].includes("🫧") ? "🫧" : "");
	const body = text.slice(match.index + match[0].length);
	const seam = findInlineAnswerSeam(body);
	if (seam !== undefined) {
		const thinking = body.slice(0, seam).trim();
		const answer = body.slice(seam).trim();
		return {
			reactionPrefix,
			thinking,
			...(answer.length > 0 ? { answer } : {}),
		};
	}
	if (!options?.hasFollowingBlocks) {
		const paragraphs = body.split(/\r?\n\r?\n/);
		if (paragraphs.length > 1) {
			const lastParagraph = paragraphs[paragraphs.length - 1]!.trim();
			const priorThinking = paragraphs.slice(0, -1).join("\n\n").trim();
			if (priorThinking.length > 0 && lastParagraph.length > 0 && !/^(?:wait\b|let's\b|hold\b)/i.test(lastParagraph)) {
				return {
					reactionPrefix,
					thinking: priorThinking,
					answer: lastParagraph,
				};
			}
		}
	}
	return {
		reactionPrefix,
		thinking: body.trim(),
	};
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
	let changed = false;
	const content: DisplayBlock[] = [];
	for (let i = 0; i < message.content.length; i++) {
		const block = message.content[i]!;
		if (block.type === "thinking") {
			if (options.hideThinking && block.narration !== true) {
				changed = true;
				continue;
			}
			content.push(block);
			continue;
		}
		if (block.type === "text" && block.text !== undefined) {
			const leaked = splitLeakedThoughtText(block.text, {
				hasFollowingBlocks: i < message.content.length - 1,
			});
			if (leaked) {
				changed = true;
				if (!options.hideThinking && leaked.thinking.length > 0) {
					content.push({ type: "thinking", thinking: leaked.thinking });
				}
				if (leaked.answer !== undefined && leaked.answer.length > 0) {
					if (!(options.hideNotes && isCalmWorkingNote(leaked.answer))) {
						const prefix = leaked.reactionPrefix ? `${leaked.reactionPrefix}\n` : "";
						content.push({ ...block, text: `${prefix}${leaked.answer}` });
					}
				} else if (leaked.reactionPrefix) {
					content.push({ ...block, text: leaked.reactionPrefix });
				}
				continue;
			}
			if (options.hideNotes && isCalmWorkingNote(block.text)) {
				changed = true;
				continue;
			}
		}
		content.push(block);
	}
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
