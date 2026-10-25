---
name: ux
description: Use when building UI components, API surfaces, or developer-facing code. The standards Claude breaks by default — state visibility, error communication, a11y, string extraction. Full source in references/.
---

# UX

Every interface — visual, programmatic, or code — must feel inevitable. The user,
the API consumer, and the developer should all think "of course it works this way."

**The one rule everything else serves:** the user always knows whether the system
is working or waiting for them. There are exactly three valid states: waiting for
input, working, done. A fourth state ("I don't know what's happening") is a UX
failure.

## Gotchas — where Claude defaults break

**Button with no immediate visible response on click.**
Every button press produces an immediate visible effect: disable the button, show a
spinner, change text to "Saving…" — anything. A button that does nothing visible
when clicked is broken UX, even if the request is in flight.

**Wrong loading indicator.**
A spinner means "working, unknown duration." A progress bar means "working,
estimated X% done." A progress bar that jumps 0% → 99% → done is a spinner
pretending to be a progress bar. Match the indicator to what you actually know.

**Error says what broke, not what to do.**
"401 Unauthorized" → wrong. "Your session expired — sign in again" → right.
"UNIQUE constraint violated" → wrong. "This email is already registered — did you
mean to sign in?" → right. Errors tell users (and API consumers) the next action,
not the internal failure.

**Form collecting all fields before validating.**
Forms are pipelines, not pages. Validate as soon as the user leaves each field.
Don't batch validation to submit. Collect minimum information before acting — each
step asks for one thing, the answer determines the next step.

**User-facing strings not extracted as constants.**
Every string a user can read is a named constant in a single organized location.
Never inline. Never concatenate to build messages (word order differs by language).
Use parameterized templates. This is localization readiness from day one — not
extracting 500 inline strings later.

**Accessibility omissions.**

- Touch targets: at least 44×44 pt (Apple) / 48×48 dp (Material).
- Color is never the sole indicator. Error states use color AND icon AND text.
- Every interactive element is keyboard accessible.
- Every image has alt text; decorative images have `alt=""`.
- Test with actual assistive technology, not only automated checkers.

**Stale data shown without a label.**
If showing cached data while refreshing, say so. "Last updated 5 minutes ago."
Fresh data lands; update the display. Never silently serve stale data as current.

## API consumer UX (the same rules apply)

- **Pit of success.** The easiest way to use the API is the correct way.
- **Consistency.** Same response shape, same naming, same pagination, same auth,
  same error codes — everywhere. One deviation forces the consumer to special-case.
- **Under 100ms.** If a response can't hit 100ms, restructure the data (precompute,
  cache, denormalize). If it genuinely takes longer, make it async: `202 Accepted`
  - job ID + status endpoint. Never hold a connection open for 30 seconds.
- **Machine-readable errors.** `code` is a stable string enum to switch on.
  `message` is human-readable and may change. Consumers match on codes.

## Developer experience (code as UX)

- Code reads top-down like a narrative. `evaluateApplicant()` tells you WHAT; each
  called function tells you HOW one step works.
- A developer opening any file understands its purpose within 5 minutes.
- Side effects are explicit in the name: `saveUser()`, `sendNotification()`.
  A function named `getUser()` must not modify anything.
- Internal package APIs follow external API rules: consistent patterns, predictable
  errors, small surface area, zero surprise.

## Offline and resilience

Writes that must not be lost go through a persistent local queue. The queue is the
commitment; sync happens in background. Reads serve cached data first, then refresh.
The architecture must make offline capability trivial to add — not a rewrite.

---

Full source: `~/.claude/rules/ux-standards.md`
