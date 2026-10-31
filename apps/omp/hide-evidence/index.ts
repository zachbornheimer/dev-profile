import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";
import { AssistantMessageComponent } from "@oh-my-pi/pi-tui/chat/assistant-message";
import { displayMessage } from "./hide";

const PATCHED = Symbol.for("omp.hide-evidence.patched");

/**
 * Hide completion-gate evidence from assistant messages on screen.
 *
 * `updateContent` is the one entry every assistant render goes through (the
 * constructor calls it too), so wrapping it changes only what is drawn: the
 * session and transcript keep the message verbatim.
 */
export default function hideEvidence(_pi: ExtensionAPI): void {
	const proto = AssistantMessageComponent.prototype as typeof AssistantMessageComponent.prototype & {
		[PATCHED]?: true;
	};
	if (proto[PATCHED]) return;
	const updateContent = proto.updateContent;
	proto.updateContent = function (this: AssistantMessageComponent, message, opts) {
		return updateContent.call(this, displayMessage(message), opts);
	};
	proto[PATCHED] = true;
}
