# Interactive atask lease owner

`index.ts` is the maintained omp extension entrypoint. It registers one timer for
an interactive UI main session, independent of turns, tool completion, or model
activity. Native subagents and detached/headless sessions have their own owners
and are excluded. The timer runs every 60 seconds; one renewal may run at a time.
It invokes `atask --json claim renew --runtime` in the owner's cwd with a ten-second
subprocess deadline, bounded captured output, and no shell. No token is put in
arguments, model context, or diagnostics. CLI output must be
`{ok:true,result:{renewed:N}}` with a nonnegative safe integer. Zero is idle after
release/complete and causes no lifecycle transition or output.

## Identity and lifecycle

One process singleton `runtimeRegistry` creates an unpredictable `mkdtemp` root
(mode 0700). It ignores any inherited root: a new process never adopts a previous
process's registration. `ATASK_RUNTIME_ROOT` is set to this fixed root before a
session event returns. Core refreshes native shell environment after
`session_start`, `session_switch`, and `session_branch`; native bash supplies
`PI_SESSION_ID` per invocation. Renewals supply both explicitly and clear legacy
`ATASK_SESSION`. Concurrent sessions share the root, not their registration.

Each `sha256(session).json` file (mode 0600, exclusive creation) contains
`{session,pid,incarnation,capability}`. The incarnation is 32 random bytes encoded
as hex, shared for this process. Each activation gets a fresh random 32-byte
capability. The CLI validates private ownership and live process ancestry and
persists a digest, not the raw capability, as its authority binding.

Switch, branch, shutdown, and the returned stop function clear the old timer and
revoke only that activation. Switching back issues a new capability. Repeated
start/reconnect in the same process retains the active capability. Pending old
renewal results cannot report, stop, or revoke a newer activation. CLI transaction
fencing prevents an old attempt from renewing a replacement attempt. Registry
roots are removed on process exit only, never when one of several sessions stops.

Any registration, subprocess, malformed-output, or renewal failure is terminal
for that activation: revoke, stop, and emit a fixed diagnostic with no stderr,
exception text, identifiers, paths, or capabilities. No retries. A new lifecycle
activation is required after failure; repeated reconnect does not restart it.

The private directory blocks unrelated users. Process-ancestry validation rejects
an unrelated process using only a session identifier. This is not a security
boundary against malicious code running as the same UID that can read private
files or modify the owning process. Crash leftovers are never adopted.

## Public contract and tests

`registerLease(host, options?)` returns an idempotent stop function. Exported
`LeaseContext` supplies `hasUI`, `cwd`, `agent.kind`,
`sessionManager.getSessionId()`, `setInterval(fn, ms)`, and `clearTimer(timer)`.
`LeaseHost.on(event, handler)` registers lifecycle handlers. Options are
`intervalMs`, `renew(owner, root): Promise<number>`, `report(event)`, and optional
`registry` for isolated fixtures. The owner is `{session,cwd}`. Reports are
`{kind:"renewed",count}` or `{kind:"failed",reason}`; reasons are `registration`,
`renewal`, or `cleanup`. The default reporter uses `console.error` for failures
and positive safe counters only. `Registry` owns activation/revocation;
`runtimeRegistry` is the shared production instance.

`mise run test:lease-unit` exercises deterministic timers, deferred renewals,
concurrency, fencing, failures, process isolation, and private registrations.
The separately owned `host-proof.ts` drives real host timers against the engine;
its environment and task wiring belong to the parent integration.
