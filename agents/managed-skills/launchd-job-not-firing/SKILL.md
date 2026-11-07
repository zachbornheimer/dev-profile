---
name: launchd-job-not-firing
description: Diagnose a scheduled macOS LaunchAgent that is loaded but never runs, and fix the usual cause (login-shell invocation).
---

# A LaunchAgent that never fires

A job can be loaded, have `StartCalendarInterval` entries, and still never run once.
`launchctl list` alone hides this: it prints a last-exit column that reads `0` for a job
that has never exited.

## Measure first

```sh
launchctl print gui/$(id -u)/<label> | rg "state|runs|last exit|program =|stdout path"
```

- `runs = 0` and `last exit code = (never exited)` means it has **never** executed since it
  was loaded. Empty `StandardOutPath`/`StandardErrorPath` files agree: the program never got
  as far as its first `echo`.
- `state = xpcproxy` with no child process of the script name means the interpreter is stuck
  before running the script body.

Cross-check with the artifact the job writes — a registry, ledger, or log line with
timestamps. If the newest entry predates the plist's install time, the job has not run.

## The usual cause

`ProgramArguments` using a login shell:

```xml
<string>/bin/zsh</string>
<string>-lic</string>
<string>exec /path/to/tick.sh</string>
```

A login shell under launchd sources profile files with no terminal: `mise`, `op`, a prompt
hook, or a keychain prompt blocks forever. Output is buffered, so the log stays empty.

## Fix

Run the script directly, with its interpreter and an explicit environment:

```xml
<key>ProgramArguments</key>
<array>
  <string>/bin/bash</string>
  <string>/absolute/path/to/tick.sh</string>
</array>
<key>EnvironmentVariables</key>
<dict>
  <key>HOME</key>
  <string>/Users/&lt;user&gt;</string>
  <key>PATH</key>
  <string>/Users/&lt;user&gt;/.local/bin:/Users/&lt;user&gt;/.local/share/mise/shims:/opt/homebrew/bin:/usr/bin:/bin</string>
</dict>
<key>WorkingDirectory</key>
<string>/absolute/repo/root</string>
```

Then:

```sh
launchctl bootout gui/$(id -u)/<label>            # ignore failure if never loaded
plutil -lint ~/Library/LaunchAgents/<label>.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/<label>.plist
launchctl print gui/$(id -u)/<label> | rg "program =|runs"
```

## Do not use kickstart to prove the fix

`launchctl kickstart -k gui/$(id -u)/<label>` runs the real job, side effects included. When
the job does work that must not run twice, prove the invocation separately: bootstrap a
temporary twin plist with a distinct `Label`, the same `ProgramArguments`, no
`StartCalendarInterval`, and the side-effectful env flag turned off. Kickstart the twin, read
its log, then `launchctl bootout` it and delete the file.

## Verify the real thing once

The only proof is `runs` incrementing on a calendar boundary and the job's own artifact
gaining an entry. Watch for the first scheduled minute after install; do not assume.
