---
name: 26 Hierarchical Classification
description: Represent taxonomy edges as Choice probability distributions and run parallel beam search in code so one ambiguous early classification doesn't permanently misroute the final leaf.
---

ORIGINAL SOURCE: https://docs.typesafe.ai/cookbooks/hierarchical_classification
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

Labels form a hierarchy (taxonomy, filesystem, ontology) too large for a single flat `Choice` over every leaf. Use this whenever greedy top-down classification is worth improving because one wrong early turn otherwise dooms the whole traversal.

## What it demonstrates

The cookbook classifies documents through four real hierarchies — CPC patent classes (~10,000+ nodes), Shopify product categories (~7,000+ nodes), MeSH biomedical subjects (~30,000+ nodes, DAG expanded to tree paths), and a snapshot of the CookSafe repository file tree (~300+ nodes) — comparing greedy traversal (always take the top child) against beam search that keeps the `K` best partial paths at every level. Across the 4 hierarchies, beam search (K=3) matched the expected leaf in all 4 cases; greedy matched only 2 of 4, failing on CPC patents and Shopify products.

## Steps / call shape

At each level: create one `Choice` per active frontier node, send those frontier questions together, expand children using the returned edge probabilities, score paths in code, and keep the best `K`. Stop when candidate paths reach leaves.

```python
def choose(state: str, labels: tuple[str, ...]) -> dict[str, float]:
    """Ask one atomic direct-child question and return its probability distribution."""
    if len(labels) == 1:
        return {labels[0]: 1.0}
    question, keys = child_question(labels)
    response = client.system_one(state=state, questions={"child": question}, model=MODEL)
    return {label: response.answers["child"].probabilities[key] for key, label in keys.items()}

def beam_search(hierarchy: Hierarchy) -> dict:
    """Parallel width-K beam search using geometric-mean probability."""
    beam = [{"path": (), "probability_product": 1.0, "decision_count": 0, "score": 1.0}]
    # expand each frontier node's Choice in parallel, score paths, retain the best K,
    # stop once retained paths are all leaves
```

Paths are scored by the geometric mean of their edge probabilities — `product(edge_probabilities) ** (1 / decisions)` — so shallow and deep leaves compare fairly. A separation ratio (top path score / second path score) near 1x signals an ambiguous classification; a large ratio signals a clear one.

## Results / numbers

| Hierarchy | Nodes | Greedy correct | Beam K=3 correct |
|---|---|---|---|
| CPC patents | ~10,000+ | No | Yes |
| Shopify products | ~7,000+ | No | Yes |
| MeSH biomedical | ~30,000+ | Yes | Yes |
| CookSafe files | ~300+ | Yes | Yes |

Beam search matched 4 of 4 expected leaves; greedy matched 2 of 4.

## Pitfalls

- For very deep hierarchies (>10 layers), multiplying probabilities directly loses floating-point precision — use `exp(mean(log(probs)))` instead.
- Beam width `K` trades latency against accuracy; parallel per-level API calls keep the wall-clock cost low, but a wider beam still costs more calls per level.
- One early greedy mistake cannot be recovered — that's the entire reason to keep multiple candidate paths rather than the single top child.
- Keep taxonomy loading/versioning deterministic, and log traversed nodes and edges so misclassifications are attributable to a specific edge for error analysis.

## Related cookbooks

- `28-Classification-Using-Confidence.md` — uses the same `Choice` confidence signal for a single-level decision (back off to a parent) rather than multi-level beam search.
- `33-Semantic-Map-Reduce.md` — applying narrow `Choice`/`Noul`/`Score` judgments across many records, the same atomic-question building block this cookbook composes into a tree search.
