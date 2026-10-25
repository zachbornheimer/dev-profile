#!/usr/bin/env python3
"""Validate an auto-run question file.

Each top-level key is one result field. `criteria` is a System One judgment.
`schema` is an LLM value. A field is one of those, never both, and never a
chat prompt wearing a string schema.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

MAX_CHOICE_OPTIONS = 255
MIN_SCORE_LEVELS = 2
QUESTION_KEYS = frozenset({"instructions", "criteria", "schema", "examples"})
EXAMPLE_KEYS = frozenset({"prompt", "answer"})
YES = "true"
NO = "false"
JSON_FENCE = "```json"
SCALAR_TYPES = frozenset({"string", "number", "integer", "boolean"})
SCALAR_CONSTRAINTS = frozenset(
    {
        "minLength",
        "maxLength",
        "pattern",
        "enum",
        "const",
        "format",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
    }
)
CANONICAL_DIR = Path(
    "/Users/zbornheimer/Developer/Personal/agentmux/internal/capabilities/questions"
)
BROKEN_DIR = Path(
    "/Users/zbornheimer/Developer/Personal/capability-replicas/mastra/src/workflows/learn-from-transcript"
)
BROKEN_FILES = ("analyze.yaml", "synthesize.yaml", "log-tickets.yaml")


def string_key(key: object) -> str | None:
    """YAML 1.1 reads the keys true and false as bools. The file means the words."""
    if key is True:
        return YES
    if key is False:
        return NO
    if isinstance(key, str) and key != "":
        return key
    return None


def validate_text(text: str, label: str) -> list[str]:
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as error:
        return [f"{label}: {error}"]
    return [f"{label}: {finding}" for finding in validate_document(document)]


def validate_document(document: object) -> list[str]:
    if not isinstance(document, dict) or not document:
        return ["a question file is a non-empty map of result fields"]
    if set(document) == {"questions"} and isinstance(document["questions"], dict):
        return [
            "put each question at the top level; a questions: wrapper is a different file"
        ]
    findings: list[str] = []
    for field, entry in document.items():
        name = string_key(field)
        if name is None or not name[0].isalpha():
            findings.append(f"{field}: a result field starts with a letter")
            continue
        findings.extend(validate_question(name, entry))
    return findings


def validate_question(field: str, entry: object) -> list[str]:
    if not isinstance(entry, dict):
        return [f"{field}: a question is a map with instructions"]
    unknown = set(entry) - QUESTION_KEYS
    findings = [f"{field}: unknown key {key}" for key in sorted(unknown, key=str)]
    if "type" in entry:
        findings.append(f"{field}: drop type; criteria or schema decides the kind")
    instructions = entry.get("instructions")
    if not isinstance(instructions, str) or instructions.strip() == "":
        findings.append(f"{field}: instructions are required")
    elif JSON_FENCE in instructions.lower():
        findings.append(
            f"{field}: instructions must not tell the model to emit a fence; the runner attaches the schema"
        )
    has_criteria = "criteria" in entry
    has_schema = "schema" in entry
    if has_criteria and has_schema:
        findings.append(f"{field}: a question is criteria or schema, not both")
        return findings
    if has_criteria:
        findings.extend(validate_criteria(field, entry["criteria"]))
        return findings
    if has_schema:
        findings.extend(validate_schema_question(field, entry))
        return findings
    findings.append(f"{field}: needs criteria (System One) or schema (LLM value)")
    return findings


def validate_criteria(field: str, criteria: object) -> list[str]:
    if isinstance(criteria, list):
        return validate_score(field, criteria)
    if isinstance(criteria, dict):
        return validate_menu(field, criteria)
    return [f"{field}: criteria are a yes/no or choice map, or a score list"]


def validate_menu(field: str, criteria: dict[object, object]) -> list[str]:
    options: list[tuple[str, object]] = []
    findings: list[str] = []
    for key, meaning in criteria.items():
        name = string_key(key)
        if name is None:
            findings.append(f"{field}: option id must be a word, not {key!r}")
            continue
        options.append((name, meaning))
    if findings:
        return findings
    names = {name for name, _ in options}
    if names == {YES, NO}:
        return validate_yes_no(field, options)
    if not options:
        return [f"{field}: a choice needs at least one option"]
    if len(options) > MAX_CHOICE_OPTIONS:
        return [
            f"{field}: a choice allows at most {MAX_CHOICE_OPTIONS} options, not {len(options)}"
        ]
    for name, meaning in options:
        if not isinstance(meaning, str) or meaning.strip() == "":
            findings.append(f"{field}: option {name} needs a meaning")
    return findings


def validate_yes_no(field: str, options: list[tuple[str, object]]) -> list[str]:
    findings: list[str] = []
    for name, meaning in options:
        if not isinstance(meaning, str) or meaning.strip() == "":
            findings.append(f"{field}: {name} needs a meaning")
    return findings


def validate_score(field: str, levels: list[object]) -> list[str]:
    if len(levels) < MIN_SCORE_LEVELS:
        return [
            f"{field}: a score needs at least {MIN_SCORE_LEVELS} levels, not {len(levels)}"
        ]
    findings: list[str] = []
    for index, level in enumerate(levels):
        where = f"{field}: level {index}"
        if not isinstance(level, dict):
            findings.append(f"{where} is a map with what")
            continue
        what = level.get("what")
        if not isinstance(what, str) or what.strip() == "":
            findings.append(f"{where} needs a what")
        examples = level.get("examples")
        if examples is None:
            continue
        if not isinstance(examples, list) or any(
            not isinstance(item, str) or item.strip() == "" for item in examples
        ):
            findings.append(f"{where} examples are non-empty strings")
    return findings


def validate_schema_question(field: str, entry: dict[str, object]) -> list[str]:
    findings = validate_schema(field, entry["schema"])
    examples = entry.get("examples")
    if not isinstance(examples, list) or not examples:
        findings.append(f"{field}: a schema question needs at least one example")
        return findings
    for index, example in enumerate(examples):
        findings.extend(validate_example(field, index, example, entry["schema"]))
    return findings


def validate_schema(field: str, schema: object) -> list[str]:
    if not isinstance(schema, dict) or not schema:
        return [f"{field}: schema is a JSON Schema object"]
    kind = schema.get("type")
    if kind == "object":
        if "properties" not in schema:
            return [f"{field}: an object schema needs properties"]
        return []
    if kind == "array":
        if "items" not in schema:
            return [f"{field}: an array schema needs items"]
        return []
    if kind in SCALAR_TYPES:
        if not SCALAR_CONSTRAINTS & set(schema):
            return [
                f"{field}: a {kind} schema needs a constraint; unconstrained prose is not an answer"
            ]
        return []
    if any(key in schema for key in ("oneOf", "anyOf", "allOf", "$ref")):
        return []
    return [f"{field}: schema needs type object or array, or a constrained scalar"]


def validate_example(
    field: str, index: int, example: object, schema: object
) -> list[str]:
    where = f"{field}: example {index + 1}"
    if isinstance(example, str):
        if example.strip() == "":
            return [f"{where} is empty"]
        return []
    if not isinstance(example, dict):
        return [f"{where} is a string, or prompt and answer"]
    unknown = set(example) - EXAMPLE_KEYS
    findings = [f"{where} has unknown key {key}" for key in sorted(unknown, key=str)]
    prompt = example.get("prompt")
    if not isinstance(prompt, str) or prompt.strip() == "":
        findings.append(f"{where} needs a prompt")
    if "answer" not in example:
        findings.append(f"{where} needs an answer")
    elif isinstance(schema, dict):
        findings.extend(answer_matches(where, example["answer"], schema))
    return findings


def answer_matches(where: str, answer: object, schema: dict[str, object]) -> list[str]:
    kind = schema.get("type")
    if kind == "array" and not isinstance(answer, list):
        return [f"{where} answer must be an array"]
    if kind == "object" and not isinstance(answer, dict):
        return [f"{where} answer must be an object"]
    if kind == "string" and not isinstance(answer, str):
        return [f"{where} answer must be a string"]
    if kind in {"number", "integer"} and (
        isinstance(answer, bool) or not isinstance(answer, (int, float))
    ):
        return [f"{where} answer must be a number"]
    if kind == "boolean" and not isinstance(answer, bool):
        return [f"{where} answer must be a boolean"]
    return []


def files_of(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(
            item
            for item in path.iterdir()
            if item.suffix in {".yaml", ".yml"} and item.is_file()
        )
    return [path]


def validate_path(path: Path) -> list[str]:
    if not path.exists():
        return [f"{path}: not found"]
    findings: list[str] = []
    for item in files_of(path):
        findings.extend(validate_text(item.read_text(encoding="utf-8"), str(item)))
    if path.is_dir() and not files_of(path):
        findings.append(f"{path}: no question files")
    return findings


def self_test() -> list[str]:
    cases = [
        (
            "yes/no",
            "Ready:\n  instructions: Is it ready?\n  criteria: {true: Yes., false: No.}\n",
            True,
        ),
        (
            "choice",
            "Kind:\n  instructions: Which kind?\n  criteria: {bug: Broken., task: Other.}\n",
            True,
        ),
        (
            "standing option",
            "Project:\n  instructions: Which project?\n  criteria: {new: None fit.}\n",
            True,
        ),
        (
            "score",
            "Strength:\n  instructions: How hard?\n  criteria:\n    - {what: Easy.}\n    - {what: Hard.}\n",
            True,
        ),
        (
            "schema",
            "Goals:\n  instructions: What are the goals?\n  schema: {type: array, items: {type: string}}\n  examples:\n    - {prompt: add export, answer: [Add a CSV export.]}\n",
            True,
        ),
        (
            "string example",
            "Pieces:\n  instructions: Split it.\n  schema: {type: array, items: {type: string}}\n  examples: ['Prompt: a. Pieces: [\"a\"]']\n",
            True,
        ),
        (
            "mixed",
            "Ready:\n  instructions: Ready?\n  criteria: {true: Yes., false: No.}\nTitle:\n  instructions: Name it.\n  schema: {type: string, minLength: 1}\n  examples:\n    - {prompt: fix the total, answer: Fix the invoice total.}\n",
            True,
        ),
        (
            "blank instructions",
            "Ready:\n  instructions: '  '\n  criteria: {true: Yes., false: No.}\n",
            False,
        ),
        (
            "both",
            "Ready:\n  instructions: Ready?\n  criteria: {true: Yes., false: No.}\n  schema: {type: object, properties: {x: {type: string}}}\n",
            False,
        ),
        ("neither", "Ready:\n  instructions: Ready?\n", False),
        (
            "type key",
            "Ready:\n  type: noul\n  instructions: Ready?\n  criteria: {true: Yes., false: No.}\n",
            False,
        ),
        (
            "wrapper",
            "questions:\n  Ready:\n    instructions: Ready?\n    criteria: {true: Yes., false: No.}\n",
            False,
        ),
        (
            "one level",
            "Strength:\n  instructions: How hard?\n  criteria:\n    - {what: Easy.}\n",
            False,
        ),
        (
            "prose schema",
            "Analysis:\n  instructions: Write the analysis.\n  schema: {type: string}\n  examples: ['a long essay']\n",
            False,
        ),
        (
            "fence",
            "Tickets:\n  instructions: 'End with a ```json block.'\n  schema: {type: array, items: {type: object, properties: {title: {type: string}}}}\n  examples:\n    - {prompt: a bug, answer: [{title: Fix it}]}\n",
            False,
        ),
        (
            "no example",
            "Goals:\n  instructions: What are the goals?\n  schema: {type: array, items: {type: string}}\n",
            False,
        ),
        ("empty", "", False),
        (
            "answer type",
            "Goals:\n  instructions: What are the goals?\n  schema: {type: array, items: {type: string}}\n  examples:\n    - {prompt: add export, answer: not-a-list}\n",
            False,
        ),
    ]
    findings: list[str] = []
    for name, text, expect_ok in cases:
        errors = validate_text(text, name)
        if expect_ok and errors:
            findings.append(f"{name}: expected pass, got {errors}")
        if not expect_ok and not errors:
            findings.append(f"{name}: expected fail")
    if CANONICAL_DIR.is_dir():
        canonical = validate_path(CANONICAL_DIR)
        if canonical:
            findings.extend(canonical)
    for name in BROKEN_FILES:
        path = BROKEN_DIR / name
        if path.is_file() and not validate_path(path):
            findings.append(f"{path}: expected this chat prompt to fail")
    return findings


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[1] == "--self-test":
        findings = self_test()
        if findings:
            print("\n".join(findings))
            return 1
        print("self-test: ok")
        return 0
    if len(argv) < 2 or argv[1].startswith("-"):
        print(f"usage: {argv[0]} FILE|DIR [FILE|DIR...] | --self-test", file=sys.stderr)
        return 2
    failed = False
    for raw in argv[1:]:
        path = Path(raw)
        findings = validate_path(path)
        if findings:
            failed = True
            print("\n".join(findings))
        else:
            print(f"{path}: ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
