import { describe, expect, it } from "bun:test";
import { displayMessage, withoutEvidence } from "./hide";

const CLAIM = '{"claim":"fixed","type":"test","ref":"bun test","scope":"tui"}';
const EVIDENCE = `\`\`\`evidence\n${CLAIM}\n\`\`\``;
const JSON_FENCE = `\`\`\`json\n${CLAIM}\n\`\`\``;

describe("withoutEvidence", () => {
	it("hides every payload shape at the end of a reply, with its blank line", () => {
		for (const payload of [EVIDENCE, JSON_FENCE, CLAIM, "```\n" + CLAIM + "\n```"]) {
			expect(withoutEvidence(`Done.\n\n${payload}`)).toBe("Done.");
			expect(withoutEvidence(`Done.\n\n${payload}\n`)).toBe("Done.");
		}
	});

	it("keeps one blank line between the text around a mid-reply payload", () => {
		for (const payload of [EVIDENCE, JSON_FENCE, CLAIM]) {
			expect(withoutEvidence(`Done.\n\n${payload}\n\nAfter.`)).toBe("Done.\n\nAfter.");
		}
	});

	it("hides payloads still streaming in", () => {
		expect(withoutEvidence('Done.\n\n```evidence\n{"claim":')).toBe("Done.");
		expect(withoutEvidence('Done.\n\n```json\n{"claim":"wav')).toBe("Done.");
		expect(withoutEvidence("Done.\n\n```json\n{\"cl")).toBe("Done.");
		expect(withoutEvidence("Done.\n\n```json")).toBe("Done.");
		expect(withoutEvidence('Done.\n\n{"claim":"wav')).toBe("Done.");
	});

	it("hides payloads inside a list item", () => {
		expect(withoutEvidence(`- item\n\n  ${CLAIM}\n- two`)).toBe("- item\n\n- two");
		expect(withoutEvidence("- item\n\n  ```evidence\n  {}\n  ```\n- two")).toBe("- item\n\n- two");
	});

	it("leaves other JSON, other fences, and prose about evidence alone", () => {
		const cases = [
			'Done.\n\n```json\n{"a":1}\n```',
			'Done.\n\n```json\n{"claim":"x",\n"type":"test"}\n```',
			'Done.\n\n```json\n{"a":1}',
			'Done.\n\n```ts\nconst x = {"claim": 1};\n```',
			'Done.\n\n{"a":1}',
			'Done.\n\n{"claim":"x",\n"type":"test"}',
			"The evidence fence is hidden.",
			"```\nplain\n```",
		];
		for (const text of cases) expect(withoutEvidence(text)).toBe(text);
	});

	it("does not treat a fence opener inside a kept fence as a new fence", () => {
		const text = "````md\n```evidence\nx\n```\n````";
		expect(withoutEvidence(text)).toBe(text);
	});
});

describe("displayMessage", () => {
	it("returns the same message when nothing is hidden", () => {
		const message = { role: "assistant", content: [{ type: "text", text: "Done." }] };
		expect(displayMessage(message)).toBe(message);
	});

	it("strips text blocks only and never mutates the original", () => {
		const message = {
			role: "assistant",
			content: [
				{ type: "thinking", thinking: CLAIM },
				{ type: "text", text: `Done.\n\n${JSON_FENCE}` },
			],
		};
		const shown = displayMessage(message);
		expect(shown.content).toEqual([
			{ type: "thinking", thinking: CLAIM },
			{ type: "text", text: "Done." },
		]);
		expect(message.content[1]).toEqual({ type: "text", text: `Done.\n\n${JSON_FENCE}` });
	});
});
