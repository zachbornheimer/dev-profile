---
name: payload
description: Use when the user asks to see "the payload", "what you sent", "the request body", "the wire body", or the raw request behind a tool call or API request. Deliver the verbatim wire request body, never a summary, a log of tool calls, or a description of the request.
---

# Payload

"Show me the payload" means the bytes on the wire: the exact request body as sent.

## The rule

1. Find the verbatim request body for the call in question — the JSON actually sent
   over HTTP (or stdio), including headers/`path`/`id` fields when the transport
   frames them.
2. Save it whole to a file (for example `~/Downloads/payload.json`) and say the
   path. Large bodies go to a file, not the chat.
3. Never substitute:
   - a list of the tool calls that produced it,
   - a summary or excerpt,
   - a re-rendering from the source that built it.

## Why verbatim

The user debugs the wire itself — fallbacks, schema shapes, silent model swaps.
A summary hides exactly the bytes they are debugging.

## Failure mode this prevents

The user asking for the payload twice because the first answer showed tool-call
logs instead of the request body (omp:01a174bd, turns 21-22).
