# Example index

Use this index by **problem shape**, not by industry. Examples are analogies rather than a closed list of supported use cases.

| If you see this...                                      | Read                                                                                                                          |
| ------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Need to discover whether TypeSafe fits at all           | `00-Opportunity-Discovery.md`, `01-When-to-Use-TypeSafe.md`                                                                   |
| Generative LLM returns labels/JSON/booleans/scores      | `29-Replace-LLM-Prompt-and-Parse.md`, `17-Function-Calling.md`                                                                |
| Regex/parser finds candidates but cannot infer meaning  | `30-Hybrid-Parsing-and-Semantic-Selection.md`, `24-Date-Extraction.md`, `25-Pre-Parsed-Value-Extraction.md`                   |
| A model/tool/extractor needs fact or policy checking    | `31-Universal-Verification-Layer.md`, `21-Verify-Citations.md`, `22-LLM-Guardrails.md`, `23-Structured-Extraction-Cascade.md` |
| Need to choose model/tool/skill/handler                 | `32-AI-Harness-and-Model-Routing.md`, `09-Intent-Routing.md`, `17-Function-Calling.md`, `18-Skill-Suggestion.md`              |
| Same state needs many independent judgments             | `06-Speculative-Fan-Out.md`, `13-Question-Parallel-Set.md`                                                                    |
| Need relevance search/ranking over candidates           | `14-Re-Rank-Search-Results.md`, `15-Line-by-Line-Semantic-Search.md`                                                          |
| Need large-scale semantic labels/features               | `33-Semantic-Map-Reduce.md`, `27-Autoresearch-Feature-Discovery.md`                                                           |
| Interactive UI needs bounded natural-language decisions | `34-Real-Time-Interactive-Decisions.md`, `10-Smart-Home-Assistant.md`                                                         |
| Team rules require interpretation rather than syntax    | `35-Semantic-Code-and-Content-Linting.md`                                                                                     |
| Humans repeatedly review text into bounded outcomes     | `36-Manual-Review-to-Confidence-Gated-Automation.md`, `07-Confidence-Gated-Routing.md`                                        |
| Need several semantic dimensions combined by policy     | `08-Composite-Scoring.md`                                                                                                     |
| Need entity/record matching                             | `19-Entity-Alignment.md`                                                                                                      |
| Need to choose RAG context before generation            | `20-Classify-RAG-Passages.md`, `14-Re-Rank-Search-Results.md`                                                                 |
| Need classification through a very large hierarchy      | `26-Hierarchical-Classification.md`                                                                                           |
| Need uncertainty-aware broader fallback                 | `28-Classification-Using-Confidence.md`                                                                                       |
| Need to reconstruct structure from unstructured text    | `16-Recover-Document-Structure.md`                                                                                            |
| Need a judgment about a screenshot, scan, or camera frame | `37-Images-and-Box.md`, `04-Choosing-Primitives.md`                                                                         |

## Generalization rule

If the user's domain is not represented, map it to a decision shape:

- **Which known option?** -> Choice
- **Does this property hold?** -> Noul
- **How much / how strong / how relevant?** -> Score
- **Where is it in an image?** -> Box, plus a presence Noul
- **Many independent judgments over one state?** -> batch them
- **Decision tree over one state?** -> speculative fan-out
- **Consequential or uncertain action?** -> confidence/probability gate in code
- **Candidate generation is easy but intent is hard?** -> deterministic candidates + semantic selection
- **Producer may be wrong?** -> semantic verification layer
