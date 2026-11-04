# Master agent definitions

One agent definition per file, in a harness-neutral format. Each harness renders
it into its own artifact; no harness is the source of truth and none is
hand-edited.

```text
~/.agents/agents/<name>.yaml   the master (this format, schema: agents/v1)
~/.agents/agents/render.py     the renderers (currently: omp)
```

## Why

The same agents existed twice: Mastra's `src/agents/<name>/<name>.yaml` and
omp's `~/.omp/agent/agents/<name>.md`. They drifted — Mastra's `code-improver`
carried a 250-line prompt while omp's was a relay that called Mastra over MCP.
A master file makes the prompt, the tool surface, and the model role identical
everywhere, and makes a harness binding a mechanical transform instead of a
second authoring job.

## Schema (`agents/v1`)

| Field                 | Type              | Meaning                                                                                                                                                                           |
| --------------------- | ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `schema`              | string            | Always `agents/v1`. A renderer refuses a version it does not know.                                                                                                                |
| `name`                | string            | Slug. The rendered file is named after it.                                                                                                                                        |
| `description`         | string            | One sentence a routing model reads. No first person.                                                                                                                              |
| `whenToUse`           | string            | When to pick this agent, in the delegator's words.                                                                                                                                |
| `tags`                | string[]          | Free-form grouping for listings. Not behaviour.                                                                                                                                   |
| `model.role`          | enum              | `default` \| `smol` \| `slow` \| `plan` \| `task`. `default` means the session's own model; the renderer emits no model.                                                          |
| `model.thinkingLevel` | enum              | `auto` \| `low` \| `medium` \| `high`. A hint, not a guarantee.                                                                                                                   |
| `workspace`           | enum              | `machine` (any absolute path), `repo` (this checkout only), `none` (no files).                                                                                                    |
| `tools.all`           | bool              | `true` gives the agent every tool the harness mounts (omp: no `tools:` key). When set, `always`/`searchable` are documentation for the prompt, not a filter.                      |
| `tools.always`        | string[]          | Canonical capabilities mounted up front.                                                                                                                                          |
| `tools.searchable`    | string[]          | Canonical capabilities found through the harness's tool search; never preloaded.                                                                                                  |
| `tools.denied`        | string[]          | Canonical capabilities the harness must withhold even if it has them.                                                                                                             |
| `spawns`              | string[] \| `"*"` | Subagent names this agent may delegate to. `[]` = none.                                                                                                                           |
| `output`              | `none` \| object  | `none`, or `{ schema: <name> }` once the agent needs a structured answer. The schema itself lives beside the master (`<name>.output.json`) so every harness reads one definition. |
| `prompt`              | string            | The system prompt. Names capabilities, never a harness's tool names.                                                                                                              |
| `harnesses`           | map               | Name overrides only — never behaviour. See below.                                                                                                                                 |

### `harnesses`

A harness block exists for one reason: the same capability has a different id
or a different file shape there. It may rename, add a model id, or set a path.
It may not add instructions, tools, or constraints the master does not state —
a harness that needs different behaviour gets a different agent, not an
override.

```yaml
harnesses:
  omp:
    name: code-improver # rendered file name
    model: ["@task"] # explicit id instead of a role
  mastra:
    definitionPath: mastra/src/agents/code-improver/code-improver.yaml
```

## Canonical capability vocabulary

Masters name these ids. A renderer maps each to its harness's own tool; a
capability a harness lacks is reported as missing, never silently dropped.

| Canonical                  | Meaning                        | omp              | Mastra                                         | Claude Code              |
| -------------------------- | ------------------------------ | ---------------- | ---------------------------------------------- | ------------------------ |
| `read`                     | read a file or range           | `read`           | `agentmux_capability_read`                     | `Read`                   |
| `write`                    | create or overwrite a file     | `write`          | `agentmux_capability_write`                    | `Write`                  |
| `edit`                     | patch an existing file         | `edit`           | `agentmux_capability_edit`                     | `Edit`                   |
| `glob`                     | find files by path shape       | `glob`           | `agentmux_capability_glob`                     | `Glob`                   |
| `grep`                     | search file contents           | `grep`           | `agentmux_capability_grep`                     | `Grep`                   |
| `list`                     | list a directory               | `find`           | `agentmux_capability_glob`                     | `LS`                     |
| `stat`                     | file metadata                  | —                | `agentmux_capability_glob`                     | `Bash(stat)`             |
| `run_command`              | run a shell command            | `bash`           | `agentmux_capability_run_command`              | `Bash`                   |
| `run_tests`                | the repo's focused test runner | `bash`           | `run_tests`                                    | `Bash`                   |
| `search_tools`             | find the rest of the catalog   | — (native)       | `search_tools`                                 | — (native)               |
| `worktrunk`                | worktree lifecycle             | `bash`           | `worktrunk`                                    | `Bash`                   |
| `atask_*`                  | task board verbs               | MCP `atask_*`    | `agentmux_capability_*`                        | via MCP                  |
| `memory_*`                 | durable memory                 | MCP `memory_*`   | `memory_*`                                     | via MCP                  |
| `web_search` / `web_fetch` | external facts                 | `web_search` / — | `web_search` / `web_fetch`                     | `WebSearch` / `WebFetch` |
| `collect_failure_evidence` | bounded failure evidence       | —                | `agentmux_capability_collect_failure_evidence` | —                        |

`—` means the harness has no equivalent: the renderer omits it and the prompt's
instruction to search before assuming absence still holds.

## Rendering

```bash
render.py code-improver            # write every harness it knows
render.py code-improver --harness omp
render.py --check code-improver    # exit 1 when an artifact is stale
```

Rules every renderer keeps:

1. **Deterministic.** Same master, same bytes. No timestamps, no ordering drift.
2. **Self-describing.** Every rendered artifact starts with a line naming the
   master and the command that regenerates it, so nobody hand-edits it.
3. **Loud on the unexpressible.** A field the harness cannot carry is reported
   on stderr; it is never approximated silently.
4. **Idempotent.** Writing an unchanged artifact touches nothing.

### The same masters, read by Mastra

`capability-replicas` reads these files directly: each agent passes `master: "<name>"` beside its
in-repo `definition` URL, and `src/agents/master-definition.ts` takes `description`, `whenToUse` and
`prompt` from the master, keeps `Model`/`ModelRouting` from the in-repo file (routing metadata is not
the agent's description), and swaps each canonical capability name for the Mastra tool that serves
it. With no master on the machine (CI, a fresh clone) the in-repo YAML is the fallback, so the build
never depends on `~/.agents`.

### Importing an existing Mastra agent

```bash
import_mastra.py <repo>/mastra/src/agents/<name>/<name>.yaml --name <name>
```

It maps `Description`/`Use when`/`Prompt` into the master shape, rewrites Mastra tool names to the
canonical ones, and prints any tool name it cannot place. `--force` overwrites a master; it drops a
hand-written `harnesses:` block, so re-add any name override afterwards.

Current targets:

- **omp** — `render.py` writes `~/.omp/agent/agents/<name>.md`: YAML frontmatter
  (`name`, `description`, `tools`, `spawns`, `model`, `thinkingLevel`, `output`)
  and the master prompt as the body, preceded by the capability bindings note.
- **Mastra** — planned: `capability-replicas` reads the master directly and
  builds its `Definition` from it (`mastra/src/agents/<name>/`), so the YAML
  beside the TS file retires.
- **Claude Code** — planned: `~/.claude/agents/<name>.md` with `name`,
  `description`, `tools`, `model` frontmatter.
- **Codex** — planned: a project-scoped agent entry; Codex has no user-level
  agent files today, so the renderer writes into the checkout it runs in.

## Adding an agent

1. Copy an existing master and change `name`, `description`, `whenToUse`, `tools`.
2. Write the prompt in capability ids. If you catch yourself naming a harness's
   tool, add the binding to the table above instead.
3. `render.py <name>` and commit both the master and the rendered artifact.
