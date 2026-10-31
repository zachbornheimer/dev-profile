/**
 * Completion-gate evidence is a one-line JSON object `{"claim": …}` that agents
 * end a reply with. The transcript keeps it for the gate; the screen does not
 * need it. It arrives in three shapes, all hidden here:
 *
 * - a ```` ```evidence ```` fence (any body),
 * - a ```` ```json ```` (or unlabeled) fence whose every non-blank line is a claim object,
 * - a bare line that is a claim object.
 *
 * Every other fence and line is left alone. While a reply streams, an open
 * trailing fence or line that can still become evidence is hidden early, so it
 * never flashes on screen.
 */

const CLAIM_PREFIX = '{"claim"';
const FENCE_OPEN_RE = /^\s*(`{3,}|~{3,})\s*([^\s`]*)/;
const JSON_LANGS: Record<string, true> = { "": true, json: true, jsonc: true, jsonl: true };

function isClaimObject(line: string): boolean {
	const trimmed = line.trim();
	if (!trimmed.startsWith("{")) return false;
	try {
		const value: unknown = JSON.parse(trimmed);
		return typeof value === "object" && value !== null && !Array.isArray(value) && "claim" in value;
	} catch {
		return false;
	}
}

/** A trailing, still-growing line that may yet become a claim object. */
function mayBecomeClaim(line: string): boolean {
	const trimmed = line.trim().replace(/\s+/g, "");
	return trimmed.length > 0 && (trimmed.startsWith(CLAIM_PREFIX) || CLAIM_PREFIX.startsWith(trimmed));
}

function isClosingFence(line: string, marker: string): boolean {
	const trimmed = line.trim();
	return trimmed.length >= marker.length && trimmed === marker[0]!.repeat(trimmed.length);
}

function isEvidenceFence(lang: string, body: readonly string[], closed: boolean): boolean {
	if (lang === "evidence") return true;
	if (!JSON_LANGS[lang]) return false;
	const lines = body.filter(line => line.trim() !== "");
	if (closed) return lines.length > 0 && lines.every(isClaimObject);
	// Still streaming: every finished line is a claim, the last may still be one.
	if (lines.length === 0) return lang !== "";
	return lines.slice(0, -1).every(isClaimObject) && mayBecomeClaim(lines[lines.length - 1]!);
}

/** Cheap pre-check for a streaming tail that is not yet recognizably evidence: an open fence or a partial `{"claim"`. */
function mayEndInPayload(text: string): boolean {
	const tail = text.slice(-(CLAIM_PREFIX.length + 16));
	return tail.includes("{") || tail.includes("```") || tail.includes("~~~");
}

/** `text` without its evidence payloads and the blank lines that set each apart. */
export function withoutEvidence(text: string): string {
	if (!text.includes('"claim"') && !text.includes("evidence") && !mayEndInPayload(text)) return text;
	const lines = text.split("\n");
	const kept: string[] = [];
	let hid = false;
	let separate = false;

	const keep = (line: string): void => {
		if (separate && line.trim() !== "") {
			if (kept.length > 0) kept.push("");
			separate = false;
		}
		if (separate && line.trim() === "") return;
		kept.push(line);
	};
	const hide = (): void => {
		while (kept.length > 0 && kept[kept.length - 1]!.trim() === "") kept.pop();
		hid = true;
		separate = true;
	};

	for (let i = 0; i < lines.length; i++) {
		const line = lines[i]!;
		const open = FENCE_OPEN_RE.exec(line);
		if (open) {
			const marker = open[1]!;
			let end = i + 1;
			while (end < lines.length && !isClosingFence(lines[end]!, marker)) end++;
			const closed = end < lines.length;
			if (isEvidenceFence(open[2]!.toLowerCase(), lines.slice(i + 1, end), closed)) {
				hide();
			} else {
				for (let j = i; j <= Math.min(end, lines.length - 1); j++) keep(lines[j]!);
			}
			i = end;
			continue;
		}
		const last = i === lines.length - 1;
		if (isClaimObject(line) || (last && line.trim().startsWith(CLAIM_PREFIX))) {
			hide();
			continue;
		}
		keep(line);
	}
	return hid ? kept.join("\n") : text;
}

interface TextBlock {
	type: "text";
	text: string;
}

interface MessageLike {
	content: ReadonlyArray<{ type: string }>;
}

/** The message as displayed: text blocks without evidence. Returns `message` itself when nothing is hidden. */
export function displayMessage<M extends MessageLike>(message: M): M {
	let content: Array<{ type: string }> | undefined;
	for (let i = 0; i < message.content.length; i++) {
		const block = message.content[i]!;
		if (block.type !== "text") continue;
		const { text } = block as TextBlock;
		const shown = withoutEvidence(text);
		if (shown === text) continue;
		content ??= [...message.content];
		content[i] = { ...block, text: shown };
	}
	return content ? { ...message, content } : message;
}
