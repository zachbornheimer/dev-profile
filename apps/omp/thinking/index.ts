/**
 * /thinking and /calm, outside omp.
 *
 * updateContent is the one entry every assistant render goes through, so
 * wrapping it changes only what is drawn. The session and the model still
 * get the original message. Tool shells are hidden by forcing the visibility
 * setter calm already owns. The working row is left alone. Fallback warnings
 * and advisor request failures are dropped in showWarning while calm is on.
 */
import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";
import { findScopedSettings, settings } from "@oh-my-pi/pi-coding-agent/config/settings";
import { cfgHideThinkingBlock } from "@oh-my-pi/pi-coding-agent/session/settings";
import { UiHelpers } from "@oh-my-pi/pi-coding-agent/modes/utils/ui-helpers";
import { Container, TUI } from "@oh-my-pi/pi-tui";
import { AssistantMessageComponent } from "@oh-my-pi/pi-tui/chat/assistant-message";
import { ReadToolGroupComponent } from "@oh-my-pi/pi-tui/chat/read-tool-group";
import { ToolExecutionComponent } from "@oh-my-pi/pi-tui/chat/tool-execution";
import {
	type Presentation,
	displayMessage,
	effectiveHideThinking,
	isCalmHiddenWarning,
	messageStoppedForTools,
	parseCalm,
	parseThinking,
	thinkingStatus,
} from "./display";

const PATCHED = Symbol.for("omp.thinking.patched");

type AssistantMessage = Parameters<AssistantMessageComponent["updateContent"]>[0];
type ToolRow = { setToolActivityVisible(visible: boolean): void };
type UpdateOptions = Parameters<AssistantMessageComponent["updateContent"]>[1];
interface RenderSnapshot {
	raw: AssistantMessage;
	display: AssistantMessage;
	options: UpdateOptions;
}

interface RenderState {
	patched: boolean;
	presentation: Presentation;
	nativeSettings: typeof settings;
	nativeHideThinking?: boolean;
	thinkingOverride?: boolean;
	toolStops: Set<number>;
	noteHostByTimestamp: Map<number, object>;
	rawMessages: WeakMap<AssistantMessageComponent, RenderSnapshot>;
	appliedThinking: WeakMap<AssistantMessageComponent, boolean>;
	assistants: Set<AssistantMessageComponent>;
	tools: Map<ToolRow, boolean>;
	transcripts: Set<{ resetStableEmission(): void }>;
	tui?: { resetDisplay(): void };
}

// Installed wrappers and reloaded handlers must use the same state owner.
const globals = globalThis as typeof globalThis & { [PATCHED]?: RenderState };
const state: RenderState = globals[PATCHED] ??= {
	patched: false,
	presentation: { hideThinking: false, calm: false, showThinkingDespiteCalm: false },
	nativeSettings: settings,
	toolStops: new Set(),
	noteHostByTimestamp: new Map(),
	rawMessages: new WeakMap(),
	appliedThinking: new WeakMap(),
	assistants: new Set(),
	tools: new Map(),
	transcripts: new Set(),
};
const { presentation, toolStops, noteHostByTimestamp, rawMessages, appliedThinking, assistants, tools, transcripts } = state;

function currentPresentation(): Presentation {
	// Native setters outrank CLI settings; /thinking explicitly overrides both.
	presentation.hideThinking = state.thinkingOverride ?? state.nativeHideThinking ?? cfgHideThinkingBlock.get(state.nativeSettings);
	return presentation;
}

function resetSession(nativeSettings: typeof settings): void {
	state.nativeSettings = nativeSettings;
	state.nativeHideThinking = undefined;
	state.thinkingOverride = undefined;
	Object.assign(currentPresentation(), { calm: false, showThinkingDespiteCalm: false });
	for (const component of assistants) {
		rawMessages.delete(component);
		appliedThinking.delete(component);
	}
	assistants.clear();
	tools.clear();
	transcripts.clear();
	toolStops.clear();
	noteHostByTimestamp.clear();
}

function rememberTranscript(host: object): void {
	if (!("resetStableEmission" in host)) return;
	const reset = host.resetStableEmission;
	if (typeof reset !== "function") return;
	transcripts.add({ resetStableEmission: () => reset.call(host) });
}

function rememberToolStop(message: { timestamp?: number; content?: readonly { type: string }[] }): void {
	if (!messageStoppedForTools(message) || typeof message.timestamp !== "number") return;
	toolStops.add(message.timestamp);
}

function isNoteHost(component: object, message: { timestamp?: number }): boolean {
	if (typeof message.timestamp !== "number" || !toolStops.has(message.timestamp)) return false;
	if (!noteHostByTimestamp.has(message.timestamp)) noteHostByTimestamp.set(message.timestamp, component);
	return noteHostByTimestamp.get(message.timestamp) === component;
}

function refreshAssistants(): void {
	const update = AssistantMessageComponent.prototype.updateContent;
	for (const component of assistants) {
		const snapshot = rawMessages.get(component);
		if (snapshot) update.call(component, snapshot.raw, snapshot.options);
	}
}

function repaint(): void {
	refreshAssistants();
	for (const [tool, requested] of tools) tool.setToolActivityVisible(requested);
	for (const transcript of transcripts) transcript.resetStableEmission();
	state.tui?.resetDisplay();
}

function wrapToolVisibility(proto: ToolRow): void {
	const setVisible = proto.setToolActivityVisible;
	proto.setToolActivityVisible = function (visible: boolean) {
		tools.set(this, visible);
		return setVisible.call(this, presentation.calm ? false : visible);
	};
}

function patchSurfaces(): void {
	if (state.patched) return;
	state.patched = true;
	const setHideThinkingBlock = AssistantMessageComponent.prototype.setHideThinkingBlock;
	AssistantMessageComponent.prototype.setHideThinkingBlock = function (hide) {
		state.nativeHideThinking = hide;
		appliedThinking.set(this, hide);
		return setHideThinkingBlock.call(this, hide);
	};
	const updateContent = AssistantMessageComponent.prototype.updateContent;
	AssistantMessageComponent.prototype.updateContent = function (message, opts) {
		const snapshot = rawMessages.get(this) ?? { raw: message, display: message, options: opts };
		// Native invalidate() replays its display copy, not the session's original message.
		if (message !== snapshot.display) snapshot.raw = message;
		snapshot.options = opts;
		rawMessages.set(this, snapshot);
		assistants.add(this);
		rememberToolStop(snapshot.raw);
		const hideNotes = presentation.calm && opts?.transient !== true && isNoteHost(this, snapshot.raw);
		// Avoid clearing native collapsed-state tracking on every streaming update.
		const hideThinking = effectiveHideThinking(currentPresentation());
		if (appliedThinking.get(this) !== hideThinking) {
			// Applying our display policy must not become a new native preference.
			appliedThinking.set(this, hideThinking);
			setHideThinkingBlock.call(this, hideThinking);
		}
		snapshot.display = displayMessage(snapshot.raw, { hideThinking, hideNotes });
		return updateContent.call(this, snapshot.display, opts);
	};
	const dispose = AssistantMessageComponent.prototype.dispose;
	AssistantMessageComponent.prototype.dispose = function () {
		assistants.delete(this);
		rawMessages.delete(this);
		appliedThinking.delete(this);
		return dispose.call(this);
	};

	wrapToolVisibility(ToolExecutionComponent.prototype);
	wrapToolVisibility(ReadToolGroupComponent.prototype);

	const addChild = Container.prototype.addChild;
	Container.prototype.addChild = function (component) {
		rememberTranscript(this);
		return addChild.call(this, component);
	};

	const requestRender = TUI.prototype.requestRender;
	TUI.prototype.requestRender = function (...args: Parameters<TUI["requestRender"]>) {
		state.tui = this;
		return requestRender.apply(this, args);
	};

	const showWarning = UiHelpers.prototype.showWarning;
	UiHelpers.prototype.showWarning = function (message, options) {
		if (presentation.calm && isCalmHiddenWarning(message)) return;
		return showWarning.call(this, message, options);
	};
}

export default function thinkingExtension(pi: ExtensionAPI): void {
	patchSurfaces();

	const reset = (_event: unknown, ctx: { cwd: string }) => {
		const nativeSettings = findScopedSettings(ctx.cwd) ?? settings;
		resetSession(nativeSettings);
	};
	pi.on("session_start", reset);
	pi.on("session_switch", reset);

	pi.on("message_update", event => {
		if (event.message.role === "assistant") rememberToolStop(event.message);
	});
	pi.on("message_end", event => {
		if (event.message.role !== "assistant" || !messageStoppedForTools(event.message)) return;
		rememberToolStop(event.message);
		if (presentation.calm) refreshAssistants();
	});

	pi.registerCommand("thinking", {
		description: "Show or hide thinking blocks, including ones already on screen",
		handler: (args, ctx) => {
			const verb = parseThinking(args);
			if (verb === "bad") {
				ctx.ui.notify("Usage: /thinking [on|off|status]", "warning");
				return;
			}
			if (verb === "on" || verb === "off") {
				state.thinkingOverride = verb === "off";
				presentation.showThinkingDespiteCalm = verb === "on";
				repaint();
			}
			ctx.ui.notify(thinkingStatus(currentPresentation()), "info");
		},
	});

	pi.registerCommand("calm", {
		description: "Quiet the transcript: hide thinking, tool shells, short working notes, and fallback warnings. The reply stays.",
		handler: (args, ctx) => {
			const parsed = parseCalm(args, presentation.calm);
			if ("error" in parsed) {
				ctx.ui.notify(parsed.error, "warning");
				return;
			}
			if ("enabled" in parsed) {
				presentation.calm = parsed.enabled;
				if (parsed.enabled) presentation.showThinkingDespiteCalm = false;
				repaint();
				ctx.ui.notify(
					parsed.enabled
						? "Calm on. Thinking, tool shells, short working notes, and fallback warnings are hidden."
						: "Calm off.",
					"info",
				);
				return;
			}
			ctx.ui.notify(presentation.calm ? "Calm: on" : "Calm: off", "info");
		},
	});
}
