---
name: scheduled-job-never-ran
description: Diagnose a scheduled job (launchd/cron/Mastra tick) that is installed but has never actually run.
---

# A scheduled job that has never run

Use when a recurring job (LaunchAgent, systemd timer, cron, a Mastra tick) is believed to be installed but its work never happens: no PRs drained, no alerts filed, no reports written. Do not re-install and assume fixed — prove one run.

## Ladder, cheapest first

1. **Ask the scheduler, not the config file.** macOS LaunchAgent:

   ```bash
   launchctl print gui/$(id -u)/<label> | rg "state|runs|last exit|program =|stdout|stderr"
   ```

   - `runs = 0` means it has never fired since it was loaded. A plist on disk is not a running job.
   - `runs > 0` with `last exit code = 0` and no log content means it fired and produced nothing — the script is the suspect.
   - `state = xpcproxy` with an advancing pid and no child process means the launcher is stuck before reaching your script.
   - Reloading a plist resets `runs`, so a fresh install always looks like "never ran". Compare with the job's own state directory mtime to tell fresh-install from never-works.

2. **Read both log files, and the job's own state.** A scheduler that redirects stdout/stderr to a path will silently fail when the directory does not exist yet. Empty logs plus a state directory created at install time means nothing has run.

3. **Check the job's side effects, not just the scheduler.** A drain writes timestamps somewhere (a registry, a ledger, `*.runs.jsonl`). If the newest entry is days old, the job has not done work even if `runs` looks plausible.

4. **Run the script by hand with the plist's exact environment.** Success here and silence under the scheduler isolates the cause to the invocation, not the code.

5. **Prime suspect: a login shell under launchd.** `ProgramArguments = ["/bin/zsh", "-lic", "…"]` sources interactive rc files that can block on a prompt, a mise hook, or a network call, and it never reaches `exec`. Replace with `/bin/bash <absolute script path>` plus an explicit `EnvironmentVariables` block (`HOME`, `PATH`, the job's own flags). WorkingDirectory should be absolute too.

6. **Prove one real run.** `launchctl kickstart -k gui/$(id -u)/<label>`, then re-read `runs`/`last exit code` and the log. A dry-run mode makes this cheap when the job has one.

## Worked example (this machine)

`com.zysys.upgrade-bot-prs` ran `zsh -lic exec tick.sh`, reported `runs = 0` and empty logs, and its registry's newest try was five days old, while `bash tick.sh` finished in 34 s by hand. `/bin/bash` plus explicit env fixed it; 13 pull requests merged in the next 40 minutes.

Two more traps seen the same day: the tick runs from `~/Developer/Personal/capabilities-runner`, a checkout separate from where the tool is developed, so a fix in the other checkout never reaches it; and an on-demand backend box that reaps itself at idle loses detached `nohup` work.

## Exit

Only after a real run has produced its side effect (a merge, a written report, a filed ticket). Otherwise report the exact step that failed.
