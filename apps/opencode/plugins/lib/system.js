// System-boundary facade: the only place plugin code may touch the
// filesystem/process layer directly (Facade Rule — see ~/.claude/rules/code-standards.md).
// Swap this module in tests to stub process execution and $HOME.

import { execFileSync } from "node:child_process"
import { homedir } from "node:os"

export function homeDir() {
  return homedir()
}

export function runProcess(command, args, input) {
  return execFileSync(command, args, {
    input,
    timeout: 20_000,
    encoding: "utf8",
  })
}
