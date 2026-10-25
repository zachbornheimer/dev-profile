---
name: ai-question-schema
description: "Use when writing, reviewing, or validating a question YAML a runner asks automatically: System One criteria (yes/no, choice, score) or an LLM answer that must match a JSON schema. Use it when the user mentions a questionnaire, judgment questions, interrogate, identify_intent.yaml, select_project.yaml, criteria, or questions that should run on their own, even if they never say schema. Run scripts/validate_question_file.py before treating a question file as valid. Mastra workflow shape stays in mastra-authoring; this skill owns the question file."
user-invokable: true
---

# Auto-run question files

One YAML file is the questionnaire. Each key is a result field. The key's shape picks the model. System One answers a closed judgment. An LLM returns one JSON value. Code reads both. It does not scrape prose.

A chat prompt with `schema: {type: string}` is not a question. Neither is an instruction that tells the model to end in a fenced JSON block. The runner attaches the schema. The file does not.

## Write the file

Top-level map. No `questions:` wrapper. No `type:` key. Kind comes from the shape, the same way AgentMux `questionnaire.Load` reads a result struct.

````yaml
Ready: # result field. Letter first.
  instructions: Is it ready? # the question, non-empty. No ```json fence.
  criteria: # System One. XOR schema.
    true: Yes.
    false: No.

Goals:
  instructions: What are the goals?
  schema: # JSON Schema of the value under Goals, not the wrapper
    type: array
    items: { type: string }
  examples: # required on a schema question
    - prompt: add a CSV export
      answer: ["Add a CSV export."]
````

A file may hold both kinds. Closed labels stay on `criteria`. Lists, spans, and objects stay on `schema`.

Canonical files, copied rather than reinvented:

- `identify_intent.yaml` — yes/no, choice, and score in one file
- `select_project.yaml` — one standing choice; the caller prepends live options
- `identify_goals_outcomes.yaml` — schema plus `{prompt, answer}`
- `split_by_semantic_atomicity.yaml` — schema plus a string example

## Criteria is System One

| `criteria`                                              | Kind   | What code stores                                       |
| ------------------------------------------------------- | ------ | ------------------------------------------------------ |
| Map whose only keys are `true` and `false`              | yes/no | P(yes) in [0, 1]. Not a bool.                          |
| Any other word-to-sentence map, 1 to 255 options        | choice | `{Value, Probabilities}`, authored order               |
| List of `{what, examples?}`, at least 2, index 0 lowest | score  | `{Point, Probabilities}`. A tie takes the lower index. |

Every option and every `what` needs words. A choice whose menu is live data keeps only the standing option in the file (`new` in `select_project.yaml`). The caller prepends live names and drops blanks and repeats.

System One is a decision component. It does not write the schema value, and it does not pick the next workflow step.

## Schema is an LLM value

`schema` is the JSON Schema of the value under that field. The runner wraps it as `{type: object, properties: {Field: schema}, required: [Field], additionalProperties: false}`, validates the reply, and retries with the refusal reason.

The schema has to name a shape code can read:

- `type: object` with `properties`, or `type: array` with `items`
- a scalar only when it also has a constraint (`minLength`, `enum`, `minimum`, and the rest)
- unconstrained `type: string` is prose, not an answer

At least one example. A string example is shown as written. A `{prompt, answer}` example must match the schema's top-level type. Do not tell the model to emit a fence.

## What the runner does

1. Send every `criteria` question in the file to System One in one call, over the same state.
2. Send every `schema` question to the LLM with the wrapped schema. Do not send those through a classifier, and do not parse a fence out of free text.
3. Compose the two results in code. Ignore a speculative answer the chosen path does not use.

Ask the whole file. Do not split one field into a chain of checks.

## Validate

```bash
python3 ~/.agents/skills/ai-question-schema/scripts/validate_question_file.py path/to/questions.yaml
python3 ~/.agents/skills/ai-question-schema/scripts/validate_question_file.py path/to/questions-dir
python3 ~/.agents/skills/ai-question-schema/scripts/validate_question_file.py --self-test
```

Exit 0 and `path: ok` means the file matches this contract. Any other line names the field and the rule it broke. Fix the file. Do not weaken the validator to accept a chat prompt.
