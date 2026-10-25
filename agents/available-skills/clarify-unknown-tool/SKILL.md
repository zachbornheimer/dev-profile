---
name: clarify-unknown-tool
description: Use when the user names a tool the agent cannot place — the name appears in neither ~/.agents nor a repo, and a web search for "<name> cli" returns several unrelated products or nothing definite — and the agent has not yet asked the user what it is. Stops the guessing loop and asks for a name, URL, or install source before any more searching, fetching, or installing.
user-invokable: true
---

# Clarify an unknown tool

Searching harder does not resolve a name collision. Two products can share a
name; a web search for `<name> cli` returns both and neither is wrong. Every
further Glob, Grep, fetch, or install attempt spends tokens without adding
information. Ask the user instead.

## Before anything else: one probe, then stop

When a user-named tool resolves nowhere on disk, spend exactly one call
identifying it before any local fan-out or question:

- `run_command`: `command -v <name>; <name> --help` — a binary names itself.
- or `web_search "<name> cli"` — a product page names the binary and installer.

Do not Glob or Grep `~`, `~/Developer`, or `~/.claude` for the name: a name that
is not on disk cannot be found on disk, and ten local searches for a typo once
cost seven turns. If the probe resolves the name, proceed. If it does not, the
trigger below holds.

## Trigger

All three must hold:

1. The user mentions a tool name (a CLI, app, binary, package, or service).
2. The name does not resolve:
   - the one probe above (`<name> --help` via run_command, or a web search for
     `<name> cli`) is ambiguous — multiple unrelated products, or no single
     authoritative product page — and a Glob/Grep over `~/.agents` is empty.
3. You have not yet asked the user about this tool.

Do not trigger on a name that resolves cleanly, on a name the user already
described, or on a second tool mentioned after you have already asked.

## Instruction

Ask the user to clarify the tool before any further searching or fetching. One
message, three options, no more probing first:

> I can't place `<name>`. Which one is it — a URL, or the package manager /
> install source (brew, npm, mise, cargo, an internal repo)?

Do not guess a product and proceed, do not install anything to find out, and do
not run more searches hoping the ambiguity clears. Wait for the answer.

## After the user answers

- Write down what the user gave you (name + URL or install source) before acting,
  so the identification is not lost when context compacts.
- If the user names an install source, verify it exists (`brew info <name>`,
  `npm view <name>`) before installing.
- If the user also cannot identify it, treat it as unresolved: say so plainly and
  ask for the exact command they saw it in.

## What this is not

Not a rule against searching. Search once, cheaply, then stop. The failure this
prevents is the loop where an agent keeps searching, picks the most popular
same-named product, and builds the wrong thing.
