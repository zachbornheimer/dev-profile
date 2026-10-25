# Research and bounded experiment

Official sources (design references, not evidence of this harness's performance):

- [basic_memory.md](https://docs.typesafe.ai/cookbooks/basic_memory.md): gate enduring
  source facts, not assistant-inferred facts; validate thresholds on labelled held-out data.
- [classifying_rag_passages.md](https://docs.typesafe.ai/cookbooks/classifying_rag_passages.md):
  separate relevance, contradiction and injection questions; routing belongs in code.
- [citation_check.md](https://docs.typesafe.ai/cookbooks/citation_check.md): exact source
  matching and contextual claim support are different checks.
- [autoresearch_feature_discovery.md](https://docs.typesafe.ai/cookbooks/autoresearch_feature_discovery.md):
  labelled held-out evaluation, not self-reported improvement.
- [Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685):
  judge bias and limitations motivate independent tool evidence and human labels.

## Existing local experiment

`dev-profile-2/report.json` under the active profile's scratch/learnings directory
contains a completed sampled run and saved prune, consolidate and verify requests and
responses. Its one prompt-act candidate was rejected for low usefulness; no accepted
rules. Satisfaction and output quality remain unknown. Goal/decision lineage and the
other absent dimensions are unknown, not implied coverage. This is not a baseline
comparison, compression gain, calibration study or measured satisfaction improvement.
No personal diagnosis is justified. Quotes remain verbatim.

Offline validation (no local inference or hosted API calls):

```sh
mise run -C ~/.agents/available-skills/learnings proof -- /path/to/report.json
```

Optional `--out /new/path/full-report.json` writes a derived full report with explicit
unknown dimensions, preserving the original report and raw artifacts. Proof checks
schema, actual original source text and metadata, exact quotes, saved local model
requests/responses, typed probabilities and recomputed dispositions. It proves artifact
consistency, not cryptographic model provenance, claim truth or completeness of a session.
Thresholds remain experimental; independent overlapping windows need manual review.
