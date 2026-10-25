---
name: 16 Recover Document Structure
description: Reconstruct lost Markdown structure with two sequential batched passes (stitch, then classify) that decide boundaries and block types, while code renders markers onto the untouched original text.
---

ORIGINAL SOURCE: https://docs.typesafe.ai/cookbooks/autoformat
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

You have plain text that lost its structure (hard-wrapped lines, stripped markup) and need it back as Markdown without letting a generative model rewrite the wording.

## What it demonstrates

The cookbook reconstructs a 28-line, hard-wrapped team memo about a build-system migration into 17 correctly formatted Markdown blocks (headings, lists, code block, warning callout, quote) using two sequential requests, because pass two depends on the blocks pass one produces.

## Steps / call shape

1. **Stitch (16 questions, 0.32s):** one `Noul` per adjacent line pair — "Does this line pick up mid-sentence, continuing a sentence left unfinished at the end of the previous line?" Code merges lines by threshold: 0.2 after a dangling line (no terminal punctuation), 0.5 after terminal punctuation (`.!?:;`).
2. **Classify (62 questions, 0.51s):** one `Choice` per merged block selecting from `heading`, `paragraph`, `list_item`, `quote`, `code`, `callout`, with companion questions for heading level, list ordering, and callout kind asked in the same batch.
3. **Render in code:** add Markdown markers onto the original wording — no text is regenerated.

```text
lines -> Noul per adjacent pair (stitch) -> merged blocks -> Choice per block (classify) -> Markdown render
```

## Results / numbers

- Input: 28 non-blank lines. Output: 17 reconstructed blocks.
- Cost: 10,211 tokens, 0.8 seconds total, $0.0015.
- Confidence: one block scored 0.43 (paragraph vs. list_item ambiguity); the rest scored 0.65-1.00.
- The narrower question "mid-sentence" outperformed a vaguer "same paragraph" framing in the cookbook's comparison: 17 blocks recovered correctly vs. 12 with the vaguer question.

## Pitfalls

- Keep direct evidence deterministic: blank lines, explicit markers, IDs, and text concatenation are code's job — reserve TypeSafe for genuinely ambiguous structure.
- Don't collapse the two passes into one call — classification needs the stitched blocks pass one produces, so the dependency is real, not an optimization to remove.
- A vague question ("same paragraph?") produces worse boundaries than a narrow one ("mid-sentence?") — pick the question that targets the precise fact deciding the merge.
- Every output character must trace back to the original input; if a rewrite creeps in, the auditability the pattern is built for is gone.

## Related cookbooks

- `15-Line-by-Line-Semantic-Search.md` — the same use of line IDs as anchor text the model reads directly rather than rewrites.
- `13-Question-Parallel-Set.md` — the batching technique each pass here relies on (one call per pass, not one call per line).
- `23-Structured-Extraction-Cascade.md` — another two-stage pipeline where the second stage depends on the first stage's output.
</content>
