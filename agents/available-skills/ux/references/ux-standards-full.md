# UX Standards

Every interface — visual, programmatic, or code — must feel inevitable. The user, the API consumer, and the developer reading the code should all think "of course it works this way." This document defines what that means at every layer.

The design direction is always outside-in: start from what the human experiences, then work inward to the API, then to the code. But push back when a UX request would require architecture that degrades the experience for everyone long-term. Bad architecture eventually breaks the UX it was built to serve.

---

## The Fundamental Rule

**The user must always know whether the system is working or waiting for them.**

There are only three valid states from the user's perspective:

1. **The system is waiting for my input.** It's clear what I should do next.
2. **The system is working.** I can see that something is happening.
3. **The system is done.** I can see the result and know what to do next.

If the user is ever in a fourth state — "I don't know what's happening" — the UX has failed. This applies at every layer: a loading spinner on a UI, an HTTP response on an API, a clear return type in code. Ambiguity is the enemy.

---

## End-User Experience

### Respect the User's Time

- **Perceived performance is real performance.** A 2-second operation that shows progress feels faster than a 1-second operation that freezes the screen. Never show a blank screen while loading. Show skeleton content, then fill it in.
- **Collect minimum information before acting.** Don't ask for 10 fields and then validate. Ask for one field, validate immediately, proceed to the next. Each interaction collects just enough to make the next decision or start the next request.
- **Start network requests as early as possible.** If the user types a username, check if it exists before they finish the form. Pipeline decisions — don't batch them.
- **Never block the user waiting for something they don't need yet.** If the screen has 5 sections and 3 load instantly from cache, show those 3 immediately. Load the other 2 in background.
- **Blocking operations must appear instant.** If an API call takes 200ms, that's fine — show the result. If it takes 2 seconds, the UI must show progress the entire time. If it takes 10 seconds, it should be async with a notification on completion.

### Always Show State

- **Every button press produces an immediate visible response.** Disable the button, show a spinner, change the text to "Saving..." — anything. A button that does nothing visible when clicked is broken UX even if the request is in flight.
- **Progress indicators match reality.** A spinner means "working, unknown duration." A progress bar means "working, estimated X% done." Don't show a progress bar that jumps from 0% to 99% to done — that's a spinner pretending to be a progress bar.
- **Completed actions confirm visually.** A save operation shows a brief "Saved" confirmation. A delete removes the item from the list immediately. The user never wonders "did that work?"
- **Errors are immediate and visible.** If a field is invalid, show the error as soon as the user leaves the field — not after they submit the form. If a background sync fails, show a non-intrusive banner — not nothing.
- **Stale data is labeled.** If showing cached data while refreshing, indicate it. "Last updated 5 minutes ago" with a subtle refresh indicator. The user knows what they're seeing and that fresh data is coming.

### Progressive Disclosure

Show only what's relevant right now. Reveal complexity as the user needs it, not before.

- **Forms are pipelines, not pages.** Each step asks for one thing. The answer determines the next step. Username → exists? → password. Doesn't exist? → create password + confirm. The user never sees fields that don't apply to them.
- **Settings are layered.** Common settings visible. Advanced settings behind "show more." Power-user settings on a different screen. Don't overwhelm to seem powerful.
- **Errors are progressive too.** First: what went wrong in plain language. If the user wants more: technical details. If a developer wants more: error code, request ID, timestamp.

### Error Communication

- **Errors tell the user what to do, not what went wrong internally.** "Your session expired — sign in again" not "401 Unauthorized." "This email is already registered — did you mean to sign in?" not "UNIQUE constraint violated."
- **Never show stack traces, error codes, or technical details to end users.** Those go in logs. The user gets human language.
- **If the system can fix it, fix it silently.** A failed sync that succeeds on automatic retry is not an error the user needs to see. But the system state must still be clear — if it's retrying, show that it's working, not that it's idle.
- **If the system can't fix it, tell the user clearly what they can do.** "Check your internet connection and try again" is actionable. "An error occurred" is not.

### Offline and Resilience

- **The architecture must make offline capability trivial to add where it matters.** If the data layer is a direct API call, offline means a rewrite. If the data layer is an abstraction that syncs via API, offline means swapping the sync strategy.
- **Writes that must not be lost go through a persistent local queue.** The queue is the commitment. The UI confirms immediately. Sync happens in background. If sync fails, the queue retries. The user never loses work. But the user always sees the sync state — queued, syncing, synced, or failed.
- **Reads serve local/cached data first, then refresh in background.** Stale data displayed instantly is better than fresh data displayed after a 3-second wait. Update the display when the fresh data arrives.
- **Not everything needs offline.** Authentication is online-required. But once authenticated, anything the user has seen before should be available without a network round-trip.

### Platform Conventions

Follow the platform's design language. Don't fight the OS.

- **iOS/macOS:** Follow Apple's Human Interface Guidelines. Native controls. System fonts. Respect safe areas, dynamic type, and dark mode.
- **Android:** Follow Material Design. But don't put Material on iOS — it feels foreign.
- **Web:** Semantic HTML first. Accessibility by default. Keyboard navigable. Screen reader compatible. No custom controls that break browser conventions (scrolling, back button, text selection).
- **Cross-platform code, platform-native feel.** Shared business logic is fine. Shared UI across platforms almost always feels wrong on at least one.

### Accessibility Is Not Optional

- [ ] Every interactive element is keyboard accessible.
- [ ] Every image has alt text. Decorative images have empty alt (`alt=""`).
- [ ] Color is never the only indicator. Error states use color AND icon AND text.
- [ ] Touch targets are at least 44x44 points (Apple HIG) or 48x48dp (Material).
- [ ] Text is readable at 200% zoom without horizontal scrolling.
- [ ] Screen readers can navigate the full interface using semantic elements.
- [ ] Test with actual assistive technology, not just automated checkers.

### Localization Readiness

Every user-facing string is a constant, never inline. This applies to all text the user sees: labels, button text, error messages, confirmations, tooltips, placeholders, notifications.

```
// Wrong: inline string
button.title = "Save Changes"
showError("Your session has expired. Please sign in again.")

// Correct: constant that supports localization
button.title = Strings.saveChanges
showError(Strings.Errors.sessionExpired)
```

- **All user-facing strings live in a single, organized location per module** — a constants file, a strings file, or a localization bundle depending on the platform.
- **String constants are grouped by feature or screen,** not dumped in one flat list.
- **String constants use descriptive keys,** not generic ones. `Strings.Login.emailPlaceholder` not `Strings.placeholder1`.
- **Never concatenate strings to build user-facing messages.** Different languages have different word orders. Use parameterized templates: `String(format: Strings.welcomeMessage, userName)` or equivalent.
- **Even if you ship in one language today, build for localization from day one.** Extracting 500 inline strings later is a painful, error-prone project. Extracting zero is free.

### UI Tests on Critical Paths

Critical user flows must have automated UI tests that fail loudly when something breaks. The test strategy follows the failure philosophy from CODE_STANDARDS.md:

- **Critical paths (quotes, sign-up, payment, form submission) have end-to-end UI tests.** These tests use realistic timeouts. If a step stalls, the test times out and fails — this is intentional. A stalled wizard that silently skips a step is a bug that only an automated test catches.
- **UI tests verify user-visible state, not implementation.** Test that the premium amount appears on screen, not that a specific CSS class was applied. Test that the "next" button advances the form, not that a state variable changed.
- **Tests wait for elements, not for time.** `waitForExistence(timeout: 10)` not `sleep(10)`. If the element never appears, the test fails with a clear reason.
- **Non-critical UI (tooltips, animations, analytics) does NOT get UI tests.** These degrade gracefully. Testing them creates brittle tests that break on visual changes.

---

## API Consumer Experience

An API is a user interface for developers. The same principles apply: respect their time, be predictable, make the state of every operation obvious.

This section covers API **design** — how the contract behaves. For API **documentation** — how the OpenAPI spec and companion Guides are structured, what Spectral rules to enable, the hub-and-spoke docs model, persona discipline, the Stripe gut check — read `api-standards.md` before editing `openapi.yaml` or any docs surface.

### The Pit of Success

Design the API so the easiest way to use it is the correct way. A developer using the API without reading docs should fall into correct usage by default.

- **One way to do each thing.** If two endpoints accomplish the same goal, one shouldn't exist.
- **Required parameters are obvious.** If it won't work without a field, the field is required in the type signature, not validated at runtime.
- **Defaults are safe.** A developer who calls the API without optional parameters gets safe, conservative behavior — not maximum permissions or unlimited results.

### Consistency

A developer who learns one endpoint already knows how every other endpoint works.

- **Same response shape everywhere.** Every success returns `{ "data": ... }`. Every error returns `{ "error": { "code": "...", "message": "...", "details": ... } }`. No endpoint is a special case.
- **Same naming convention everywhere.** If one resource uses `created_at`, all resources use `created_at`. No mixing `snake_case` and `camelCase`.
- **Same pagination everywhere.** Pick cursor-based or offset-based. Same parameter names, same response structure, every list endpoint.
- **Same authentication everywhere.** One auth mechanism. One header. Every endpoint.
- **Same error handling everywhere.** Error codes are predictable. `not_found` means the same thing on every resource. `validation_error` always includes which fields failed and why.

### Response Time

- **100ms or less for API responses.** This is a hard constraint. If a response can't hit 100ms, the data needs to be restructured — precomputed, cached, denormalized. Don't optimize the API; restructure the data.
- **If an operation genuinely takes longer, make it async.** Accept the request, return `202 Accepted` with a job ID, let the client poll or receive a webhook. Never hold an HTTP connection open for 30 seconds.
- **The consumer always knows the state of their request.** Synchronous: the response is the state. Async: the job has a status endpoint. Webhook: the callback confirms completion. No ambiguity.

### Errors That Help

- **Errors tell the consumer what to fix.** `{ "error": "validation_error", "message": "email is required", "field": "email" }` — the developer knows exactly what to change.
- **Include enough context to debug without reading source code.** Request ID, timestamp, which parameter failed and why.
- **Rate limit responses include retry-after headers.** Don't just say "too many requests" — say when to come back.
- **4xx errors are the consumer's problem.** They can fix it by changing their request. **5xx errors are your problem.** The consumer should never see a 5xx in normal operation. If they do, that's an incident.
- **Errors are machine-readable.** The `code` field is a stable string enum that the consumer can switch on. The `message` field is human-readable and may change. Consumers match on codes, not messages.

### Idempotency

- **GET, PUT, DELETE are naturally idempotent.** Calling them twice produces the same result.
- **POST operations accept idempotency keys.** The client sends a unique key with each request. If the server receives the same key twice, it returns the same response without re-executing. This makes the persistent queue pattern safe — the queue can retry without creating duplicates.

### Versioning

- **Version from day one.** `/v1/users`. Not `/users` with a header.
- **Never break an existing version.** Add fields, add endpoints. Never remove, rename, or change the type of an existing field.
- **Deprecate with a timeline.** When v2 launches, v1 gets a sunset date. Responses include deprecation headers. Docs clearly state the migration path.

### SDK Generation

- **Client SDKs are generated from the OpenAPI spec, never hand-written.** One spec, every language gets a client automatically.
- **The spec is the source of truth.** If the spec and the implementation disagree, the implementation has a bug.

---

## Developer Experience (Code as UX)

The codebase is an interface that developers consume. A new developer — or an AI agent — is a user of your code. They deserve the same quality of experience as an end user.

### The 5-Minute Rule

A developer opening any file should understand its purpose within 5 minutes. If they can't:

- The file is too long (250 line heuristic).
- The naming doesn't convey intent.
- The abstraction level is wrong — either too high (indirection maze) or too low (implementation details everywhere).

### Code Reads Like Prose

The best code reads top-down like a narrative. The high-level function tells you WHAT happens. Each called function tells you HOW one step works. You only go deeper when you need to.

```
evaluateApplicant()
  → checkAgeEligibility()
  → checkStateAvailability()
  → evaluateConditions()
  → calculatePremium()
```

Reading `evaluateApplicant` tells you the full story without seeing any implementation. Each step is one function. Each function is independently testable. The flow can be reordered without rewriting internals — just like reordering steps in a UX pipeline.

### Internal APIs Follow External API Rules

Interfaces between packages follow the same rules as external APIs:

- **Consistent patterns.** If one package uses `New()` as a constructor, all packages do.
- **Predictable errors.** Every function that can fail returns an error the same way.
- **Small surface area.** A package's public API should be learnable in minutes.
- **Zero surprise.** A function named `GetUser` returns a user. It does not modify state, send emails, or trigger side effects.

### Modularity for UX Iteration

Code structure must support UX restructuring without rewrites. This is a direct architectural requirement.

- **UI components are independent units.** A `UsernameStep` component doesn't know about `PasswordStep`. They communicate through a parent orchestrator. Reordering the flow means changing the orchestrator, not the components.
- **API endpoints map to capabilities, not screens.** An endpoint that returns "everything the settings page needs" breaks when the settings page is redesigned. Endpoints that return users, preferences, and billing independently survive any UI restructuring.
- **Business logic is unaware of presentation.** The underwriting engine doesn't know if it's being called from a web form, a mobile app, or a batch job. It takes structured input and returns structured output.

### State Clarity in Code

The fundamental rule applies to code too. At every level, the state is obvious:

- **Functions return clear types.** A function returns a `Result`, an `Error`, or a `Value` — never a value that might be null without the type signature saying so.
- **Async operations have observable state.** A background job exposes `pending`, `running`, `completed`, `failed` — not a boolean `isDone`.
- **Side effects are explicit.** If a function modifies external state, its name says so: `saveUser()`, `deleteRecord()`, `sendNotification()`. A function named `getUser()` must not modify anything.

---

## Pushing Back on UX Requests

Sometimes the best UX decision is saying no. When evaluating a UX request, ask:

**"Does this add a special case?"** Special cases add complexity. Complexity adds bugs. Bugs degrade UX for everyone. A feature that delights one user but adds a conditional branch that affects all users is usually not worth it.

**"Can the architecture support this without degrading?"** If implementing a UX request requires bypassing the queue, hardcoding a value, or duplicating logic, the request needs to be renegotiated. Propose an alternative that achieves the same user outcome without the architectural cost.

**"Will this still work at 10x scale?"** A UX pattern that works for 100 users might break at 10,000. A custom notification per user action might be fine now but generate millions of notifications later. Design for the future load, not today's load.

**"Is this complexity in the right place?"** Complexity should live in the system, not in the user's head. But it should also live in the right layer of the system. A complex business rule belongs in the engine, not in the UI. A complex layout belongs in the UI, not in the API response format.

The goal is not to refuse requests. It's to translate "I want X" into the implementation of X that respects the user, the API consumer, the developer, and the architecture simultaneously. When those interests conflict, the architecture wins — because the architecture is what makes all future UX possible.

---

## Checklist

Before shipping any feature:

- [ ] The user always knows whether the system is working or waiting for them
- [ ] Every action produces immediate visible feedback
- [ ] Errors tell the user (or API consumer) what to do, not what broke internally
- [ ] Forms collect minimum information before acting
- [ ] The API response is under 100ms (or async with clear status)
- [ ] The API follows the same patterns as every other endpoint
- [ ] The code is modular enough to support reordering the UX flow
- [ ] Offline capability could be added without a rewrite (where applicable)
- [ ] Writes that must not be lost go through a persistent mechanism
- [ ] Accessibility requirements are met
- [ ] The feature works at 10x current scale
