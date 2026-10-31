# Spec: AI turn history — thinking glow and action stack

**Status:** Proposed
**Version:** 0.1.0
**Last updated:** 2026-08-15

> This spec uses RFC 2119 normative keywords. MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY have their RFC 2119 meanings. Statements marked "(informative)" are non-normative.
>
> Ground truth is the Bevel recording in `source-video.mp4` (38.18s). Where this spec diverges from that recording, the divergence is labeled **DELTA** and is intentional — it is the completed-state contract for a history UI.

## 1. Frame

### 1.1 Changelog headline

Every AI turn now shows work as a shimmering status plus a growing action tree, then collapses into a duration header so the answer is what you read in history.

### 1.2 Observable outcome

A person watching a turn always knows the system is working (shimmer on "Thinking…" and on the current action), what it is doing (named rows stacking underneath), and when it is done (glow gone, duration label, answer below). Opening the same turn later looks like the completed state, not like a replay of the glow.

### 1.3 Stakeholders

- **Product / design:** a single pattern for live progress and for scrolled-back history, so AI work never looks like a spinner with no story.
- **Implementer (human or agent):** a falsifiable contract for states, motion, events, collapse rules, and failure.
- **End user:** can tell waiting / working / done at a glance, inspect any finished action, and read the answer without a ten-row tool dump in the way.

### 1.4 Non-goals

- A numeric progress bar or percent-complete indicator. Duration of model work is unknown; a bar that jumps is a lie.
- A token-by-token dump of hidden chain-of-thought as the primary surface. Rows are named actions, not the raw reasoning transcript.
- Re-styling the composer, model picker, or chat chrome. Those appear in the reference video and are out of scope except where they change in response to turn state (send ↔ stop).

### 1.5 Conformance classes

- **Renderer** — the history / transcript component that paints a turn.
- **Producer** — the runtime that emits thinking and action events for a turn.
- **Inspector** — the sheet or pane that shows an action's payload.

## 2. Invariants

Invariants hold across all states, all inputs, all concurrent callers, all crash points.

- **INV-001** — A turn MUST be in exactly one of: `waiting`, `working`, `done`, `stopped`, `failed`. A fourth visual state of "I don't know" is an invariant violation.
- **INV-002** — At most one action row in a turn MUST be `in_progress` at a time.
- **INV-003** — The shimmer MUST appear only on the working status label and the single `in_progress` action title. Completed, failed, and stopped text MUST be static.
- **INV-004** — Action rows MUST be append-only in display order. A renderer MUST NOT reorder, insert above, or silently drop a row that the producer has already emitted.
- **INV-005** — Opening a historical turn MUST render the completed (or stopped / failed) presentation. A renderer MUST NOT replay the shimmer on a turn whose terminal state is already known.
- **INV-006** — Collapse and expand MUST NOT destroy action identity, order, payloads, or inspectability.
- **INV-007** — Color MUST NOT be the only signal that a row is in progress. The shimmer (or, under reduced motion, a textual "In progress" suffix) MUST remain.

## 3. Requirements

### REQ-001 — Immediate working chrome

**Classes:** renderer
**Statement:** A renderer MUST paint the working status label within 100 ms of the user sending a message, before any action event arrives.
**Precondition:** The user has submitted a turn and the producer has accepted it.
**Postcondition:** The status label reads the working copy (default: "Thinking…"), the composer primary control is Stop, and the shimmer is running on the status label.
**Example:**

```gherkin
Given an empty new chat
When the user sends "How has my health been this week?"
Then "Thinking…" appears under the user bubble with the skeleton shimmer, and the send arrow becomes a stop square
```

**Failure modes:**

- `transient-failure`: producer accept is delayed → renderer still shows working chrome locally; if accept fails, transition to `failed` with "Couldn't start".
- `permanent-failure`: send rejected → no working chrome; error on the composer.

### REQ-002 — Skeleton shimmer, not a spinner

**Classes:** renderer
**Statement:** A renderer MUST express "working, unknown duration" as a luminance sweep through the glyphs of the status label (and the in-progress action title). It MUST NOT use a spinner, a determinate bar, or a percent.
**Precondition:** The turn is `working`.
**Postcondition:** A highlight band moves across the live text on a 1.2–1.6 s loop. Base text is ~40% of the completed contrast; the band peaks near the completed contrast.
**Example:**

```gherkin
Given the turn is working and no action has completed
When 800 ms elapses
Then "Thinking…" has visibly changed luminance along the word, then the band continues
```

**Failure modes:**

- `invariant-violation`: shimmer painted on a completed row → abort the animation on that row and log; the row MUST snap to static.
- `precondition-violation`: `prefers-reduced-motion: reduce` → MUST NOT run the sweep; MUST show static working copy plus a textual working cue.

### REQ-003 — Action tree stacks under the status

**Classes:** renderer, producer
**Statement:** A producer MUST emit named action events as work starts. A renderer MUST append each new row under the status label, newest last, with a type icon and title.
**Precondition:** The turn is `working`.
**Postcondition:** The tree contains every emitted action in emit order. Parent/child rails follow the producer's `parent_id`.
**Example:**

```gherkin
Given "Thinking…" is showing
When the producer emits {id: a1, type: reason, title: "Analyzing Health This Week"} then {id: a2, parent: a1, type: plan, title: "Evaluating next steps"}
Then those two rows appear under the status, child indented, connected by a vertical rail
```

**Failure modes:**

- `invalid-input`: event missing `id` or `title` → renderer ignores the event and the producer MUST emit a valid follow-up or fail the turn.
- `precondition-violation`: event for an unknown `turn_id` → ignore.

### REQ-004 — In-progress row uses the same shimmer

**Classes:** renderer
**Statement:** The single `in_progress` action title MUST use the same shimmer as the status label. That row MUST NOT show a chevron and MUST NOT be tappable.
**Precondition:** An action exists with status `in_progress`.
**Postcondition:** The live row is visually quieter (shimmering, no chevron). All earlier rows are static.
**Example:**

```gherkin
Given three completed actions and a fourth just started
When the fourth row is painted
Then "Analyzing health metrics for the week" shimmers and has no chevron, while the three above are solid and (if inspectable) show chevrons
```

**Failure modes:**

- `invariant-violation`: two rows shimmering → renderer MUST cancel shimmer on every row except the latest `in_progress`.

### REQ-005 — Completing a row

**Classes:** renderer, producer
**Statement:** When a producer marks an action `completed`, the renderer MUST stop that row's shimmer within one frame, set the title to the completed text color, and show a chevron if and only if the action is inspectable.
**Precondition:** The action was `in_progress` or `pending`.
**Postcondition:** The row is static and, if inspectable, opens the inspector on activate.
**Example:**

```gherkin
Given the metrics row is shimmering with no chevron
When the producer emits {id: a4, status: completed, inspectable: true}
Then the row snaps to solid text and a trailing chevron appears
```

**Failure modes:**

- `transient-failure`: completion event lost → row MAY stay `in_progress` until the turn terminals; on turn `done` every non-terminal row MUST snap to `completed` or `failed` per the producer's terminal snapshot.

### REQ-006 — Inspectable action sheet

**Classes:** renderer, inspector
**Statement:** Activating a completed inspectable row MUST open an inspector whose title is the action title and whose body is the action payload (code, query, result, or structured log). The inspector MUST be dismissible without changing turn state.
**Precondition:** The row is `completed` or `failed` and `inspectable: true`.
**Postcondition:** The sheet is visible; the turn behind it is unchanged.
**Example:**

```gherkin
Given "Analyzing health metrics for the week" is completed and inspectable
When the user activates the row
Then a sheet titled with that name opens, labeled with the payload language (e.g. Python), showing the code
```

**Failure modes:**

- `precondition-violation`: row is `in_progress` → activation is a no-op.
- `permanent-failure`: payload missing → inspector opens with "No details for this step."

### REQ-007 — Header collapse control

**Classes:** renderer
**Statement:** Once at least one action exists, the status row MUST offer a collapse control. Collapse hides the tree and keeps the status label. Expand restores the tree in emit order.
**Precondition:** `actions.length >= 1`.
**Postcondition:** Tree visibility matches the control. Identities persist (INV-006).
**Example:**

```gherkin
Given a four-row tree under "Thinking…"
When the user activates the header chevron
Then the four rows hide and "Thinking…" (still shimmering) remains
```

**Failure modes:**

- `precondition-violation`: no actions yet → no chevron.

### REQ-008 — Terminal status label

**Classes:** renderer
**Statement:** When the turn becomes `done`, the status label MUST become a duration sentence ("Thought for 20 seconds.") and the shimmer MUST stop. When `stopped`, the label MUST be "Stopped after N seconds." When `failed`, "Failed after N seconds."
**Precondition:** The producer has emitted a terminal turn event with `duration_ms`.
**Postcondition:** Status text is static. Composer primary control is Send.
**Example:**

```gherkin
Given the turn has been working for 20100 ms
When the producer emits {turn: done, duration_ms: 20100}
Then the label reads "Thought for 20 seconds." with no shimmer
```

**Failure modes:**

- `invalid-input`: missing `duration_ms` → renderer MUST compute elapsed from local start; MUST NOT show "Thought for 0 seconds."
- `invariant-violation`: shimmer still running after terminal → force-cancel all animations.

### REQ-009 — Completed turns collapse the tree (DELTA)

**Classes:** renderer
**Statement:** When a turn first becomes `done`, `stopped`, or `failed`, the renderer MUST collapse the action tree, unless the user expanded the tree during this turn. A historical turn opened later MUST start collapsed regardless of the live session.
**Precondition:** The turn has a terminal status.
**Postcondition:** The default history presentation is: user bubble, duration header, answer. The tree is one expand away.
**Example:**

```gherkin
Given the user never touched the collapse control
When the turn completes
Then the ten action rows hide, "Thought for 20 seconds." remains, and the answer is the next block
```

**Failure modes:**

- `precondition-violation`: user had the tree expanded at the moment of completion → MUST leave it expanded (do not yank).
- `invariant-violation`: historical turn paints the live shimmer → forbidden (INV-005).

### REQ-010 — Answer is below the thinking block

**Classes:** renderer
**Statement:** The assistant answer MUST render below the thinking block, never inside it, and MUST be allowed to stream. The thinking block MUST NOT wait for the full answer before switching to the terminal label.
**Precondition:** The producer has begun the answer stream or emitted `done`.
**Postcondition:** A reader can see duration header, then (if expanded) actions, then answer text.
**Example:**

```gherkin
Given the turn just became done
When the first answer tokens arrive
Then they appear under the (collapsed) thinking header, not as a child action row
```

**Failure modes:**

- `transient-failure`: stream stall → last painted tokens remain; a stalled cue MAY appear after 8 s with no tokens.

### REQ-011 — Overflow jump control

**Classes:** renderer
**Statement:** If the answer grows past the viewport while the user is not pinned to the bottom, the renderer MUST show a jump-to-end control. If the user is pinned, the viewport MUST follow new tokens.
**Precondition:** Answer content overflows the visible transcript.
**Postcondition:** The user can reach the live end in one activation.
**Example:**

```gherkin
Given the user has scrolled up to read the action tree
When more answer text arrives below the fold
Then a down-arrow chip appears above the composer
```

**Failure modes:**

- none beyond ordinary hit-testing; the control MUST disappear when the viewport is at the end.

### REQ-012 — Producer event contract

**Classes:** producer
**Statement:** A producer MUST emit the events in §3.1 of the companion HTML (turn.accepted, action.started, action.completed, action.failed, turn.done / turn.stopped / turn.failed) with stable ids. An `action.started` for a new id while another action is `in_progress` MUST first complete or fail the previous one, or nest it via `parent_id` without a second `in_progress` peer.
**Precondition:** A turn has been accepted.
**Postcondition:** A renderer can reconstruct the tree from the event log alone.
**Example:**

```gherkin
Given action a4 is in_progress
When the producer wants to start a5
Then it emits action.completed(a4) before action.started(a5), or starts a5 as a child only after a4 is terminal
```

**Failure modes:**

- `invariant-violation`: two peer `in_progress` actions → renderer keeps the latest and marks the earlier `completed` (self-heal) and the producer MUST treat that as a bug.
- `permanent-failure`: turn cannot continue → `turn.failed` with a user-facing `message`.

### REQ-013 — Stop

**Classes:** renderer, producer
**Statement:** Activating Stop MUST cancel in-flight work. The turn MUST become `stopped`. Partial actions MUST snap to `stopped` or `completed` per what actually finished. The answer, if any tokens exist, MUST remain.
**Precondition:** The turn is `working`.
**Postcondition:** Status is "Stopped after N seconds." Shimmer is off. Composer is Send.
**Example:**

```gherkin
Given four completed rows and one shimmering row
When the user hits Stop
Then the live row becomes "Stopped" (or is removed if it never produced a payload), the header reads "Stopped after N seconds.", and no further rows append
```

**Failure modes:**

- `transient-failure`: cancel not yet acked → chrome still shows Stopped locally; late events after cancel MUST be ignored.

### REQ-014 — Accessibility

**Classes:** renderer
**Statement:** The status label MUST be a polite live region. Action titles MUST be announced when they start. Inspectable rows MUST be keyboard-activatable. Touch targets MUST be at least 44×44 pt. `prefers-reduced-motion: reduce` MUST disable the sweep (REQ-002).
**Precondition:** Assistive technology or reduced-motion is in use.
**Postcondition:** A VoiceOver / TalkBack user can follow working → each action → done without seeing the animation.
**Example:**

```gherkin
Given VoiceOver is on
When the first action starts
Then VoiceOver announces "Analyzing Health This Week, in progress"
```

**Failure modes:**

- `invariant-violation`: color-only in-progress state → forbidden (INV-007).

### REQ-015 — Collapsed summary

**Classes:** renderer
**Statement:** A collapsed terminal header SHOULD include a one-line count of steps ("6 steps") so a closed tree is not an empty secret. It MUST NOT require the user to expand to learn that work happened.
**Precondition:** The tree is collapsed and `actions.length >= 1`.
**Postcondition:** The header communicates duration and that a tree exists.
**Example:**

```gherkin
Given 10 actions and a collapsed done turn
When the user looks at the header
Then they see "Thought for 20 seconds." and a control that implies more (chevron, and SHOULD "10 steps")
```

**Failure modes:**

- none; omitting the count is allowed in v0.1 (SHOULD).

## 4. Edge cases

- **Empty input:** REQ-001 — working chrome still appears; if the producer rejects, drop to `failed` with no tree.
- **Zero actions, then answer:** allowed. Status goes working → "Thought for N seconds." with no chevron and no tree.
- **Maximum scale:** at 50+ actions the collapsed default (REQ-009) is the load-bearing rule. Expanded view MUST virtualize or clip; it MUST NOT mount 50 inspectable sheets.
- **Concurrent callers:** one turn, one renderer. Two in-flight turns in one transcript are separate trees (INV-002 is per turn).
- **Crash recovery:** if the process dies mid-turn, on restore the producer MUST either resume as `working` (shimmer allowed) or terminal-snapshot the turn. The renderer MUST NOT invent rows.
- **Offline / degraded dependency:** producer emits `action.failed` on the live row, then either continues or `turn.failed`. The failed row stays inspectable with the error payload.
- **Adversarial caller:** a producer that emits two `in_progress` peers is healed by REQ-012; the renderer does not crash.
- **User expanded, then completion:** REQ-009 — stay expanded.
- **Historical open:** INV-005 + REQ-009 — collapsed, no shimmer.
- **Reduced motion:** REQ-002 + REQ-014.

## 5. Evolution and unresolved

### 5.1 Stability contract

- **Stable (breaking change = major version):** INV-001–INV-007, REQ-001, REQ-002, REQ-003, REQ-004, REQ-005, REQ-008, REQ-009, REQ-010, REQ-012, REQ-013.
- **Provisional (may change with deprecation):** REQ-006 inspector chrome, REQ-011 overflow chip, REQ-015 count copy, default English strings.
- **IMPLEMENTATION-DEFINED:** icon set per action type; exact easing curve of row insert; whether a non-inspectable completed row (the sparkle "Evaluating next steps" in the reference) is ever tappable.

### 5.2 Unresolved questions

- **Q1:** Exact English for a failed action row versus a failed turn. Deferred until the first product with real tool errors; v0.1 uses "Failed" on the row and REQ-008 on the header.
- **Q2:** Whether reason-parent rows should stay visible when collapsed-expanded, or only the tool children. v0.1 shows the full emit tree.
- **Q3:** Grouping many tiny tool calls into one row. Out of scope; the producer decides granularity.

### 5.3 Invalidation conditions

This spec is wrong if the product decides that AI work should be hidden (no tree, spinner only), or if a determinate progress signal becomes honest (real step counts known in advance). Either change invalidates REQ-002 and REQ-009.

## 6. Traceability

See `tests/spec/traceability.yaml`. This spec is satisfied when every entry in that file has `status: passing`.
