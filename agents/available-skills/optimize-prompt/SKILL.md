---
name: optimize-prompt
description: TRIGGER when writing or modifying a quality-guard detection prompt, eval/judge prompt, or a durable system prompt. Do not use for prompt-writer labor work orders or subagent handoffs.
user-invokable: true
disable-model-invocation: false
argument-hint: "[prompt-text or file-path]"
---

# Prompt Optimizer

Optimize prompts using Anthropic's documented best practices for context engineering,
few-shot prompting, and reliable agent behavior.

## When to use

Apply this skill when you are:

- Writing a `detection.llm.prompt` in a quality-guard rule YAML
- Creating evaluation/judgment prompts
- Writing or revising a durable system prompt that will be reused

Do not use for prompt-writer labor work orders or one-off subagent handoffs.
Those stay outcome-first slots, not 10-element XML composition.

## The 5-Step Optimization Pipeline

Based on Anthropic's Prompt Improver methodology:

### Step 1: Structure with XML tags

Claude was explicitly trained to recognize XML tags. Every prompt should use them
to separate instructions from data, context from task, examples from evaluation.

**Before:**

```text
You are reviewing code. Check if it follows the facade pattern. The code is: {code}
Tell me if it passes or fails.
```

**After:**

```xml
<role>You are a senior code reviewer evaluating the facade pattern.</role>

<instructions>
Evaluate whether the code routes all system I/O through injectable facades.
</instructions>

<input>
{{code}}
</input>

Provide your assessment in <decision> tags.
```

### Step 2: Apply the 10-Element Composition

Not every prompt needs all 10, but consider each:

1. **Role** — who Claude is for this task
2. **Task context** — why this matters, what success looks like
3. **Tone** — communication style constraints
4. **Detailed rules** — numbered, specific, principle-based (NOT exhaustive lists)
5. **Examples** — 3-5 diverse examples in `<example>` tags (the single most effective lever)
6. **Input data** — wrapped in XML tags, placed near the top for long content
7. **Immediate task** — the actual request, placed near the END
8. **Precognition** — "Think step by step in <thinking> tags before answering"
9. **Output format** — explicit shape (JSON, XML tags, structured text)
10. **Constraints** — what NOT to do (but prefer telling Claude what TO do)

### Step 3: Add Chain-of-Thought

For judgment/evaluation prompts, require reasoning BEFORE the decision:

```xml
First, analyze the code in <thinking> tags.
Then provide your decision in <decision> tags.
```

For hallucination-resistant evaluation, force evidence extraction first:

```xml
Extract relevant evidence from the code in <evidence> tags.
Evaluate whether the evidence supports a PASS or FAIL.
Only then render your decision.
```

### Step 4: Add Diverse Examples

Examples are "the pictures worth a thousand words." Every evaluation prompt
should have at least 2-3 examples showing:

- A clear PASS case with reasoning
- A clear FAIL case with reasoning
- An edge case that could go either way

```xml
<examples>
  <example>
    <input>func getUser(id string) (*User, error) { return db.Find(id) }</input>
    <thinking>db.Find is a direct database call not going through an injectable facade.</thinking>
    <decision>FAIL</decision>
    <reason>Direct db.Find call should go through an injected Store interface.</reason>
  </example>
  <example>
    <input>func getUser(s Store, id string) (*User, error) { return s.Find(id) }</input>
    <thinking>s is an injected Store interface. The caller controls the implementation.</thinking>
    <decision>PASS</decision>
  </example>
</examples>
```

### Step 5: Enforce Output Format

Every prompt must specify the exact shape of the response:

```xml
Respond with ONLY a JSON object:
{"decision": "PASS" or "FAIL", "reason": "one sentence", "line": 0}
```

Or for structured evaluation:

```xml
<decision>PASS|FAIL</decision>
<reason>Actionable explanation citing specific code</reason>
```

## Anti-Patterns to Fix

When optimizing a prompt, check for and fix these:

| Anti-Pattern                         | Fix                                                            |
| ------------------------------------ | -------------------------------------------------------------- |
| Vague instructions                   | Add specific criteria, examples                                |
| No output format                     | Add explicit output shape                                      |
| "Do not X" framing                   | Rewrite as "Do Y instead"                                      |
| Laundry list of edge cases           | Replace with 3-5 diverse examples                              |
| Over-specification (brittle if-else) | Replace with principle-based heuristics                        |
| Under-specification (too vague)      | Add concrete evaluation criteria                               |
| No chain-of-thought                  | Add `<thinking>` before decision                               |
| Sequential option evaluation         | Avoid pairwise comparison (ordering bias)                      |
| `"CRITICAL: You MUST..."`            | Use normal language (overcapitalization causes overtriggering) |
| Flat structure, no XML tags          | Organize with descriptive XML tags                             |
| Examples all showing same pattern    | Diversify: pass, fail, edge case                               |
| Long data at end of prompt           | Move long data to top, query to bottom                         |

## The "Right Altitude" Test

Every prompt should pass this test:

- **Too high (under-specified):** "Review this code for quality" — gives no signal
- **Too low (over-specified):** "If the function has more than 5 params and any param is a bool and the return type is error, then..." — brittle, unmaintainable
- **Right altitude:** "Would a senior engineer at a top company flag this in a code review? What specifically would they say?" — principle-based, flexible, clear

## The Golden Rule Test

Show the prompt to a colleague with no context about the task.
If they would be confused about what to do, Claude will be too.

## For quality-guard Rule Prompts Specifically

Every `detection.llm.prompt` in a rule YAML should:

1. State the rule as a principle, not a checklist
2. Include `{{file_context}}` and `{{diff}}` template variables
3. Require evidence before judgment (`<thinking>` or evidence extraction)
4. Include 2-3 `examples-good` and `examples-bad` with real code
5. Specify output format: PASS/FAIL with reason
6. Explain WHY the rule exists (Claude generalizes from reasons)
7. Use normal language — no `CRITICAL`, `MUST`, `ALWAYS` overcapitalization

## Context Engineering Principles

- **Smallest set of high-signal tokens** — every token competes for attention
- **Context is precious and finite** — treat it like a budget, not a dump
- **Examples > rules** — 3 good examples teach better than 20 bullet points
- **Principle > enumeration** — "would a senior engineer mock this?" beats a list of functions
- **Structure > prose** — XML tags, numbered lists, clear sections
- **Reason > command** — "because X" helps Claude generalize; bare commands don't
