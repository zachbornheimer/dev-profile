# Hierarchical file classification with TypeSafe — design contract (v1)

Status: design only, no code changed. Target: `~/.agents/skills/typesafe-ai/scripts/classify_file.py` (plus the new modules named below).

## 0. What I read and what I found in the baseline

- The current pipeline has five steps: `observe` → `prefilter` → `strong_project_match` → a request with one relevance Noul per candidate (IDF shortlist of 8 plus 6 `personal:*` buckets), a `kind` Choice and a 6-way `disposition` Choice → `decide`, which applies the legality table and the per-disposition floors.
- Results in `/tmp/organize/desktop.jsonl` (119 items):
  - Disposition: keep 52, move-to-repo 25, trash-candidate 20, personal-docs 17, archive 4, file-to-linear 1.
  - Reason: 28 "confidence below floor", 12 "disposition illegal for project type".
  - So 40 items (34%) ended as `keep` at confidence 0.0 because the gates threw away the model's answer.
- Root causes:
  1. **The disposition Choice is asked before the project is known.** The model picks from all 6 options and code then vetoes 12 of them (illegal pairs). Many real issue lists came out `keep 0.00` (flight-fix-list.md, everest-problems.md, ev-ui-issues*.md, 2026-09-01-builder-ui-problems.md).
  2. **Recall of the flat shortlist is purely lexical.** For NAS-Rebuild-GOAL.md, the real `zachbornheimer/homelab` keywords are `homelab, cue, docker, compose`, with no "nas" and no "gorillabank". The file's tokens miss homelab, and the always-offered `personal:other` wins at 0.33.
  3. **Trash is judged only by a semantic "backup/throwaway" signal.** Nothing checks whether a file can be recreated or holds private data:
     - `mail-import-backup/` contains `Import.mbox`, which is irreplaceable mail.
     - `Dorico Diagnostics.zip` contains `Activation Manager/.../config.dat` and `settings.json`, which is license data.
     - Both came out trash-candidate at 0.91 and 0.65.
  4. **`answers.choice()` returns only `(choice, confidence)`.** Beam search needs the full distribution. The docs confirm Choice answers carry `probabilities` (a dict from option to probability) alongside `confidence`.
- TypeSafe guidance used:
  - Cookbook `hierarchical_classification`: beam width 3, one `Choice` per frontier node, path score = geometric mean of edge probabilities, and edges with a single child are not counted.
  - Cookbook `classification_using_confidence`: back off to the parent below a cutoff. Their 0.9 was tuned on their own data, so it is not copied here.
  - Examples 13 (batch the shared state once), 07/05 (gate by consequence, log outcomes), 19 (deterministic blocking before model judgment), 36 (review queue → labeled data → gated automation).

## 1. Taxonomy data file

### 1.1 Location and ownership

- Builder: `~/.agents/skills/organize-files/scripts/build_taxonomy.py`. It is pure and deterministic: no network and no clock in the output except `generated_at`.
- Inputs, all under `~/.agents/skills/organize-files/data/`:
  - `repo-catalog.json`, which exists: 165 repos, 47 archived.
  - `linear-projects.json`, new: `[{"name": "...", "id": "..."}]`, a snapshot of the Linear project list.
  - `personal-areas.json`, new: a short curated list of `~/Documents` subareas (see 1.4).
  - `taxonomy-overrides.json`, new: small and reviewed (see 1.3).
- Output: `~/.agents/skills/organize-files/data/taxonomy.json`.
- Loader and validator: new `~/.agents/skills/typesafe-ai/scripts/taxonomy.py`. The classifier never builds the taxonomy; it only loads and validates it. This keeps "taxonomy loading/versioning deterministic", per example 26.

### 1.2 Schema (`schema_version: 1`)

```json
{
  "schema_version": 1,
  "taxonomy_version": "1.<sha256(canonical inputs)[:12]>",
  "generated_at": "2026-09-23T00:00:00Z",
  "sources": {
    "catalog": { "path": "...", "generated_at": "...", "sha256": "..." },
    "linear": { "path": "...", "sha256": "..." },
    "personal": { "path": "...", "sha256": "..." },
    "overrides": { "path": "...", "sha256": "..." }
  },
  "nodes": [
    {
      "id": "area:homelab",
      "parent": null,
      "depth": 1,
      "type": "area",
      "label": "Homelab & NAS",
      "criteria": "<=180 chars; used verbatim as Choice criteria",
      "tokens": [
        "homelab",
        "nas",
        "gorillabank",
        "synology",
        "lidarr",
        "docker"
      ]
    },
    {
      "id": "product:homelab",
      "parent": "area:homelab",
      "depth": 2,
      "type": "product",
      "label": "homelab",
      "criteria": "...",
      "tokens": ["..."],
      "derived_by": "override:merge"
    },
    {
      "id": "leaf:repo:zachbornheimer/homelab",
      "parent": "product:homelab",
      "depth": 3,
      "type": "leaf",
      "leaf_kind": "repo",
      "project_key": "zachbornheimer/homelab",
      "local_path": "/Users/zbornheimer/Developer/Personal/homelab",
      "aliases": [],
      "criteria": "...",
      "tokens": ["..."]
    },
    {
      "id": "leaf:linear:Homelab",
      "parent": "product:homelab",
      "depth": 3,
      "type": "leaf",
      "leaf_kind": "linear",
      "project_key": "linear:Homelab",
      "criteria": "..."
    },
    {
      "id": "leaf:personal:finance",
      "parent": "product:personal-docs",
      "depth": 3,
      "type": "leaf",
      "leaf_kind": "personal",
      "project_key": "personal:finance",
      "destination": "~/Documents/Finance",
      "criteria": "..."
    }
  ]
}
```

Flat node list with parent pointers. Ids are ASCII: `[a-z0-9:/._-]`, plus the Linear name kept verbatim after `leaf:linear:`.

Choice option keys are generated slugs `o0..oN` plus `other`. The request builder keeps an in-memory `{slug: node_id}` map, as the cookbook does with `c0`, `c1`. This keeps odd characters (spaces, `×`) out of criteria keys.

**The validator in `taxonomy.py` raises; the caller then falls back to flat mode with reason "taxonomy invalid".** It checks that:

- ids are unique and every parent exists;
- `depth == parent.depth + 1` and every leaf is at depth 3;
- each `project_key` is unique across leaves;
- every non-leaf has at least one child;
- every node has non-empty `criteria` (at most `DESCRIPTION_CHARS`, 180);
- the root has at most `FILE_TAXONOMY_MAX_AREAS` (10) areas;
- `schema_version` is known.

### 1.3 Derivation rules (the builder, in order)

- **P0 Areas from orgs.** Map org → area using `overrides.org_areas`. This is a 6-entry identity table, not a list of repos:
  - `Software-Automation-Holdings-LLC`, `isa-sdk`, `ninjaquoter` → `area:insurance-software`
  - `ZAB-AI-LLC` → `area:zab-ai`
  - `zysys` → `area:zysys`
  - `zachbornheimer` → `area:personal-software`
  - Synthetic areas: `area:homelab`, `area:personal-life`, `area:ventures`.
  - `overrides.repo_area` moves individual repos. This is the only way homelab gets its members; see forks F4.
- **P1 Token enrichment.** A repo's tokens are:
  - its basename;
  - all keywords (normalized, generic stopwords removed with the existing `_words` / `FILE_GENERIC_SCORING_STOPWORDS`);
  - words from `description_proposed` whose catalog document frequency is ≤ 3.

  This fixes the homelab recall gap without hand-editing keywords: nas-recovery's description names gorillabank and Synology.
- **P2 Product families.** Within an area, take a repo's first 4 keywords (normalized). The family key is the keyword with the lowest catalog-wide document frequency (DF) such that DF ≥ 2, the keyword is shared by at least 2 repos in the same area, and DF ≤ `FAMILY_MAX_DF` (12). The DF cap rejects "wordpress", "sdk", "php" and similar. On a tie, pick the key with more live members, then sort alphabetically.
  - Repos with the same family key become `product:<key>`.
  - Repos with no family become their own product: `product:<basename>`, with exactly one leaf.
  - Expected families: rapidsign, zyins, eapp, bpp/best plan pro, isa, obsidian-backup, prepiq, zwsip, flight, ninjaquoter, zab-ai.
- **P3 Archived fold.** An archived repo is never a leaf. You never move docs into an archived repo.
  - If its product has any live leaf, it becomes an `alias` on the live leaf with the most token overlap (tie → newest `pushed_at`). Its tokens merge into that leaf, so the IDF shortlist and strong match still find it.
  - If the family has no live member, it becomes one leaf with `"archived": true` under its product. Legality then drops move-to-repo (see 4.2).
- **P4 Linear attach.** Normalize a Linear project name into tokens, removing launch/exit/summit/years and similar filler with a tiny stoplist in the builder.
  - Attach it as a `leaf:linear:*` sibling under the product whose name or tokens contain one of its tokens with DF ≤ 2. Examples:
    - AgentMux → agentmux
    - ZQ → zq
    - Flight → flight
    - Evident Output → evident-output
    - librarian → librarian
    - PrepIQ → prepiq
    - Obsidian Backup → obsidian-backup
    - Book Bestie Launch → book-bestie
    - DragonGate Portals → portal-builder (via keyword `dragongate`)
    - ISJAC, ISJAC Summit 2027 launch → isjac-site
    - Ansible for Zysys Hosting → ansible-infra
    - Progress Library → progress
    - Homelab → homelab (after P0 override)
  - Unattached projects go to `overrides.linear_area`, else to `area:ventures`, each as its own product. That covers Hypeddit Exit, PPG ×4 (grouped by the shared "PPG" token under P2 logic), Site Status SaaS, ZachStacks Launch, and AI Harness Code Efficiency.
- **P5 Personal.** `area:personal-life` → a single product `product:personal-docs` → one leaf per entry in `personal-areas.json`, each with a `destination`. `personal:other` is deliberately not a leaf. Its job becomes the `other` escape on the leaf Choice, which backs off to `product:personal-docs` with destination `~/Documents`. This is the direct fix for "personal:other swallows everything".
- **P6 Criteria text.**
  - Leaf: `description_proposed` truncated to 180 characters.
  - Product: "Products: <member basenames>; <top 6 tokens>".
  - Area: the override label plus the top 8 tokens by member frequency.
  - All generated; overrides may replace the criteria of any node.
- **P7 Sibling cap.** If an area has more than `FILE_TAXONOMY_FULL_CHOICE_MAX_SIBLINGS` (12) products, the builder does not fail. It marks the area `"large": true`, and the request builder shortlists within it (see 2.3). `area:personal-software` (about 40 singletons) and `area:insurance-software` will be large.

`taxonomy-overrides.json` holds only: `org_areas`, `area_labels`, `repo_area`, `product_merge` (e.g. homelab + nas-recovery + carve-reconcile → `product:homelab`, if Zach wants that), `linear_area`, and `criteria`. Each entry has a `"why"` string. The builder prints which rule placed each leaf as `derived_by`, for diff review.

### 1.4 Versioning

- `taxonomy_version = "<schema_version>.<first 12 hex of sha256 over canonical JSON of all four inputs>"`. The same inputs always give the same version.
- Every classification output and every decision record carries `taxonomy_version`.
- Node ids are stable across rebuilds as long as the repo, family key or Linear name is unchanged. Tuning joins decisions to the taxonomy on node id, not on version.
- The builder writes `taxonomy.json` only when content changes, and prints a node-level diff (added, removed, moved) when an old file exists.

## 2. Per-level request shape

### 2.1 State (the same object in every round, so batching and caching apply)

The existing `_observation_state` fields are kept unchanged: `filename`, `extension`, `size`, `mtime`, `is_dir`, `excerpt` (≤ 20 000 bytes), `entries`. One field is added:

- `source_dir`: the parent directory name, e.g. "Desktop". It will matter later for Downloads and Documents.

The taxonomy is never put in state. It appears only as Choice criteria.

### 2.2 Question ids and primitives

| id                    | primitive                                                                                                                                                        | when                                                                                                         |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `area`                | Choice over all area slugs + `other` ("None of these areas fits; unrelated or unknowable.")                                                                      | round 1                                                                                                      |
| `kind`                | Choice, the existing `KIND_CRITERIA`                                                                                                                             | round 1                                                                                                      |
| `flag_backup`         | Noul: "Is this file a backup, export copy, or duplicate of data that also exists elsewhere, rather than the primary copy? Use `filename`, `entries`, `excerpt`." | round 1                                                                                                      |
| `flag_issue_list`     | Noul: "Is `excerpt` primarily a list of bugs, tasks, or problems that still need doing?"                                                                         | round 1                                                                                                      |
| `flag_evidence`       | Noul: "Is this captured output — a log, transcript, test/proof run, or diagnostic bundle — rather than authored prose or code?"                                  | round 1                                                                                                      |
| `flag_private`        | Noul: "Do `excerpt` or `entries` contain credentials, license/activation data, email/mail archives, or private personal information?"                            | round 1                                                                                                      |
| `flag_regenerable`    | Noul: "Could this file be recreated at will by re-running a tool or re-exporting, so deleting it loses nothing?"                                                 | round 1 (a 5th flag, added by me; see 4.1)                                                                   |
| `product@<area-slug>` | Choice over that area's products (full list, or shortlisted if the area is large) + `other`                                                                      | speculatively in round 1 for the top `FILE_TAXONOMY_SPECULATIVE_AREAS` (2) areas by prior; otherwise round 2 |
| `leaf@<product-slug>` | Choice over the product's leaves + `other`                                                                                                                       | only for products with more than 1 leaf; round 2, or round 3                                                 |

The `disposition` Choice is removed in hierarchical mode. Disposition is computed (section 4).

### 2.3 Deterministic prior and shortlist reuse

- `_catalog_matches` and `_linear_matches` are kept as they are, scoring leaves. They now score against node tokens: taxonomy leaf tokens replace catalog-entry tokens, and the DF is recomputed over leaves.
- **Area prior** = the sum of the scores of shortlisted leaves under that area. The two top-prior areas get a speculative `product@` question in round 1. With no prior at all, nothing is speculated.
- **Large areas:** product options = products containing a leaf in the IDF shortlist within that area (at most `FILE_PROJECT_CANDIDATE_LIMIT`, 8), padded to at least 4 by the area's products with the most live leaves, plus `other`. Small areas always offer every product. Here the shortlist narrows what is offered; it no longer decides the answer.
- **`strong_project_match` short-circuits:** a strong match resolves to a leaf, or to the successor leaf for an archived alias. The path is fully determined, with implied edge p = 1. Round 1 then carries only `kind` and the 5 flags; there is no area question. `resolved_depth = 3`, `reason = "strong match"`.

### 2.4 Rounds (at most `FILE_TAXONOMY_MAX_ROUNDS` = 3; typically 2; 1 on a strong match)

- **R1:** `area`, `kind`, 5 flags, and `product@A` for the top-2 prior areas.
- After R1: frontier = the top `FILE_TAXONOMY_BEAM_WIDTH` (3) areas by P(area), excluding `other`.
- **R2:**
  - `product@A` for frontier areas not yet asked;
  - `leaf@P` for every multi-leaf product currently among the top-3 depth-2 partials;
  - speculatively, `leaf@P` for multi-leaf products in not-yet-asked frontier areas that are hit by the IDF shortlist.
- **R3:** only `leaf@P` for surviving depth-2 partials that still lack one. If nothing is missing, R3 is skipped.
- On a `JudgmentError` in round ≥ 2: keep the answers already received and resolve with what exists, without failing. Reason = `"partial: <reason>"`. On an error in R1: the existing fallback.

## 3. Beam, scoring, back-off

- **Edges:** p(child | parent) = the Choice `probabilities[slug]`. It is read by a new `answers.choice_distribution(answers, qid) -> dict[str, float]`, which raises if `probabilities` is missing, matching the existing reader style.
- **Single-child edges** have p = 1 and are **not counted** in the score (as in the cookbook).
- **`other`** ends the path at the parent.
- **Path score** (for beam ranking) = the geometric mean of the counted edges: `exp(mean(log(max(p, EPS))))`, with `EPS = 1e-9`. Keep the top K = 3 at each depth; ties are broken by node id.
- **Back-off** (decides `resolved_depth`) uses **prefix mass**, not the geometric mean:
  - mass(node) = the sum, over surviving beam paths through the node, of the plain product of the counted edge probabilities along that path.
  - Walk the best-scoring path from its leaf upward. The resolved node is the deepest node with `mass(node) >= FILE_TAXONOMY_DEPTH_FLOORS[depth]`. If none qualifies, the result is root (`resolved_depth = 0`, `project = "none"`).
  - Why prefix mass: when two homelab leaves split 0.45/0.45, the leaf fails its floor but `product:homelab` has mass 0.9, so the file lands at homelab instead of `none`. This is cookbook 28's back-off, done with the distribution we already have and no extra call.
- Initial floors: `{1: 0.55, 2: 0.40, 3: 0.30}`. They decrease with depth because mass is a product. Mark them `# initial; retune from decisions.jsonl`.
- **Every edge is logged into `edges`** in the output (see 5) for error analysis.

### Constants to add in `constants.py`

```python
FILE_TAXONOMY_SCHEMA_VERSION = 1
FILE_TAXONOMY_BEAM_WIDTH = 3
FILE_TAXONOMY_MAX_ROUNDS = 3
FILE_TAXONOMY_SPECULATIVE_AREAS = 2
FILE_TAXONOMY_FULL_CHOICE_MAX_SIBLINGS = 12
FILE_TAXONOMY_LARGE_AREA_MIN_OPTIONS = 4
FILE_TAXONOMY_MAX_AREAS = 10
FILE_TAXONOMY_PROB_EPSILON = 1e-9
FILE_TAXONOMY_OTHER = "other"
FILE_TAXONOMY_DEPTH_FLOORS = {1: 0.55, 2: 0.40, 3: 0.30}
(
    FILE_FLAG_BACKUP,
    FILE_FLAG_ISSUE_LIST,
    FILE_FLAG_EVIDENCE,
    FILE_FLAG_PRIVATE,
    FILE_FLAG_REGENERABLE(ids),
)
FILE_FLAG_FLOORS = {
    "trash_backup": 0.80,
    "trash_regenerable": 0.70,
    "private_guard": 0.50,
    "issue_to_linear": 0.70,
    "evidence": 0.60,
}
REASON_FILE_STRONG_MATCH = "strong match"
REASON_FILE_BACKOFF = "resolved above leaf"
REASON_FILE_PRIVATE_GUARD = "private data blocks trash"
REASON_FILE_TAXONOMY_INVALID = "taxonomy invalid"
```

Builder-only constants (`FAMILY_MAX_DF = 12`, `DESCRIPTION_TOKEN_MAX_DF = 3`) live in `build_taxonomy.py`.

## 4. Disposition once the path is known

### 4.1 Rule: the disposition is computed, not a Choice

The earlier failures were illegal pairs (the model chose before the project was known) and trash judged without asking "is it recoverable". The rules below are ordered; the first match wins. The output confidence is the minimum of the probabilities that the rule relied on.

| #  | condition                                                                                                  | disposition                                             | confidence                            |
| -- | ---------------------------------------------------------------------------------------------------------- | ------------------------------------------------------- | ------------------------------------- |
| R0 | the prefilter matched (backup suffix, screenshot, media)                                                   | unchanged from today                                    | unchanged                             |
| R1 | `flag_private >= 0.50`                                                                                     | trash is **forbidden** for this file; continue with R3+ | —                                     |
| R2 | `flag_backup >= 0.80` and `flag_regenerable >= 0.70` and not R1                                            | trash-candidate                                         | min(backup, regenerable, 1 − private) |
| R3 | `flag_issue_list >= 0.70` and the resolved product has a `leaf:linear:*`                                   | file-to-linear; destination = that Linear name          | min(issue_list, mass(product))        |
| R4 | resolved leaf is a live repo with `local_path`, and kind ∈ {spec, document, issue-list, script, data-dump} | move-to-repo → `<local_path>/docs`                      | mass(leaf)                            |
| R5 | resolved leaf is personal                                                                                  | personal-docs → leaf `destination`                      | mass(leaf)                            |
| R6 | resolved node is `product:personal-docs`                                                                   | personal-docs → `~/Documents`                           | mass(product)                         |
| R7 | `flag_evidence >= 0.60` and resolved depth ≥ 2                                                             | archive (see fork F1)                                   | min(evidence, mass)                   |
| R8 | resolved depth ≥ 1                                                                                         | archive (see fork F5)                                   | mass(resolved)                        |
| R9 | otherwise                                                                                                  | keep                                                    | 0.0                                   |

`FILE_DISPOSITION_CONFIDENCE_FLOORS` still applies afterwards. Below its floor, the result is keep with reason "confidence below floor". The floors keep their current meaning, so existing floor tests still apply.

### 4.2 Legality invariant

`legal(node)`:

- live repo leaf with `local_path`: {move-to-repo, archive, trash-candidate, keep}, plus file-to-linear if its product has a Linear leaf.
- repo leaf with no `local_path`, or archived: {archive, trash-candidate, keep}, plus file-to-linear under the same condition.
- Linear leaf: {file-to-linear, archive, trash-candidate, keep}.
- personal leaf or `product:personal-docs`: {personal-docs, archive, trash-candidate, keep}.
- other product or area: {archive, trash-candidate, keep}, plus file-to-linear if the product has a Linear leaf.
- root: {archive, trash-candidate, keep}.

**Invariant:** `result.disposition ∈ legal(node at resolved_depth)`. `destination_hint` is derived only from that node, and trash is never chosen while R1 holds. `decide` asserts this. A violation raises `ValueError`, which leads to the existing fallback. It should be impossible by construction, and a property test proves that. `REASON_FILE_ILLEGAL_DISPOSITION` stays only for flat mode and is deleted at cutover.

## 5. Output contract (JSONL; the existing fields keep their meaning)

```json
{
  "path": "...",
  "project": "zachbornheimer/homelab",
  "kind": "spec",
  "disposition": "move-to-repo",
  "destination_hint": ".../homelab/docs",
  "confidence": 0.62,
  "reason": "selected",
  "taxonomy_version": "1.ab12cd34ef56",
  "node": "leaf:repo:zachbornheimer/homelab",
  "tree_path": [
    "area:homelab",
    "product:homelab",
    "leaf:repo:zachbornheimer/homelab"
  ],
  "resolved_depth": 3,
  "path_score": 0.71,
  "flags": {
    "backup": 0.05,
    "issue_list": 0.12,
    "evidence": 0.08,
    "private": 0.10,
    "regenerable": 0.04
  },
  "edges": [
    { "q": "area", "node": "area:homelab", "p": 0.81, "confidence": 0.74 },
    "..."
  ],
  "alternates": [{ "tree_path": ["..."], "path_score": 0.44 }],
  "rounds": 2
}
```

- `project` stays the leaf's `project_key` when `resolved_depth == 3`. Otherwise it is `"none"`, so existing consumers never see a non-leaf key. The coarser answer appears in `tree_path` and `node`.
- **Rename relative to the brief:** the new field is called `tree_path`, not `path`, because `path` is already the file path. `resolved_depth` is kept as named. `path_score` is the geometric mean; `confidence` stays disposition confidence.
- Flat mode (no `--taxonomy` flag) emits exactly today's 7 fields.

## 6. Labeled decisions file

Path: `~/.agents/skills/organize-files/data/decisions.jsonl`, append-only, one record per reviewed item:

```json
{
  "schema_version": 1,
  "decided_at": "2026-09-23T18:00:00Z",
  "reviewer": "zach",
  "file": {
    "path": "...",
    "size": 1234,
    "mtime": "...",
    "sha256": "<first 1MB>"
  },
  "taxonomy_version": "1.ab12cd34ef56",
  "classifier": "classify-file@<git sha>",
  "predicted": {
    "node": "...",
    "tree_path": ["..."],
    "resolved_depth": 2,
    "project": "none",
    "kind": "...",
    "disposition": "...",
    "confidence": 0.5,
    "flags": {},
    "edges": []
  },
  "label": {
    "node": "leaf:repo:zachbornheimer/homelab",
    "disposition": "move-to-repo",
    "kind": null,
    "note": "free text"
  },
  "verdict": "accepted | corrected | skipped"
}
```

- `label.node` may be a non-leaf (meaning "right area, no better answer"). `label.node = null` means "unknowable".
- Importer: `organize-files/scripts/import_decisions.py <review-export.json>`. It maps the review page export to records, dedupes on (file.sha256, decided_at), and never rewrites old lines.
- Tuner (report only, never edits constants): `organize-files/scripts/tune_report.py`. It outputs:
  - per-depth accuracy and coverage curves over candidate floors;
  - precision of each disposition rule;
  - the flag-floor error cost, weighting a false trash at 10× a false keep.

  The human edits `constants.py`.

## 7. Test plan (`test_classify_file.py` + new `test_taxonomy.py` + `organize-files/scripts/test_build_taxonomy.py`)

### Unit (fake answers, which now include `probabilities`; `choice_answer()` helper gains a `probabilities=` kwarg)

1. **Builder rules:**
   - P2 groups the rapidsign and zyins families.
   - P3 folds `bpp-ui` (archived) as an alias under a live bpp leaf, and no archived repo is ever a leaf with move-to-repo legal.
   - P4 attaches "Book Bestie Launch" to book-bestie and "DragonGate Portals" to portal-builder; "Hypeddit Exit" goes to ventures.
   - The version hash is stable and changes when one input byte changes.
   - Snapshot test on the real catalog: area count ≤ 10, every live repo is placed exactly once.
2. **Validator:** duplicate id, orphan parent, wrong depth, empty criteria, and unknown schema version each raise.
3. **Request shape:**
   - Round 1 contains `area`, `kind`, 5 flags, at most 2 `product@`, and no `disposition`.
   - A strong match gives round 1 = `kind` + flags only.
   - A large area offers 4 to 8 products plus `other`.
   - Every Choice has `other`.
4. **Beam and back-off (pure functions):**
   - The geometric mean excludes single-child edges.
   - Leaf mass 0.45/0.45 → resolved at the product.
   - Area `other` argmax → root.
   - Top-K trimming is deterministic.
   - A round-2 JudgmentError still resolves.
5. **Legality property test:** every node type × every kind × a flag grid {0.1, 0.5, 0.9}^5 gives `disposition ∈ legal(node)`, and no trash when private ≥ 0.5.

### RED cases from the named Desktop files (fixtures copy the real observation shape; answers are faked to what a correct model would return)

- **NAS-Rebuild-GOAL.md.**
  - Request test: the homelab area's criteria mention nas/gorillabank (from P1 enrichment), and `product:homelab` is offered even though flat IDF missed it.
  - Decide test: area p = 0.8 and product p = 0.7 give `tree_path[:2] == [area:homelab, product:homelab]` and never `personal:*`.
- **mail-import-backup/** (entries `["Import.mbox"]`): with flag_backup 0.95, flag_private 0.9 and regenerable 0.1 → not trash; reason includes the private guard; disposition is archive or keep.
- **Dorico Diagnostics.zip** (entries include `Activation Manager/.../config.dat`): with flag_evidence 0.8 and flag_private 0.7 → not trash.
- **flight-fix-list.md**: a strong or resolved `product:flight` that has `leaf:linear:Flight`, plus flag_issue_list 0.85 → file-to-linear, and never keep 0.00 with reason "illegal".
- **evo-canary-fable-report.md / zys-703-canary-evidence.md**: a strong match to evident-output plus flag_evidence 0.8 → R7 archive (a placeholder until fork F1 is decided), with `resolved_depth == 3`.
- **RapidSign-CIP-attorney-brief.md**: no strong match; area p 0.7 and product p 0.6 → resolves to at least `product:rapidsign` (today: project none, keep 0.00).
- **obsidian-live-proof-*.txt**: flag_backup 0.2 → not trash via R2, even though it is regenerable. Evidence → archive under `product:obsidian-backup`. This shows trash now requires "duplicate AND regenerable".
- **hof-25162-backup-preconvert.html**: backup 0.95, regenerable 0.9, private 0.05 → trash-candidate still works (guards against over-correction).
- **ZBbio-readable.md**: area personal-life, leaf `other` → `product:personal-docs`, personal-docs with destination `~/Documents` (the `personal:other` replacement).

### Live eval (opt-in, `TYPESAFE_LIVE=1`, not run in CI)

`organize-files/scripts/eval_desktop.py`:

- Runs the pipeline over `~/Desktop`.
- Compares against `organize-files/data/eval-desktop-labels.json`, about 15 named files with expected `tree_path` prefix and disposition class.
- Prints a comparison with the baseline in `/tmp/organize/desktop.jsonl`.
- Ship gate for cutover:
  - "illegal" count = 0;
  - "below floor at depth 0" drops from 28 to ≤ 12;
  - 0 trash on the private-guard files;
  - at least 12 of 15 labels correct at their labeled depth.

## 8. Migration slices (each shippable; flat mode keeps working until S8)

| slice | content                                                                                                                                                                                                                                                 | est.  |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| S1    | `answers.choice_distribution`; `taxonomy.py` loader and validator; `choice_answer(probabilities=)` test helper. No behavior change.                                                                                                                     | 1.5 h |
| S2    | Flags + computed disposition **in flat mode**: replace the `disposition` Choice with the 5 flag Nouls and rules R0–R9 (project-kind → legal table). RED: mail-import-backup, Dorico, hof backup, flight-fix-list. Delivers the trash fixes immediately. | 3 h   |
| S3    | `build_taxonomy.py` (P0–P7), overrides, personal-areas and linear-projects inputs; snapshot and rule tests; generates `taxonomy.json` v1.                                                                                                               | 3.5 h |
| S4    | Beam: round planner, scorer, prefix-mass back-off, `--taxonomy` flag in `typesafe.py` `classify-file`, extended output fields. Unit tests for beam and legality.                                                                                        | 4 h   |
| S5    | Shortlist and strong-match rewired onto taxonomy leaves (area prior, large-area option narrowing, archived alias → successor). RED: NAS-Rebuild-GOAL, RapidSign brief.                                                                                  | 2 h   |
| S6    | Live eval harness + labels file; run on Desktop; tune floors once by hand.                                                                                                                                                                              | 2 h   |
| S7    | `decisions.jsonl` importer + `tune_report.py`.                                                                                                                                                                                                          | 2.5 h |
| S8    | Cutover: organize-files calls with `--taxonomy` by default; delete flat-mode `personal:*` bucket Nouls, `DISPOSITION_CRITERIA` Choice and `REASON_FILE_ILLEGAL_DISPOSITION`; update SKILL.md and LAYOUT.md.                                             | 1.5 h |

Total ≈ 20 h. Dependencies:

- S1 comes first.
- S2 needs only S1, so it can ship before any taxonomy work.
- S3 is independent of S2.
- S4 needs S1 and S3.
- S5 needs S4.
- S6 needs S5.
- S7 can start after S4, since it needs the output fields.
- S8 is last.

## 9. Decisions I made (no input needed)

- Taxonomy format: a flat node list with parent pointers, content-hash versioning and stable ids. The builder lives in organize-files; the loader lives in typesafe-ai.
- Three levels (area → product → leaf); single-leaf products imply their edge.
- Beam width 3; geometric-mean ranking; prefix-mass back-off. Initial floors 0.55 / 0.40 / 0.30, to be retuned.
- Speculative `product@` for the top-2 prior areas in round 1; at most 3 rounds.
- Disposition is computed rather than asked. A 5th flag, `flag_regenerable`, is added, and trash requires duplicate AND regenerable AND not private.
- `personal:other` becomes the `other` escape → `product:personal-docs`.
- `project` keeps its leaf-only meaning; the new fields are additive, with `tree_path` rather than `path`.
- `decisions.jsonl` is append-only; the tuner reports and never edits constants.

## 10. Forks only Zach can decide

- **F1 Evidence/log files tied to a repo** (zq-real-failures.md, evo-canary-*, homelab-docker-forensics-*.txt, rapidsign-walk-evidence). Options:
  - (a) archive to `~/Documents/Archive/<product>`;
  - (b) move-to-repo into `docs/evidence/`;
  - (c) trash when regenerable.

  The design defaults to (a).
- **F2 Issue lists for products with no Linear project** (everest-problems.md, ev-ui-issues*.md, builder-ui-problems — Everest/eapp in SAH). Options: move-to-repo, propose a new Linear project, or keep for review. As designed, R3 fails and R4 applies, so they land as move-to-repo.
- **F3 Personal leaves:** which `~/Documents` subdirs are real destinations. Proposed: Finance, Family, Health, Legal, Career, Academics, Journals, Patents, plus Music → `~/Documents/Music` or `~/Music`. Also: where do the ZBbio biography artifacts go (Career? a dedicated leaf?), and do legal briefs like the RapidSign CIP attorney brief go to the product or to `~/Documents/Legal`? That is, should a cross-cutting "personal/legal overrides project" rule exist?
- **F4 Area membership rules can't infer:**
  - Is homelab one product (homelab + nas-recovery + carve-reconcile + librarian) or separate products under `area:homelab`?
  - Do hevc-archive, volatile-downloads and home.zachandaj.com belong in homelab?
  - Which area do the unattached Linear projects join: Hypeddit Exit, PPG ×4, Site Status SaaS, ZachStacks Launch, AI Harness Code Efficiency?
  - Should ninjaquoter and isa-sdk fold into insurance-software?
- **F5 Back-off destination:** when resolved only to a product or area, may the mover archive the file to a product folder automatically, or must a non-leaf result always be keep/review?
- **F6 Automation gate:** is trash-candidate ever executed automatically at some confidence, or always queued for human review? The same question applies to move-to-repo into a git working tree.

### Critical Files for Implementation

- /Users/zbornheimer/.agents/skills/typesafe-ai/scripts/classify_file.py
- /Users/zbornheimer/.agents/skills/typesafe-ai/scripts/constants.py
- /Users/zbornheimer/.agents/skills/typesafe-ai/scripts/answers.py
- /Users/zbornheimer/.agents/skills/typesafe-ai/scripts/typesafe.py (classify_files loop, `--taxonomy` flag)
- /Users/zbornheimer/.agents/skills/typesafe-ai/scripts/test_classify_file.py
- /Users/zbornheimer/.agents/skills/organize-files/data/repo-catalog.json (the builder's input; new builder at /Users/zbornheimer/.agents/skills/organize-files/scripts/build_taxonomy.py)

## 11. Decisions from Zach (2026-09-23)

- F1 evidence: uploaded to the Linear issue it proves (`attach-evidence`, needs_ticket; redacted copy if private). No NAS evidence store for now.
- F2 issue lists without a Linear project: `keep` + needs_triage; the skill's agent step works out the owning project and asks Zach.
- F4 homelab: one product (homelab + nas-recovery + carve-reconcile + librarian).

### Decisions from Zach (2026-09-24): a 6th flag, `flag_loss_record`

Live case: classify-file suggested trash for `navidrome_missing_files.csv` and
`lidarr-csv-coverage.jsonl` -- inventories from the NAS data-loss recovery
(`nas-recovery`/`carve-reconcile`, under `product:homelab`). "The missing files
should be a flag that it's important" (Zach). An inventory of what is missing is
the only record of the loss; it cannot be regenerated by re-running a tool.

- `flag_loss_record` is the 6th disposition flag Noul, batched with the other 5 in
  round 1 in both flat mode and tree mode (both modes share
  `classify_file.FLAG_QUESTIONS`/`FILE_FLAGS`). Question: does this file record
  data that was lost, missing, deleted, or unrecovered -- an inventory of missing
  files, a coverage/gap report, or a recovery manifest -- such that it may be the
  only record of what is gone?
- Rule: `flag_loss_record >= FILE_FLAG_FLOORS["loss_record"]` (0.50, the same bar
  as `private_guard`) blocks trash, exactly like the private guard -- R1 in both
  `classify_file._resolve_disposition` and `taxonomy_classify._decide`. It does not
  block any other disposition: once trash is blocked, the file still routes to its
  resolved product as `move-to-repo`, or `archive` when no repo leaf applies.
- `FileResult.important` (new field, both modes) is `True` whenever `flag_private`
  or `flag_loss_record` clears its floor, independent of which disposition the rule
  chain lands on -- a signal to the human/agent reviewer that the file needs eyes-on.
- A deterministic prefilter hint (`loss_record_filename_hint`, exposed to the model
  as `state.loss_record_hint`) raises attention on the question when the filename
  contains a token like "missing"/"lost"/"unrecovered"/"coverage"
  (`FILE_LOSS_RECORD_FILENAME_TOKENS`). The hint is context only -- the model's own
  Noul answer, gated by the floor above, is what decides the disposition.
- Guarded against over-correction: a genuinely regenerable, non-private,
  non-loss-record backup (`hof-25162-backup-preconvert.html`) still reaches
  `trash-candidate`.
- F6 automation: always review for now; decide later from decisions.jsonl accuracy.
