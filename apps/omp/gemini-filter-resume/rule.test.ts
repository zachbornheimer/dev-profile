import { expect, test } from "bun:test";
import { isFilterBlock, nextResume, resumeText } from "./rule";

test("all Gemini filter wordings count, ordinary stops do not", () => {
	expect(isFilterBlock("This request was blocked by Gemini's filters.")).toBe(true);
	expect(isFilterBlock("Request blocked by Google (PROHIBITED_CONTENT)")).toBe(true);
	expect(isFilterBlock("Generation was blocked by content filters (SAFETY)")).toBe(true);
	expect(isFilterBlock("model finished")).toBe(false);
});

test("the ladder is please continue, then restate, then stop", () => {
	const first = nextResume(0, true);
	const second = nextResume(first.count, true);
	const third = nextResume(second.count, true);
	expect(first).toEqual({ count: 1, step: "please-continue" });
	expect(second).toEqual({ count: 2, step: "restate" });
	expect(third).toEqual({ count: 2, step: "stop" });
	expect(resumeText(first.step, "fix the parser")).toBe("please continue");
	expect(resumeText(second.step, "fix the parser")).toContain("fix the parser");
	expect(resumeText(third.step, "fix the parser")).toBeUndefined();
});

test("a normal stop resets the ladder", () => {
	expect(nextResume(2, false)).toEqual({ count: 0, step: "stop" });
	expect(nextResume(0, false)).toEqual({ count: 0, step: "stop" });
});

test("a missing or filter-shaped user text is not copied into the restate", () => {
	expect(resumeText("restate", "")).toBe("Continue the original coding task in plain language.");
	expect(resumeText("restate", "This request was blocked by Gemini's filters.")).not.toContain(
		"blocked by Gemini's filters",
	);
});
