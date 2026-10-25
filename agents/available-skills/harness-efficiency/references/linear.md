# Linear

Personal Linear MCP. Team **Zysys**. Project **AI Harness Code Efficiency**
(renamed from Claude Code Harness Efficiency).

- id: `05c39a34-e16e-4a08-94ed-38e61ae2c7b9`
- url: <https://linear.app/zysys/project/ai-harness-code-efficiency-ecf68853de26>

Search before create. Update an existing ticket rather than opening a duplicate.
Skip `one_off` findings unless severe.

## Update, do not duplicate

| Issue                     | Topic                                     |
| ------------------------- | ----------------------------------------- |
| ZYS-734                   | Session budget                            |
| ZYS-790                   | Gates vs edits (gate-hours vs edit-hours) |
| ZYS-742                   | Bash compound commands                    |
| ZYS-748                   | Isolation verifier                        |
| ZYS-731, ZYS-737, ZYS-736 | Work-order gate                           |
| ZYS-729                   | Stop-hook cap                             |
| ZYS-740, ZYS-753          | Worktree vs `~/.agents`                   |
| ZYS-751, ZYS-752          | zq                                        |
| ZYS-788                   | golangci-lint module root                 |

## Ticket body

Every new or updated issue includes:

1. Problem
2. Evidence (measured counts, not vibes)
3. Harnesses / models (omit if unknown)
4. Frequency (`session_count`, `occurrences`)
5. Proposed primitive and fix
6. Measurable acceptance
7. Session ids
