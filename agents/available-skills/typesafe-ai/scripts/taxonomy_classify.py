"""S4/S5: beam-search classification over `taxonomy.json` (design contract
sections 2-5, /tmp/organize/taxonomy-design.md). Three layers, each testable
on its own (design section 7):

- deterministic leaf scoring + strong match (S5, mirrors `classify_file`'s
  catalog scoring but against taxonomy leaf tokens);
- a round planner that builds at most `FILE_TAXONOMY_MAX_ROUNDS` batched
  Choice/Noul requests (S4 section 2.4);
- pure beam-scoring and prefix-mass back-off functions (S4 section 3) that
  never touch the network, so they are unit-testable without a fake `ask`.

`classify` is the only function that calls `ask`; everything it calls is a
pure function of the taxonomy and the answers already received.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import answers as answers_module
import classify_file
from constants import (
    FILE_DEST_LIFE,
    FILE_DISPOSITION_ARCHIVE,
    FILE_DISPOSITION_ATTACH_EVIDENCE,
    FILE_DISPOSITION_CONFIDENCE_FLOORS,
    FILE_DISPOSITION_FILE_TO_LINEAR,
    FILE_DISPOSITION_KEEP,
    FILE_DISPOSITION_MOVE_TO_REPO,
    FILE_DISPOSITION_PERSONAL_DOCS,
    FILE_DISPOSITION_TRASH_CANDIDATE,
    FILE_DISPOSITIONS,
    FILE_FLAG_BACKUP,
    FILE_FLAG_EVIDENCE,
    FILE_FLAG_FLOORS,
    FILE_FLAG_ISSUE_LIST,
    FILE_FLAG_LOSS_RECORD,
    FILE_FLAG_PRIVATE,
    FILE_FLAG_REGENERABLE,
    FILE_FLAGS,
    FILE_KINDS,
    FILE_PROJECT_CANDIDATE_LIMIT,
    FILE_PROJECT_NONE,
    FILE_SCORING_EXCERPT_CHARS,
    FILE_STRONG_MATCH_MAX_DOCUMENT_FREQUENCY,
    FILE_TAXONOMY_BEAM_WIDTH,
    FILE_TAXONOMY_DEPTH_FLOORS,
    FILE_TAXONOMY_LARGE_AREA_MIN_OPTIONS,
    FILE_TAXONOMY_MAX_ROUNDS,
    FILE_TAXONOMY_OTHER,
    FILE_TAXONOMY_PROB_EPSILON,
    FILE_TAXONOMY_SPECULATIVE_AREAS,
    LOCAL_PICK_MIN_TOKEN_LENGTH,
    LOCAL_PICK_STOPWORDS,
    REASON_BELOW_CONFIDENCE,
    REASON_FILE_BACKOFF,
    REASON_FILE_EVIDENCE_NEEDS_TRIAGE,
    REASON_FILE_ISSUE_NEEDS_TRIAGE,
    REASON_FILE_LOSS_RECORD_GUARD,
    REASON_FILE_PRIVATE_GUARD,
    REASON_FILE_STRONG_MATCH,
    REASON_SELECTED,
)
from taxonomy import (
    TAXONOMY_NODE_TYPE_AREA,
    TAXONOMY_NODE_TYPE_LEAF,
    TAXONOMY_NODE_TYPE_PRODUCT,
    Taxonomy,
    TaxonomyNode,
)

Ask = Callable[[dict[str, Any]], dict[str, Any]]
PERSONAL_DOCS_PRODUCT_ID = "product:personal-docs"
_AREA_QUESTION = "area"
_PRODUCT_QUESTION_PREFIX = "product@"
_LEAF_QUESTION_PREFIX = "leaf@"

# --- tokenizing (mirrors classify_file's local-match tokenizer; duplicated in
# miniature rather than reaching into classify_file's private helpers) ------

_WORD_RE = re.compile(r"[a-z0-9]+")


def _words(text: str) -> set[str]:
    tokens: set[str] = set()
    for raw in _WORD_RE.findall(text.lower()):
        if (
            len(raw) < LOCAL_PICK_MIN_TOKEN_LENGTH
            or raw in LOCAL_PICK_STOPWORDS
            or raw in classify_file.FILE_GENERIC_SCORING_STOPWORDS
        ):
            continue
        tokens.add(raw)
    return tokens


def _filename_raw_segments(filename: str) -> set[str]:
    stem = Path(filename).stem.lower()
    return {
        segment
        for segment in re.split(r"[-_ .]+", stem)
        if segment
        and segment not in LOCAL_PICK_STOPWORDS
        and segment not in classify_file.FILE_GENERIC_SCORING_STOPWORDS
    }


def _observation_tokens(observation: dict[str, Any]) -> set[str]:
    stem = Path(observation["filename"]).stem
    tokens = _words(stem.replace("-", " ").replace("_", " "))
    tokens |= _filename_raw_segments(observation["filename"])
    tokens |= _words(observation.get("excerpt", "")[:FILE_SCORING_EXCERPT_CHARS])
    return tokens


def _observation_state(observation: dict[str, Any]) -> dict[str, Any]:
    return {
        "filename": observation["filename"],
        "extension": observation["extension"],
        "size": observation["size"],
        "mtime": observation["mtime"],
        "is_dir": observation["is_dir"],
        "excerpt": observation["excerpt"],
        "entries": observation["entries"],
        "source_dir": Path(observation["path"]).parent.name,
        "loss_record_hint": classify_file.loss_record_filename_hint(observation["filename"]),
    }


# --- S5: deterministic leaf scoring, area prior, strong match --------------


def _leaf_token_document_frequency(taxonomy: Taxonomy) -> dict[str, int]:
    document_frequency: dict[str, int] = {}
    for node in taxonomy.nodes.values():
        if node.type != TAXONOMY_NODE_TYPE_LEAF:
            continue
        for token in set(node.tokens):
            document_frequency[token] = document_frequency.get(token, 0) + 1
    return document_frequency


def leaf_matches(observation: dict[str, Any], taxonomy: Taxonomy) -> list[tuple[str, float]]:
    """Every taxonomy leaf scored against the file's tokens (IDF-weighted overlap,
    same shape as `classify_file._catalog_matches`), highest first."""
    document_frequency = _leaf_token_document_frequency(taxonomy)
    obs_tokens = _observation_tokens(observation)
    scored: list[tuple[str, float]] = []
    for node in taxonomy.nodes.values():
        if node.type != TAXONOMY_NODE_TYPE_LEAF:
            continue
        overlap = obs_tokens & set(node.tokens)
        if not overlap:
            continue
        score = sum(1.0 / document_frequency.get(token, 1) for token in overlap)
        scored.append((node.id, score))
    scored.sort(key=lambda item: -item[1])
    return scored


def _area_of(taxonomy: Taxonomy, node: TaxonomyNode) -> str | None:
    current = node
    while current.parent is not None:
        current = taxonomy.node(current.parent)
    return current.id if current.type == TAXONOMY_NODE_TYPE_AREA else None


def area_prior(taxonomy: Taxonomy, scored_leaves: list[tuple[str, float]]) -> dict[str, float]:
    """Area prior (design section 2.3) = the sum of shortlisted leaf scores under
    that area — decides which areas get a speculative `product@` question."""
    prior: dict[str, float] = {}
    for leaf_id, score in scored_leaves[:FILE_PROJECT_CANDIDATE_LIMIT]:
        area_id = _area_of(taxonomy, taxonomy.node(leaf_id))
        if area_id is not None:
            prior[area_id] = prior.get(area_id, 0.0) + score
    return prior


def strong_taxonomy_match(observation: dict[str, Any], taxonomy: Taxonomy) -> str | None:
    """A repo leaf whose basename is both an exact filename segment and rare enough
    across the taxonomy to be unambiguous (mirrors
    `classify_file.strong_project_match`, scored over taxonomy leaves instead of the
    flat catalog). None means the caller must ask instead of guessing."""
    document_frequency = _leaf_token_document_frequency(taxonomy)
    raw_segments = _filename_raw_segments(observation["filename"])
    best: tuple[str, float] | None = None
    for node in taxonomy.nodes.values():
        if node.type != TAXONOMY_NODE_TYPE_LEAF or node.leaf_kind != "repo" or not node.project_key:
            continue
        basename = node.project_key.rsplit("/", 1)[-1].lower()
        if basename not in raw_segments:
            continue
        if document_frequency.get(basename, 99) > FILE_STRONG_MATCH_MAX_DOCUMENT_FREQUENCY:
            continue
        score = 1.0 / document_frequency.get(basename, 1)
        if best is None or score > best[1]:
            best = (node.id, score)
        elif score == best[1] and node.id != best[0]:
            return None  # ambiguous tie between two distinct leaves
    return best[0] if best else None


def _shortlisted_products(
    taxonomy: Taxonomy, area_id: str, scored_leaves: list[tuple[str, float]]
) -> list[str]:
    """Every product in a small area; for a `large` area, the IDF-shortlisted
    products (padded to `FILE_TAXONOMY_LARGE_AREA_MIN_OPTIONS` by leaf count when the
    shortlist alone is thin) — the shortlist narrows what is offered, never what is
    decided (design section 2.3)."""
    area = taxonomy.node(area_id)
    products = taxonomy.children_of(area_id)
    if not area.large:
        return [product.id for product in products]
    scored: dict[str, float] = {}
    for leaf_id, score in scored_leaves:
        leaf = taxonomy.node(leaf_id)
        if leaf.parent and taxonomy.node(leaf.parent).parent == area_id:
            scored[leaf.parent] = scored.get(leaf.parent, 0.0) + score
    ranked = sorted(scored, key=lambda product_id: -scored[product_id])[
        :FILE_PROJECT_CANDIDATE_LIMIT
    ]
    if len(ranked) < FILE_TAXONOMY_LARGE_AREA_MIN_OPTIONS:
        by_leaf_count = sorted(products, key=lambda product: -len(taxonomy.children_of(product.id)))
        for product in by_leaf_count:
            if len(ranked) >= FILE_TAXONOMY_LARGE_AREA_MIN_OPTIONS:
                break
            if product.id not in ranked:
                ranked.append(product.id)
    return ranked


# --- request shaping: slugged Choice options (design section 1.2) ----------


def _slug_choice(
    instructions: str, options: list[tuple[str, str]], other_text: str
) -> tuple[dict[str, Any], dict[str, str]]:
    """Builds one Choice question with generated `o0..oN` + `other` option keys
    (design section 1.2 -- taxonomy ids/Linear names can carry characters a Choice
    option key should not), and the slug->node_id map needed to read the answer
    back. `options` is `[(node_id, criteria), ...]`."""
    criteria: dict[str, str] = {}
    slug_to_node: dict[str, str] = {}
    for index, (node_id, criteria_text) in enumerate(options):
        slug = f"o{index}"
        criteria[slug] = criteria_text
        slug_to_node[slug] = node_id
    criteria[FILE_TAXONOMY_OTHER] = other_text
    question = {"type": "choice", "instructions": instructions, "criteria": criteria}
    return question, slug_to_node


def _area_question(taxonomy: Taxonomy) -> tuple[dict[str, Any], dict[str, str]]:
    options = [(area.id, area.criteria) for area in sorted(taxonomy.areas(), key=lambda a: a.id)]
    return _slug_choice(
        "Which area does `filename`/`excerpt`/`entries` belong to?",
        options,
        "None of these areas fits; unrelated or unknowable.",
    )


def _product_question(
    taxonomy: Taxonomy, area_id: str, scored_leaves: list[tuple[str, float]]
) -> tuple[dict[str, Any], dict[str, str]]:
    product_ids = sorted(_shortlisted_products(taxonomy, area_id, scored_leaves))
    options = [(pid, taxonomy.node(pid).criteria) for pid in product_ids]
    return _slug_choice(
        "Which product within this area does the file belong to?",
        options,
        "None of these products fits.",
    )


def _leaf_question(taxonomy: Taxonomy, product_id: str) -> tuple[dict[str, Any], dict[str, str]]:
    leaves = sorted(taxonomy.children_of(product_id), key=lambda leaf: leaf.id)
    options = [(leaf.id, leaf.criteria) for leaf in leaves]
    return _slug_choice(
        "Which specific project/destination does the file belong to?",
        options,
        "None of these specific items fits; the product-level answer is best.",
    )


# --- edges, scoring, back-off (pure; design section 3) ----------------------


@dataclass(frozen=True, slots=True)
class Edge:
    question_id: str
    node_id: str
    probability: float
    confidence: float
    counted: bool = True


def geometric_mean_score(edges: list[Edge]) -> float:
    """Path score = geometric mean of the *counted* edge probabilities (single-child
    edges, e.g. a product with exactly one leaf, are implied at p=1 and excluded)."""
    counted = [edge.probability for edge in edges if edge.counted]
    if not counted:
        return 1.0
    log_mean = sum(math.log(max(p, FILE_TAXONOMY_PROB_EPSILON)) for p in counted) / len(counted)
    return math.exp(log_mean)


def _prefix_mass_by_depth(edges: list[Edge]) -> dict[int, float]:
    """mass(depth) = the plain product of edge probabilities from the root down to
    that depth (every edge counts here, including implied single-child ones, since
    back-off cares about how much probability mass actually reaches that node — not
    how informative the edge was)."""
    mass_by_depth: dict[int, float] = {0: 1.0}
    running = 1.0
    for depth, edge in enumerate(edges, start=1):
        running *= edge.probability
        mass_by_depth[depth] = running
    return mass_by_depth


def resolve_depth(edges: list[Edge], floors: dict[int, float] | None = None) -> tuple[int, float]:
    """Back off from the deepest node up the path to the deepest one whose prefix
    mass still clears its floor (design section 3); root (depth 0, mass 1.0) always
    qualifies, so this never fails to return."""
    floors = floors if floors is not None else FILE_TAXONOMY_DEPTH_FLOORS
    mass_by_depth = _prefix_mass_by_depth(edges)
    for depth in range(len(edges), 0, -1):
        if mass_by_depth[depth] >= floors.get(depth, 1.0):
            return depth, mass_by_depth[depth]
    return 0, mass_by_depth[0]


def top_k_by_score(
    candidates: list[tuple[list[Edge], float]], k: int = FILE_TAXONOMY_BEAM_WIDTH
) -> list[tuple[list[Edge], float]]:
    """Deterministic top-K trim: highest score first, ties broken by the deepest
    node's id so repeated runs on the same answers always pick the same beam."""
    return sorted(
        candidates,
        key=lambda item: (-item[1], item[0][-1].node_id if item[0] else ""),
    )[:k]


# --- round planning + orchestration -----------------------------------------


@dataclass
class _RoundState:
    observation: dict[str, Any]
    taxonomy: Taxonomy
    scored_leaves: list[tuple[str, float]] = field(default_factory=list)
    strong_match: str | None = None
    area_edge: Edge | None = None
    area_distribution: dict[str, float] = field(default_factory=dict)  # every area's P(area)
    product_edges: dict[str, Edge] = field(default_factory=dict)  # area_id -> edge
    leaf_edges: dict[str, Edge] = field(default_factory=dict)  # product_id -> edge
    asked_product_areas: set[str] = field(default_factory=set)
    asked_leaf_products: set[str] = field(default_factory=set)
    rounds_used: int = 0
    partial_reason: str | None = None


def _build_round_1(state: _RoundState) -> tuple[dict[str, Any], dict[str, dict[str, str]]]:
    """Round 1 (design section 2.4): `area`, `kind`, the 5 flag Nouls, and a
    speculative `product@<area>` Choice for the top `FILE_TAXONOMY_SPECULATIVE_AREAS`
    prior areas. A strong match skips `area`/`product@` entirely — the path is
    already fully determined."""
    questions: dict[str, Any] = {}
    slug_maps: dict[str, dict[str, str]] = {}
    if state.strong_match is None:
        area_question, area_slugs = _area_question(state.taxonomy)
        questions[_AREA_QUESTION] = area_question
        slug_maps[_AREA_QUESTION] = area_slugs
        prior = area_prior(state.taxonomy, state.scored_leaves)
        top_prior_areas = sorted(prior, key=lambda a: -prior[a])[:FILE_TAXONOMY_SPECULATIVE_AREAS]
        for area_id in top_prior_areas:
            question_id = f"{_PRODUCT_QUESTION_PREFIX}{area_id}"
            product_question, product_slugs = _product_question(
                state.taxonomy, area_id, state.scored_leaves
            )
            questions[question_id] = product_question
            slug_maps[question_id] = product_slugs
            state.asked_product_areas.add(area_id)
    questions[classify_file.QUESTION_KIND] = {
        "type": "choice",
        "instructions": "What kind of file is this?",
        "criteria": dict(classify_file.KIND_CRITERIA),
    }
    for flag_id, instructions in classify_file.FLAG_QUESTIONS.items():
        questions[flag_id] = {"type": "noul", "instructions": instructions}
    return questions, slug_maps


def _read_round_1(
    state: _RoundState, answers_by_id: dict[str, Any], slug_maps: dict[str, dict[str, str]]
) -> None:
    if state.strong_match is not None:
        return
    area_slugs = slug_maps[_AREA_QUESTION]
    area_slug, area_probabilities = _read_choice(answers_by_id, _AREA_QUESTION)
    state.area_distribution = {
        area_slugs[slug]: p for slug, p in area_probabilities.items() if slug in area_slugs
    }
    node_id = area_slugs.get(area_slug)
    if node_id is not None:
        _, area_confidence = answers_module.choice(answers_by_id, _AREA_QUESTION)
        state.area_edge = Edge(
            _AREA_QUESTION, node_id, area_probabilities.get(area_slug, 0.0), area_confidence
        )
    for area_id in list(state.asked_product_areas):
        question_id = f"{_PRODUCT_QUESTION_PREFIX}{area_id}"
        if question_id not in answers_by_id:
            continue
        _record_product_answer(state, area_id, question_id, answers_by_id, slug_maps[question_id])


def _read_choice(answers_by_id: dict[str, Any], question_id: str) -> tuple[str, dict[str, float]]:
    choice, _confidence = answers_module.choice(answers_by_id, question_id)
    probabilities = answers_module.choice_distribution(answers_by_id, question_id)
    return choice, probabilities


def _record_product_answer(
    state: _RoundState,
    area_id: str,
    question_id: str,
    answers_by_id: dict[str, Any],
    slug_to_node: dict[str, str],
) -> None:
    slug, probabilities = _read_choice(answers_by_id, question_id)
    node_id = slug_to_node.get(slug)
    if node_id is None:
        return
    state.product_edges[area_id] = Edge(question_id, node_id, probabilities.get(slug, 0.0), 0.0)


def _record_leaf_answer(
    state: _RoundState,
    product_id: str,
    question_id: str,
    answers_by_id: dict[str, Any],
    slug_to_node: dict[str, str],
) -> None:
    slug, probabilities = _read_choice(answers_by_id, question_id)
    node_id = slug_to_node.get(slug)
    if node_id is None:
        return
    state.leaf_edges[product_id] = Edge(question_id, node_id, probabilities.get(slug, 0.0), 0.0)


def _beam_product_ids(state: _RoundState) -> list[str]:
    """The top `FILE_TAXONOMY_BEAM_WIDTH` product partials seen so far, ranked by
    area-prior * product-probability (the beam-trimming step, design section 3)."""
    scored: list[tuple[str, float]] = []
    for area_id, edge in state.product_edges.items():
        area_probability = (
            state.area_edge.probability
            if (state.area_edge and state.area_edge.node_id == area_id)
            else 1.0
        )
        scored.append((edge.node_id, area_probability * edge.probability))
    scored.sort(key=lambda item: -item[1])
    return [product_id for product_id, _score in scored[:FILE_TAXONOMY_BEAM_WIDTH]]


def _build_round_2(state: _RoundState) -> tuple[dict[str, Any], dict[str, dict[str, str]]] | None:
    """Round 2 (design section 2.4): `product@` for frontier areas not yet asked,
    plus `leaf@` for every multi-leaf product already among the top-3 depth-2
    partials from round 1's speculative answers."""
    if state.strong_match is not None or state.area_edge is None:
        return None
    questions: dict[str, Any] = {}
    slug_maps: dict[str, dict[str, str]] = {}
    # The frontier (design section 2.4) is the top `FILE_TAXONOMY_BEAM_WIDTH` areas
    # by P(area) excluding `other`, plus whatever area already got a speculative
    # product@ answer in round 1 (so a round-1 speculative pick outside the top-3 by
    # probability, but already answered, is still asked its remaining questions).
    ranked_areas = sorted(state.area_distribution, key=lambda a: -state.area_distribution[a])
    frontier_areas = set(ranked_areas[:FILE_TAXONOMY_BEAM_WIDTH]) | set(state.product_edges)
    for area_id in sorted(frontier_areas):
        if area_id in state.asked_product_areas:
            continue
        question_id = f"{_PRODUCT_QUESTION_PREFIX}{area_id}"
        product_question, product_slugs = _product_question(
            state.taxonomy, area_id, state.scored_leaves
        )
        questions[question_id] = product_question
        slug_maps[question_id] = product_slugs
        state.asked_product_areas.add(area_id)
    for product_id in _beam_product_ids(state):
        if product_id in state.asked_leaf_products:
            continue
        if len(state.taxonomy.children_of(product_id)) <= 1:
            continue
        question_id = f"{_LEAF_QUESTION_PREFIX}{product_id}"
        leaf_question, leaf_slugs = _leaf_question(state.taxonomy, product_id)
        questions[question_id] = leaf_question
        slug_maps[question_id] = leaf_slugs
        state.asked_leaf_products.add(product_id)
    return (questions, slug_maps) if questions else None


def _read_round_2_or_3(
    state: _RoundState, answers_by_id: dict[str, Any], slug_maps: dict[str, dict[str, str]]
) -> None:
    for area_id in list(state.asked_product_areas):
        question_id = f"{_PRODUCT_QUESTION_PREFIX}{area_id}"
        if question_id in slug_maps and question_id in answers_by_id:
            _record_product_answer(
                state, area_id, question_id, answers_by_id, slug_maps[question_id]
            )
    for product_id in list(state.asked_leaf_products):
        question_id = f"{_LEAF_QUESTION_PREFIX}{product_id}"
        if question_id in slug_maps and question_id in answers_by_id:
            _record_leaf_answer(
                state, product_id, question_id, answers_by_id, slug_maps[question_id]
            )


def _build_round_3(state: _RoundState) -> tuple[dict[str, Any], dict[str, dict[str, str]]] | None:
    """Round 3: only `leaf@` for surviving depth-2 partials that still lack one."""
    if state.strong_match is not None:
        return None
    questions: dict[str, Any] = {}
    slug_maps: dict[str, dict[str, str]] = {}
    for product_id in _beam_product_ids(state):
        if product_id in state.asked_leaf_products:
            continue
        if len(state.taxonomy.children_of(product_id)) <= 1:
            continue
        question_id = f"{_LEAF_QUESTION_PREFIX}{product_id}"
        leaf_question, leaf_slugs = _leaf_question(state.taxonomy, product_id)
        questions[question_id] = leaf_question
        slug_maps[question_id] = leaf_slugs
        state.asked_leaf_products.add(product_id)
    return (questions, slug_maps) if questions else None


def _best_path_edges(state: _RoundState) -> list[Edge]:
    """The single best-scoring path assembled from the edges collected across all
    rounds: area -> (its product, if answered) -> (that product's leaf, or the
    implied single-leaf edge, if answered)."""
    if state.strong_match is not None:
        node = state.taxonomy.node(state.strong_match)
        product = state.taxonomy.node(node.parent) if node.parent else None
        area_id = _area_of(state.taxonomy, node)
        edges = []
        if area_id is not None:
            edges.append(Edge(_AREA_QUESTION, area_id, 1.0, 1.0, counted=False))
        if product is not None:
            edges.append(Edge("", product.id, 1.0, 1.0, counted=False))
        edges.append(Edge("", node.id, 1.0, 1.0, counted=False))
        return edges

    edges: list[Edge] = []
    if state.area_edge is None:
        return edges
    edges.append(state.area_edge)
    product_edge = state.product_edges.get(state.area_edge.node_id)
    if product_edge is None:
        return edges
    edges.append(product_edge)
    leaves = state.taxonomy.children_of(product_edge.node_id)
    if len(leaves) == 1:
        edges.append(Edge("", leaves[0].id, 1.0, 1.0, counted=False))
        return edges
    leaf_edge = state.leaf_edges.get(product_edge.node_id)
    if leaf_edge is not None:
        edges.append(leaf_edge)
    return edges


def _alternate_paths(state: _RoundState) -> list[tuple[list[Edge], float]]:
    """Every other product partial the beam kept, for the `alternates` output
    field — each scored the same way as the winning path (design section 5)."""
    alternates: list[tuple[list[Edge], float]] = []
    if state.area_edge is None:
        return alternates
    winning_product = state.product_edges.get(state.area_edge.node_id)
    for area_id, product_edge in state.product_edges.items():
        if area_id == state.area_edge.node_id and product_edge is winning_product:
            continue
        area_probability = (
            1.0 if area_id == state.area_edge.node_id else state.area_edge.probability
        )
        path = [Edge(_AREA_QUESTION, area_id, area_probability, 0.0, counted=False), product_edge]
        leaf_edge = state.leaf_edges.get(product_edge.node_id)
        if leaf_edge is not None:
            path.append(leaf_edge)
        alternates.append((path, geometric_mean_score(path)))
    return alternates


@dataclass(frozen=True, slots=True)
class TaxonomyResolution:
    node_id: str | None
    tree_path: tuple[str, ...]
    resolved_depth: int
    path_score: float
    edges: tuple[Edge, ...]
    alternates: tuple[tuple[tuple[str, ...], float], ...]
    reason: str


def resolve_path(state: _RoundState) -> TaxonomyResolution:
    """Pure: turns the edges collected across rounds into a resolved node via
    back-off (design section 3). Never calls `ask`."""
    edges = _best_path_edges(state)
    if not edges:
        return TaxonomyResolution(None, (), 0, 1.0, (), (), REASON_SELECTED)
    if state.strong_match is not None:
        return TaxonomyResolution(
            state.strong_match,
            tuple(edge.node_id for edge in edges),
            len(edges),
            1.0,
            tuple(edges),
            (),
            REASON_FILE_STRONG_MATCH,
        )
    depth, _mass = resolve_depth(edges)
    tree_path = tuple(edge.node_id for edge in edges[:depth])
    resolved_node = tree_path[-1] if tree_path else None
    reason = REASON_SELECTED if depth == len(edges) else REASON_FILE_BACKOFF
    if state.partial_reason:
        reason = f"partial: {state.partial_reason}"
    alternates = tuple(
        (tuple(edge.node_id for edge in path), score) for path, score in _alternate_paths(state)
    )
    return TaxonomyResolution(
        resolved_node,
        tree_path,
        depth,
        geometric_mean_score(list(edges)),
        tuple(edges),
        alternates,
        reason,
    )


@dataclass(frozen=True, slots=True)
class TaxonomyFileResult:
    """The taxonomy-mode output contract (design section 5): the flat 7 fields plus
    `tree_path`/`resolved_depth`/`path_score`/`node`/`edges`/`alternates`/`rounds`.
    `project` keeps its leaf-only meaning — a coarser resolution reports "none" here
    and carries the real answer in `tree_path`/`node`."""

    file: classify_file.FileResult
    node: str | None
    tree_path: tuple[str, ...]
    resolved_depth: int
    path_score: float
    edges: tuple[dict[str, Any], ...]
    alternates: tuple[dict[str, Any], ...]
    rounds: int
    taxonomy_version: str

    def as_json(self) -> dict[str, Any]:
        payload = self.file.as_json()
        payload.update(
            {
                "taxonomy_version": self.taxonomy_version,
                "node": self.node,
                "tree_path": list(self.tree_path),
                "resolved_depth": self.resolved_depth,
                "path_score": self.path_score,
                "edges": list(self.edges),
                "alternates": list(self.alternates),
                "rounds": self.rounds,
            }
        )
        return payload


def classify(observation: dict[str, Any], taxonomy: Taxonomy, ask: Ask) -> TaxonomyFileResult:
    """Orchestrates up to `FILE_TAXONOMY_MAX_ROUNDS` batched TypeSafe calls, then
    resolves the beam and computes the disposition (design sections 2-5). `ask` is
    the only network-touching dependency (the facade a caller injects)."""
    state = _RoundState(observation=observation, taxonomy=taxonomy)
    state.scored_leaves = leaf_matches(observation, taxonomy)
    state.strong_match = strong_taxonomy_match(observation, taxonomy)

    questions_1, slugs_1 = _build_round_1(state)
    answers_1 = ask({"state": _observation_state(observation), "questions": questions_1})
    state.rounds_used = 1
    kind, _kind_confidence = answers_module.choice(answers_1, classify_file.QUESTION_KIND)
    flags = {flag_id: answers_module.noul(answers_1, flag_id) for flag_id in FILE_FLAGS}
    # Round-1 malformed answers propagate to `classify_file.fallback` (design section
    # 2.4: "on an error in R1, the existing fallback") -- only round >= 2 failures are
    # partial-resolved from what round 1 already secured.
    _read_round_1(state, answers_1, slugs_1)

    for round_number, build_round in ((2, _build_round_2), (3, _build_round_3)):
        if round_number > FILE_TAXONOMY_MAX_ROUNDS or state.partial_reason:
            break
        planned = build_round(state)
        if planned is None:
            break
        questions, slug_maps = planned
        try:
            round_answers = ask({"state": _observation_state(observation), "questions": questions})
            state.rounds_used = round_number
            _read_round_2_or_3(state, round_answers, slug_maps)
        except (ValueError, KeyError) as exc:
            state.partial_reason = str(exc)
            break

    if kind not in FILE_KINDS:
        raise ValueError("TypeSafe file kind outside the closed set")
    resolution = resolve_path(state)
    result = _decide(resolution, flags, kind, taxonomy, observation["path"])
    return TaxonomyFileResult(
        file=result,
        node=resolution.node_id,
        tree_path=resolution.tree_path,
        resolved_depth=resolution.resolved_depth,
        path_score=resolution.path_score,
        edges=tuple(
            {
                "q": edge.question_id,
                "node": edge.node_id,
                "p": edge.probability,
                "confidence": edge.confidence,
            }
            for edge in resolution.edges
        ),
        alternates=tuple(
            {"tree_path": list(path), "path_score": score} for path, score in resolution.alternates
        ),
        rounds=state.rounds_used,
        taxonomy_version=taxonomy.taxonomy_version,
    )


# --- disposition (design section 4, mirrors classify_file._resolve_disposition;
# node-shaped instead of project-string-shaped, kept in sync manually until the S8
# cutover deletes flat mode per the design's own migration-slice table) -----------


def _node(taxonomy: Taxonomy, node_id: str | None) -> TaxonomyNode | None:
    return taxonomy.node(node_id) if node_id is not None else None


def _has_linear_sibling(taxonomy: Taxonomy, node: TaxonomyNode | None) -> str | None:
    if node is None:
        return None
    product_id = node.id if node.type == TAXONOMY_NODE_TYPE_PRODUCT else node.parent
    if product_id is None:
        return None
    for child in taxonomy.children_of(product_id):
        if child.leaf_kind == "linear":
            return child.id
    return None


def _legal_dispositions(taxonomy: Taxonomy, node: TaxonomyNode | None) -> tuple[str, ...]:
    linear_extra = (FILE_DISPOSITION_FILE_TO_LINEAR,) if _has_linear_sibling(taxonomy, node) else ()
    if node is not None and node.id == PERSONAL_DOCS_PRODUCT_ID:
        # R6 (design section 4.1): a file resolved only to the personal-docs
        # product (no specific personal leaf won) still files to ~/Documents.
        return (
            FILE_DISPOSITION_PERSONAL_DOCS,
            FILE_DISPOSITION_ARCHIVE,
            FILE_DISPOSITION_TRASH_CANDIDATE,
            FILE_DISPOSITION_KEEP,
        )
    if node is None or node.type != TAXONOMY_NODE_TYPE_LEAF:
        return (
            FILE_DISPOSITION_ARCHIVE,
            FILE_DISPOSITION_TRASH_CANDIDATE,
            FILE_DISPOSITION_KEEP,
        ) + linear_extra
    if node.leaf_kind == "personal":
        return (
            FILE_DISPOSITION_PERSONAL_DOCS,
            FILE_DISPOSITION_ARCHIVE,
            FILE_DISPOSITION_TRASH_CANDIDATE,
            FILE_DISPOSITION_KEEP,
        )
    if node.leaf_kind == "linear":
        return (
            FILE_DISPOSITION_FILE_TO_LINEAR,
            FILE_DISPOSITION_ARCHIVE,
            FILE_DISPOSITION_TRASH_CANDIDATE,
            FILE_DISPOSITION_KEEP,
            FILE_DISPOSITION_ATTACH_EVIDENCE,
        )
    base = (
        FILE_DISPOSITION_ARCHIVE,
        FILE_DISPOSITION_TRASH_CANDIDATE,
        FILE_DISPOSITION_KEEP,
        FILE_DISPOSITION_ATTACH_EVIDENCE,
    )
    if node.local_path and not node.archived:
        base = (FILE_DISPOSITION_MOVE_TO_REPO,) + base
    return base + linear_extra


def _destination_hint(taxonomy: Taxonomy, node: TaxonomyNode | None, disposition: str) -> str:
    if disposition in (
        FILE_DISPOSITION_TRASH_CANDIDATE,
        FILE_DISPOSITION_KEEP,
        FILE_DISPOSITION_FILE_TO_LINEAR,
        FILE_DISPOSITION_ATTACH_EVIDENCE,
    ):
        return ""
    if node is None:
        return ""
    if node.type == TAXONOMY_NODE_TYPE_LEAF and node.leaf_kind == "personal":
        return node.destination or ""
    if node.type == TAXONOMY_NODE_TYPE_LEAF and node.leaf_kind == "repo" and node.local_path:
        return str(Path(node.local_path).expanduser() / "docs")
    if node.id == PERSONAL_DOCS_PRODUCT_ID:
        return FILE_DEST_LIFE
    return ""


def _decide(
    resolution: TaxonomyResolution,
    flags: dict[str, float],
    kind: str,
    taxonomy: Taxonomy,
    path: str,
) -> classify_file.FileResult:
    node = _node(taxonomy, resolution.node_id)
    private_guard = flags[FILE_FLAG_PRIVATE] >= FILE_FLAG_FLOORS["private_guard"]
    loss_record_guard = flags[FILE_FLAG_LOSS_RECORD] >= FILE_FLAG_FLOORS["loss_record"]
    would_trash = (
        flags[FILE_FLAG_BACKUP] >= FILE_FLAG_FLOORS["trash_backup"]
        and flags[FILE_FLAG_REGENERABLE] >= FILE_FLAG_FLOORS["trash_regenerable"]
    )
    is_issue_list = flags[FILE_FLAG_ISSUE_LIST] >= FILE_FLAG_FLOORS["issue_to_linear"]
    is_evidence = flags[FILE_FLAG_EVIDENCE] >= FILE_FLAG_FLOORS["evidence"]
    linear_sibling = _has_linear_sibling(taxonomy, node)
    if private_guard:
        reason = REASON_FILE_PRIVATE_GUARD
    elif loss_record_guard:
        reason = REASON_FILE_LOSS_RECORD_GUARD
    else:
        reason = REASON_SELECTED
    needs_triage = needs_ticket = needs_redaction = False
    important = private_guard or loss_record_guard

    if not private_guard and not loss_record_guard and would_trash:
        disposition = FILE_DISPOSITION_TRASH_CANDIDATE
        confidence = min(
            flags[FILE_FLAG_BACKUP],
            flags[FILE_FLAG_REGENERABLE],
            1 - flags[FILE_FLAG_PRIVATE],
            1 - flags[FILE_FLAG_LOSS_RECORD],
        )
    elif is_issue_list and linear_sibling is not None:
        disposition = FILE_DISPOSITION_FILE_TO_LINEAR
        confidence = min(flags[FILE_FLAG_ISSUE_LIST], resolution.path_score)
    elif is_issue_list:
        disposition, confidence, reason, needs_triage = (
            FILE_DISPOSITION_KEEP,
            flags[FILE_FLAG_ISSUE_LIST],
            REASON_FILE_ISSUE_NEEDS_TRIAGE,
            True,
        )
    elif (
        node is not None
        and node.type == TAXONOMY_NODE_TYPE_LEAF
        and node.leaf_kind == "repo"
        and node.local_path
        and not node.archived
        and kind in classify_file.FILE_KINDS_MOVABLE_TO_REPO
    ):
        disposition, confidence = FILE_DISPOSITION_MOVE_TO_REPO, resolution.path_score
    elif node is not None and (
        (node.type == TAXONOMY_NODE_TYPE_LEAF and node.leaf_kind == "personal")
        or node.id == PERSONAL_DOCS_PRODUCT_ID
    ):
        disposition, confidence = FILE_DISPOSITION_PERSONAL_DOCS, resolution.path_score
    elif is_evidence and linear_sibling is not None:
        disposition, confidence, needs_ticket, needs_redaction = (
            FILE_DISPOSITION_ATTACH_EVIDENCE,
            flags[FILE_FLAG_EVIDENCE],
            True,
            private_guard,
        )
    elif is_evidence:
        disposition, confidence, reason, needs_triage = (
            FILE_DISPOSITION_KEEP,
            flags[FILE_FLAG_EVIDENCE],
            REASON_FILE_EVIDENCE_NEEDS_TRIAGE,
            True,
        )
    elif node is not None:
        disposition, confidence = FILE_DISPOSITION_ARCHIVE, resolution.path_score
    else:
        disposition, confidence = FILE_DISPOSITION_KEEP, 0.0

    if disposition not in FILE_DISPOSITIONS:
        raise ValueError("computed taxonomy disposition outside the closed set")
    if disposition not in _legal_dispositions(taxonomy, node):
        disposition, confidence, reason = FILE_DISPOSITION_KEEP, 0.0, "disposition illegal for node"
        needs_triage = needs_ticket = needs_redaction = False
    elif confidence < FILE_DISPOSITION_CONFIDENCE_FLOORS[disposition]:
        disposition, confidence, reason = FILE_DISPOSITION_KEEP, 0.0, REASON_BELOW_CONFIDENCE
        needs_triage = needs_ticket = needs_redaction = False

    project = (
        node.project_key
        if (node is not None and node.type == TAXONOMY_NODE_TYPE_LEAF and node.project_key)
        else FILE_PROJECT_NONE
    )
    return classify_file.FileResult(
        path=path,
        project=project,
        kind=kind,
        disposition=disposition,
        destination_hint=_destination_hint(taxonomy, node, disposition),
        confidence=confidence,
        reason=resolution.reason if reason == REASON_SELECTED else reason,
        needs_triage=needs_triage,
        needs_ticket=needs_ticket,
        needs_redaction=needs_redaction,
        important=important,
    )
