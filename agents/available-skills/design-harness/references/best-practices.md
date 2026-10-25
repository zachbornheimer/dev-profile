# Agent harness best practices (digest)

Use this while designing. Prefer primary sources for depth; this is the working
checklist for the `design-harness` skill.

## Workflow vs agent (Anthropic)

- **Workflows:** LLMs + tools on **predefined** code paths. Predictable.
- **Agents:** model **dynamically** directs process and tools.
- Most production wins are **workflows with tools**, not fully free agents.
- Increase autonomy only when flexibility is worth latency, cost, and compounded error.

Source: [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)

## Composable patterns (use the smallest that fits)

| Pattern                   | Use when                                                   |
| ------------------------- | ---------------------------------------------------------- |
| **Prompt chaining**       | Fixed subtasks; gate between steps                         |
| **Routing**               | Distinct categories need different prompts/tools           |
| **Parallelization**       | Independent subtasks (sectioning) or voting for confidence |
| **Orchestrator–workers**  | Subtasks **unknown** until runtime (coding, open research) |
| **Evaluator–optimizer**   | Clear eval criteria; iteration measurably improves output  |
| **Autonomous agent loop** | Open-ended; trusted env; hard stop bounds required         |

For known pipelines (page overhaul, deploy, report generation): **chaining +
parallel + gates**, not a free orchestrator for the outer spine.

## What the harness owns

1. **Orchestration loop** — what runs next
2. **Context construction** — what the model sees
3. **Skill/tool routing** — ACI: clear tools, poka-yoke args
4. **Memory / durable state** — resume, audit, HITL pause
5. **Verification & governance** — gates before world writes
6. **Bounds** — timeouts, max iterations, spend, stop conditions

Model scaling improves reasoning; **system scaling** improves the harness.

## Multi-agent as distributed systems (GitHub et al.)

- Every handoff needs a **typed schema**
- Validate at boundaries
- Specialists don't free-chat the outer path
- "Add more agents" without interfaces → failure
- Prefer **supervisor + phase gates** over unconstrained swarms

## Human involvement

| Mode                      | Meaning                                                      |
| ------------------------- | ------------------------------------------------------------ |
| **In the loop**           | Human required every critical step (slow)                    |
| **On the loop**           | System runs; human steers policy, approves irreversible acts |
| **Runtime approval gate** | Pause, persist state, resume after accept/reject             |

Irreversible / production / money / publish → human gate.
Generation and self-check → automated gates.

## Idempotency & resume (logistics)

- **Start:** same in-flight work → return existing run id (`reused`)
- **Crash:** resume from last completed node, not restart from zero unless unsafe
- **Apply:** same content hash → no-op write
- **Stale generating:** park or fail closed; never double-spend side effects

## Gates

- **Absolute** criteria tied to contract / brand / tests
- **Fail closed** when context missing
- Prefer **code** gates over LLM judges; use LLM judge only for residual taste with structured rubrics
- Never ship on "best of N weak candidates" alone

## Tool / ACI quality

- Formats models write well (natural text, full files) over brittle diffs/JSON when possible
- Absolute paths, example usage, edge cases in tool docs
- Test tool use; poka-yoke parameters
- Often more leverage than prompt tweaking

## Frameworks

- Fine to start; production often **drops abstraction** once the pattern is clear
- Understand what the framework hides
- Config should own **when**; code should own **what good means**

## Effectiveness checklist

- [ ] Outer control flow is code/config, not chat memory
- [ ] Generative work is slot-constrained (skeleton/contract)
- [ ] Typed artifacts between nodes
- [ ] Absolute gates before human sees candidates
- [ ] Ground truth from environment (build, render, test)
- [ ] One human gate for liability, not babysitting
- [ ] Idempotent start + apply
- [ ] Named failure → named node
- [ ] Golden + known-bad fixtures
- [ ] Improve-the-harness loop after every bad run

## Anti-patterns

| Anti-pattern                    | Prefer                          |
| ------------------------------- | ------------------------------- |
| Free agent for known stages     | Workflow spine                  |
| Relative score only             | Absolute gates                  |
| Generate directly to production | Generate → gate → apply → human |
| Handoff as prose                | Versioned artifact types        |
| Fix one run by hand only        | Fixture + gate + re-press       |
| Framework as product            | Thin graph + clear policies     |
