export const FILTER_MARKERS = [
	"blocked by Gemini's filters",
	"Request blocked by Google",
	"Generation was blocked by content filters",
] as const;

export const PLEASE_CONTINUE = "please continue";

const RESTATE_CAP = 4000;

export type ResumeStep = "please-continue" | "restate" | "stop";

export function isFilterBlock(text: string): boolean {
	return FILTER_MARKERS.some(marker => text.includes(marker));
}

/** A non-block resets the ladder. A third block in a row stops. */
export function nextResume(count: number, blocked: boolean): { count: number; step: ResumeStep } {
	if (!blocked) return { count: 0, step: "stop" };
	if (count <= 0) return { count: 1, step: "please-continue" };
	if (count === 1) return { count: 2, step: "restate" };
	return { count, step: "stop" };
}

export function resumeText(step: ResumeStep, lastUser: string): string | undefined {
	if (step === "please-continue") return PLEASE_CONTINUE;
	if (step !== "restate") return undefined;
	const task = lastUser.trim();
	if (!task || isFilterBlock(task) || task === PLEASE_CONTINUE) {
		return "Continue the original coding task in plain language.";
	}
	const body = task.length > RESTATE_CAP ? `${task.slice(0, RESTATE_CAP)}…` : task;
	return `Continue the original coding task. Restated request:\n\n${body}`;
}
