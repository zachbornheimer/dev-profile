"""Pure derivation rules (P0-P7) that turn the repo catalog, Linear projects
and personal areas into a taxonomy node list. No filesystem, network or clock
access — see /tmp/organize/taxonomy-design.md section 1.3 for the rule specs
this module implements, in order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from taxonomy_tokens import (
    GENERIC_STOPWORDS,
    document_frequency,
    normalize_keyword,
    repo_basename,
    words,
)

DESCRIPTION_CHARS = 180
FAMILY_MAX_DF = 12
DESCRIPTION_TOKEN_MAX_DF = 3
FULL_CHOICE_MAX_SIBLINGS = 12
FAMILY_CANDIDATE_KEYWORDS = 4
LINEAR_ATTACH_MAX_DF = 2

LINEAR_NAME_STOPWORDS = frozenset(
    {
        "launch",
        "exit",
        "summit",
        "phase",
        "ops",
        "ad",
        "hoc",
        "support",
        "inbound",
        "callback",
        "feed",
        "hosting",
        "for",
        "of",
        "and",
        "the",
        "a",
        "an",
        "to",
    }
)

# Tech-stack / role descriptors that show up as an early keyword on many
# unrelated repos — a shared language or role is not a shared product.
# Language tags are additionally excluded per-repo via the catalog's own
# `language` field, so this list covers the non-language generic terms
# that still slipped under FAMILY_MAX_DF in practice (e.g. "plugin",
# "wordpress", "sdk", "git", "macos").
FAMILY_KEY_STOPWORDS = frozenset(
    {
        "cli",
        "sdk",
        "wordpress",
        "plugin",
        "docker",
        "backend",
        "frontend",
        "tool",
        "tooling",
        "api",
        "git",
        "macos",
        "launchd",
        "metadata",
        "nlp",
        "worktree",
        "react",
        "react-native",
        "node",
        "nodejs",
        "http-client",
        "grpc",
        "expo",
        "supabase",
        "auth",
        "forms",
        "hosting",
        "infrastructure",
        "mobile-app",
        # Generated-SDK mirror tags: every language's generated client repeats
        # these, so they name a build mechanism, not a product. A framework
        # tag like "laravel" is the same shape (many unrelated repos can use
        # it) and is stopped for the same reason.
        "generated",
        "packagist",
        "laravel",
    }
)

AREA_ROOT_NONE = "area:none"

_ID_UNSAFE_RE = re.compile(r"[^a-z0-9._-]+")


def _id_slug(text: str) -> str:
    """Node ids are ASCII `[a-z0-9:/._-]`; a raw catalog keyword can contain
    a space or other punctuation (e.g. "final expense"), so any id segment
    built from one must be slugified."""
    return _ID_UNSAFE_RE.sub("-", text.strip().lower()).strip("-")


@dataclass
class BuildInputs:
    repos: list[dict[str, Any]]
    linear_projects: list[dict[str, Any]]
    personal_areas: list[dict[str, Any]]
    overrides: dict[str, Any]
    developer_clones: dict[str, str] = field(default_factory=dict)


def build_nodes(inputs: BuildInputs) -> list[dict[str, Any]]:
    """Run P0-P7 in order and return the flat node list (areas, products,
    leaves), each carrying a `derived_by` tag for diff review."""
    areas = _build_areas(inputs.overrides)
    repo_area = _assign_repo_areas(inputs.repos, inputs.overrides)
    products, leaves_by_product = _build_products(inputs, repo_area)
    _attach_personal(inputs, areas, products, leaves_by_product)
    _attach_linear(inputs, areas, products, leaves_by_product)
    _mark_large_areas(areas, products)
    _finalize_area_criteria(areas, products, inputs.overrides.get("area_labels", {}))
    _apply_criteria_overrides(
        areas, products, leaves_by_product, inputs.overrides.get("criteria", {})
    )

    nodes: list[dict[str, Any]] = list(areas.values())
    nodes.extend(products.values())
    for leaves in leaves_by_product.values():
        nodes.extend(leaves)
    return nodes


# --- P0: areas from orgs -----------------------------------------------


def _build_areas(overrides: dict[str, Any]) -> dict[str, dict[str, Any]]:
    org_areas = overrides.get("org_areas", {})
    area_labels = overrides.get("area_labels", {})
    area_ids = sorted(
        {entry["area"] for entry in org_areas.values()} | set(area_labels)
    )
    areas: dict[str, dict[str, Any]] = {}
    for area_id in area_ids:
        areas[area_id] = {
            "id": area_id,
            "parent": None,
            "depth": 1,
            "type": "area",
            "label": area_labels.get(area_id, area_id.split(":", 1)[-1]),
            "criteria": "",
            "tokens": [],
            "derived_by": "override:org_areas",
        }
    return areas


def _assign_repo_areas(
    repos: list[dict[str, Any]], overrides: dict[str, Any]
) -> dict[str, str]:
    org_areas = overrides.get("org_areas", {})
    repo_area_override = overrides.get("repo_area", {})
    assigned: dict[str, str] = {}
    for repo in repos:
        full_name = repo["full_name"]
        if full_name in repo_area_override:
            assigned[full_name] = repo_area_override[full_name]["area"]
            continue
        org = full_name.split("/", 1)[0]
        org_entry = org_areas.get(org)
        if org_entry:
            assigned[full_name] = org_entry["area"]
    return assigned


# --- P1: token enrichment ------------------------------------------------


def _repo_keyword_tokens(repo: dict[str, Any]) -> set[str]:
    tokens = {repo_basename(repo["full_name"])}
    for keyword in repo.get("keywords") or []:
        normalized = normalize_keyword(keyword)
        tokens |= words(normalized.replace("-", " "))
        if normalized not in GENERIC_STOPWORDS:
            tokens.add(normalized)
    return tokens


def _enrich_repo_tokens(
    repo: dict[str, Any], description_df: dict[str, int]
) -> set[str]:
    tokens = _repo_keyword_tokens(repo)
    description = str(repo.get("description_proposed") or "")
    for token in words(description):
        if description_df.get(token, 0) <= DESCRIPTION_TOKEN_MAX_DF:
            tokens.add(token)
    return tokens


def _description_document_frequency(repos: list[dict[str, Any]]) -> dict[str, int]:
    token_sets = [words(str(r.get("description_proposed") or "")) for r in repos]
    return document_frequency(token_sets)


# --- P2: product families -------------------------------------------------


def _first_n_keywords(repo: dict[str, Any], n: int) -> list[str]:
    return [normalize_keyword(k) for k in (repo.get("keywords") or [])[:n]]


def _family_key_candidates(repo: dict[str, Any]) -> list[str]:
    """A repo's first-4-keyword family candidates, minus its own language
    tag and generic tech/role descriptors (FAMILY_KEY_STOPWORDS) — those
    describe the repo's stack, not its product identity."""
    language = str(repo.get("language") or "").strip().lower()
    return [
        key
        for key in _first_n_keywords(repo, FAMILY_CANDIDATE_KEYWORDS)
        if key != language and key not in FAMILY_KEY_STOPWORDS
    ]


def _basename_prefix(full_name: str) -> str:
    """The text before a repo basename's first "-", or the whole basename
    when it has none (e.g. "rapidsign-sdk-go" -> "rapidsign", "zyins" ->
    "zyins", "isacrm" -> "isacrm" — no hyphen, so it never merges into a
    same-prefix family by accident)."""
    basename = repo_basename(full_name)
    prefix, separator, _rest = basename.partition("-")
    return prefix if separator else basename


def _family_key_for_area(
    area_repos: list[dict[str, Any]], keyword_df: dict[str, int]
) -> dict[str, str]:
    """Choose each repo's family key (or none) within one area."""
    candidate_repo_count: dict[str, int] = {}
    for repo in area_repos:
        for key in set(_family_key_candidates(repo)):
            candidate_repo_count[key] = candidate_repo_count.get(key, 0) + 1

    def eligible(key: str) -> bool:
        df = keyword_df.get(key, 0)
        return candidate_repo_count.get(key, 0) >= 2 and df >= 2 and df <= FAMILY_MAX_DF

    family_key: dict[str, str] = {}
    for repo in area_repos:
        # A repo's own basename prefix outranks a DF-selected keyword when
        # the prefix is *itself* an eligible candidate — i.e. some other
        # repo in the area independently names it as a keyword, shared by
        # >=2 repos and under FAMILY_MAX_DF (`eligible`, above). This is
        # what keeps "<product>-sdk-<lang>" repos (whose own first keywords
        # are generic build/mirror tags) grouped with their parent product
        # instead of splitting three ways on the lowest-DF tag (e.g.
        # "isaapi"/"generated"/"packagist" for rapidsign) — while a bare
        # naming-convention prefix with no independent keyword evidence
        # (e.g. "wp-*", "sdk-*") never triggers it, so unrelated repos that
        # merely share a hyphenated prefix do not get merged by accident.
        prefix = _basename_prefix(repo["full_name"])
        if eligible(prefix):
            family_key[repo["full_name"]] = prefix
            continue
        candidates = [k for k in _family_key_candidates(repo) if eligible(k)]
        if not candidates:
            continue
        candidates = sorted(
            set(candidates),
            key=lambda k: (keyword_df.get(k, 0), -candidate_repo_count.get(k, 0), k),
        )
        family_key[repo["full_name"]] = candidates[0]
    return family_key


# --- P3: archived fold -----------------------------------------------------


def _pick_alias_target(
    archived: dict[str, Any], live_leaves: list[dict[str, Any]]
) -> dict[str, Any]:
    """Most token overlap wins; newest `pushed_at` breaks a tie.

    Two stable passes: sort newest-first, then stable-sort by descending
    overlap — Python's sort stability preserves the recency order within
    each overlap tier.
    """
    archived_tokens = set(_repo_keyword_tokens(archived))
    by_recency = sorted(
        live_leaves, key=lambda leaf: leaf.get("_pushed_at_sort_key", ""), reverse=True
    )
    ranked = sorted(
        by_recency,
        key=lambda leaf: -len(archived_tokens & set(leaf.get("tokens") or [])),
    )
    return ranked[0]


def _build_products(
    inputs: BuildInputs, repo_area: dict[str, str]
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    repos = inputs.repos
    overrides = inputs.overrides
    description_df = _description_document_frequency(repos)
    all_keyword_df = document_frequency([set(r.get("keywords") or []) for r in repos])
    all_keyword_df = {normalize_keyword(k): v for k, v in all_keyword_df.items()}

    {r["full_name"]: r for r in repos}
    by_area: dict[str, list[dict[str, Any]]] = {}
    for repo in repos:
        area = repo_area.get(repo["full_name"])
        if area is None:
            continue
        by_area.setdefault(area, []).append(repo)

    family_key_by_repo: dict[str, str] = {}
    for area, area_repos in by_area.items():
        family_key_by_repo.update(_family_key_for_area(area_repos, all_keyword_df))

    merge_target: dict[str, str] = {}
    merge_why: dict[str, str] = {}
    for merge in overrides.get("product_merge", []):
        for member in merge["members"]:
            merge_target[member] = merge["into"]
            merge_why[merge["into"]] = merge["why"]

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for repo in repos:
        area = repo_area.get(repo["full_name"])
        if area is None:
            continue
        full_name = repo["full_name"]
        if full_name in merge_target:
            product_id = merge_target[full_name]
        elif full_name in family_key_by_repo:
            product_id = f"product:{_id_slug(family_key_by_repo[full_name])}"
        else:
            product_id = f"product:{_id_slug(repo_basename(full_name))}"
        grouped.setdefault((area, product_id), []).append(repo)

    products: dict[str, dict[str, Any]] = {}
    leaves_by_product: dict[str, list[dict[str, Any]]] = {}
    for (area, product_id), members in grouped.items():
        live = [r for r in members if not r.get("archived")]
        archived = [r for r in members if r.get("archived")]
        derived_by = (
            "override:merge"
            if product_id in merge_why
            else "family"
            if len(live) > 1 or (live and len(members) > 1)
            else "singleton"
        )

        leaves: list[dict[str, Any]] = []
        if live:
            for repo in live:
                tokens = _enrich_repo_tokens(repo, description_df)
                leaf = _repo_leaf_node(
                    repo, product_id, tokens, inputs.developer_clones
                )
                leaves.append(leaf)
            for repo in archived:
                target = _pick_alias_target(repo, leaves)
                target.setdefault("aliases", []).append(repo["full_name"])
                target["tokens"] = sorted(
                    set(target["tokens"]) | _repo_keyword_tokens(repo)
                )
        else:
            primary = max(archived, key=lambda r: r.get("pushed_at") or "")
            tokens: set[str] = set()
            for repo in archived:
                tokens |= _enrich_repo_tokens(repo, description_df)
            leaf = _repo_leaf_node(primary, product_id, tokens, inputs.developer_clones)
            leaf["archived"] = True
            leaf["aliases"] = sorted(
                r["full_name"]
                for r in archived
                if r["full_name"] != primary["full_name"]
            )
            leaves.append(leaf)

        for leaf in leaves:
            leaf.pop("_pushed_at_sort_key", None)

        product_tokens = sorted(
            {tok for leaf in leaves for tok in leaf.get("tokens") or []}
        )
        products[product_id] = {
            "id": product_id,
            "parent": area,
            "depth": 2,
            "type": "product",
            "label": product_id.split(":", 1)[-1],
            "criteria": _product_criteria(product_id, leaves, product_tokens),
            "tokens": product_tokens,
            "derived_by": derived_by,
        }
        if product_id in merge_why:
            products[product_id]["why"] = merge_why[product_id]
        leaves_by_product[product_id] = leaves

    return products, leaves_by_product


def _repo_leaf_node(
    repo: dict[str, Any],
    product_id: str,
    tokens: set[str],
    developer_clones: dict[str, str],
) -> dict[str, Any]:
    full_name = repo["full_name"]
    local_path = developer_clones.get(full_name) or repo.get("local_path")
    return {
        "id": f"leaf:repo:{full_name.lower()}",
        "parent": product_id,
        "depth": 3,
        "type": "leaf",
        "leaf_kind": "repo",
        "project_key": full_name,
        "local_path": local_path,
        "aliases": [],
        "criteria": _leaf_criteria(repo),
        "tokens": sorted(tokens),
        "derived_by": "repo",
        "_pushed_at_sort_key": repo.get("pushed_at") or "",
    }


def _leaf_criteria(repo: dict[str, Any]) -> str:
    text = str(
        repo.get("description_proposed")
        or repo.get("description_current")
        or repo["full_name"]
    )
    return text[:DESCRIPTION_CHARS]


def _product_criteria(
    product_id: str, leaves: list[dict[str, Any]], tokens: list[str]
) -> str:
    members = ", ".join(leaf.get("project_key", leaf["id"]) for leaf in leaves)
    top_tokens = ", ".join(tokens[:6])
    text = f"Products: {members}; {top_tokens}"
    return text[:DESCRIPTION_CHARS]


# --- P5: personal -----------------------------------------------------


def _attach_personal(
    inputs: BuildInputs,
    areas: dict[str, dict[str, Any]],
    products: dict[str, dict[str, Any]],
    leaves_by_product: dict[str, list[dict[str, Any]]],
) -> None:
    area_id = "area:personal-life"
    if area_id not in areas:
        return
    product_id = "product:personal-docs"
    leaves = []
    for entry in inputs.personal_areas:
        key = entry["key"]
        leaves.append(
            {
                "id": f"leaf:personal:{key}",
                "parent": product_id,
                "depth": 3,
                "type": "leaf",
                "leaf_kind": "personal",
                "project_key": f"personal:{key}",
                "destination": entry["destination"],
                "criteria": entry.get("criteria", entry["label"])[:DESCRIPTION_CHARS],
                "tokens": sorted(words(entry["label"]) | set(entry.get("tokens", []))),
                "derived_by": "personal-areas",
            }
        )
    tokens = sorted({tok for leaf in leaves for tok in leaf["tokens"]})
    products[product_id] = {
        "id": product_id,
        "parent": area_id,
        "depth": 2,
        "type": "product",
        "label": "Personal documents",
        "criteria": "Personal life documents filed by area (Finance, Family, Health, ...).",
        "tokens": tokens,
        "derived_by": "personal-areas",
    }
    leaves_by_product[product_id] = leaves


# --- P4: Linear attach -----------------------------------------------------


def _linear_tokens(name: str) -> set[str]:
    """Word-split the Linear project name, keeping short-but-meaningful
    codes like "zq" or "evo" (mirrors classify_file.py's raw filename
    segments: only stopwords and digits are dropped, not short length)."""
    raw = name.replace("—", " ").replace("&", " ").replace(":", " ").replace("→", " ")
    candidates = re.split(r"[^a-z0-9]+", raw.lower())
    return {
        t
        for t in candidates
        if t and t not in LINEAR_NAME_STOPWORDS and not t.isdigit()
    }


def _product_identity_tokens(
    product: dict[str, Any],
    leaves: list[dict[str, Any]],
    repos_by_full_name: dict[str, dict[str, Any]],
) -> tuple[set[str], set[str]]:
    """A product's identity for Linear matching, split into (basename_tokens,
    keyword_tokens): each repo leaf's basename, split into words (so a
    multi-word Linear name like "Book Bestie" can reach "book-bestie"), and
    every keyword kept *whole* — not split into words. Splitting a keyword
    is what let a buried word like "tracking" (from the keyword
    "book-tracking") or "efficiency" (from "token-efficiency") falsely
    connect an unrelated Linear project; kept whole, those only match a
    Linear name that spells them out the same way, while a genuinely
    identifying single-word keyword like "dragongate" still matches
    exactly. basename_tokens rank above keyword_tokens when both match,
    since a product's own name is a stronger identity signal than an
    incidental shared keyword (e.g. "progress" is evident-output's 6th
    keyword but product:progress's own basename)."""
    repo_leaves = [leaf for leaf in leaves if leaf.get("leaf_kind") == "repo"]
    if not repo_leaves:
        return set(product["tokens"]), set()
    basename_tokens: set[str] = set()
    keyword_tokens: set[str] = set()
    for leaf in repo_leaves:
        repo = repos_by_full_name.get(leaf["project_key"])
        if repo is None:
            continue
        basename = repo_basename(repo["full_name"])
        basename_tokens |= words(basename.replace("-", " "))
        basename_tokens.add(basename)
        for keyword in repo.get("keywords") or []:
            keyword_tokens.add(normalize_keyword(keyword))
    return basename_tokens, keyword_tokens - basename_tokens


def _is_better_match(
    candidate: tuple[int, int], current: tuple[int, int] | None
) -> bool:
    """Lower (tier, df) wins: basename tier beats keyword tier; within a
    tier, the rarer (lower document frequency) token wins."""
    return current is None or candidate < current


def _attach_linear(
    inputs: BuildInputs,
    areas: dict[str, dict[str, Any]],
    products: dict[str, dict[str, Any]],
    leaves_by_product: dict[str, list[dict[str, Any]]],
) -> None:
    repos_by_full_name = {r["full_name"]: r for r in inputs.repos}
    identity_tokens = {
        product_id: _product_identity_tokens(
            product, leaves_by_product.get(product_id, []), repos_by_full_name
        )
        for product_id, product in products.items()
    }
    all_tokens_by_product = {
        product_id: basename | keyword
        for product_id, (basename, keyword) in identity_tokens.items()
    }
    product_token_df = document_frequency(list(all_tokens_by_product.values()))
    linear_area_override = inputs.overrides.get("linear_area", {})

    unattached: list[dict[str, Any]] = []
    for project in inputs.linear_projects:
        name = project["name"]
        tokens = _linear_tokens(name)
        best_product = None
        best_rank = None
        for product_id in sorted(products):
            basename_tokens, keyword_tokens = identity_tokens[product_id]
            for token in tokens & basename_tokens:
                rank = (0, product_token_df.get(token, 0))
                if _is_better_match(rank, best_rank):
                    best_rank, best_product = rank, product_id
            for token in tokens & keyword_tokens:
                df = product_token_df.get(token, 0)
                if df > LINEAR_ATTACH_MAX_DF:
                    continue
                rank = (1, df)
                if _is_better_match(rank, best_rank):
                    best_rank, best_product = rank, product_id
        if best_product is None:
            unattached.append(project)
            continue
        leaf = _linear_leaf(project, best_product)
        leaves_by_product.setdefault(best_product, []).append(leaf)

    _attach_unattached_linear(
        unattached, areas, products, leaves_by_product, linear_area_override
    )


def _linear_leaf(project: dict[str, Any], product_id: str) -> dict[str, Any]:
    name = project["name"]
    return {
        "id": f"leaf:linear:{name}",
        "parent": product_id,
        "depth": 3,
        "type": "leaf",
        "leaf_kind": "linear",
        "project_key": f"linear:{name}",
        "linear_id": project.get("id"),
        "criteria": f"Linear project: {name}"[:DESCRIPTION_CHARS],
        "tokens": sorted(_linear_tokens(name)),
        "derived_by": "linear-attach",
    }


def _attach_unattached_linear(
    unattached: list[dict[str, Any]],
    areas: dict[str, dict[str, Any]],
    products: dict[str, dict[str, Any]],
    leaves_by_product: dict[str, list[dict[str, Any]]],
    linear_area_override: dict[str, Any],
) -> None:
    if not unattached:
        return
    default_area = "area:ventures"
    if default_area not in areas:
        return

    by_area: dict[str, list[dict[str, Any]]] = {}
    for project in unattached:
        area = linear_area_override.get(project["name"], {}).get("area", default_area)
        by_area.setdefault(area, []).append(project)

    for area, projects in by_area.items():
        token_counts: dict[str, int] = {}
        for project in projects:
            for token in _linear_tokens(project["name"]):
                token_counts[token] = token_counts.get(token, 0) + 1
        grouped: dict[str, list[dict[str, Any]]] = {}
        for project in projects:
            candidates = [
                t
                for t in _linear_tokens(project["name"])
                if token_counts.get(t, 0) >= 2
            ]
            key = min(candidates) if candidates else None
            group_id = (
                f"product:{key}" if key else f"product:{_slugify(project['name'])}"
            )
            grouped.setdefault(group_id, []).append(project)

        for product_id, group_projects in grouped.items():
            leaves = [_linear_leaf(p, product_id) for p in group_projects]
            tokens = sorted({tok for leaf in leaves for tok in leaf["tokens"]})
            products[product_id] = {
                "id": product_id,
                "parent": area,
                "depth": 2,
                "type": "product",
                "label": product_id.split(":", 1)[-1],
                "criteria": _product_criteria(product_id, leaves, tokens),
                "tokens": tokens,
                "derived_by": "linear-unattached",
            }
            leaves_by_product[product_id] = leaves


def _slugify(name: str) -> str:
    tokens = sorted(_linear_tokens(name)) or ["other"]
    return "-".join(tokens[:3])


# --- P6: area criteria text -------------------------------------------


def _finalize_area_criteria(
    areas: dict[str, dict[str, Any]],
    products: dict[str, dict[str, Any]],
    area_labels: dict[str, str],
) -> None:
    """Area criteria = the override label plus the top 8 tokens by member
    (product) frequency; area tokens = the same top-8 list."""
    token_counts_by_area: dict[str, dict[str, int]] = {}
    for product in products.values():
        area_id = product["parent"]
        counts = token_counts_by_area.setdefault(area_id, {})
        for token in product["tokens"]:
            counts[token] = counts.get(token, 0) + 1

    for area_id, area in areas.items():
        counts = token_counts_by_area.get(area_id, {})
        top_tokens = sorted(counts, key=lambda t: (-counts[t], t))[:8]
        area["tokens"] = top_tokens
        label = area_labels.get(area_id, area["label"])
        area["criteria"] = (
            f"{label}: {', '.join(top_tokens)}"[:DESCRIPTION_CHARS] or label
        )


def _apply_criteria_overrides(
    areas: dict[str, dict[str, Any]],
    products: dict[str, dict[str, Any]],
    leaves_by_product: dict[str, list[dict[str, Any]]],
    criteria_overrides: dict[str, str],
) -> None:
    if not criteria_overrides:
        return
    by_id: dict[str, dict[str, Any]] = dict(areas)
    by_id.update(products)
    for leaves in leaves_by_product.values():
        for leaf in leaves:
            by_id[leaf["id"]] = leaf
    for node_id, criteria in criteria_overrides.items():
        node = by_id.get(node_id)
        if node is not None:
            node["criteria"] = str(criteria)[:DESCRIPTION_CHARS]


# --- P7: sibling cap ---------------------------------------------------


def _mark_large_areas(
    areas: dict[str, dict[str, Any]], products: dict[str, dict[str, Any]]
) -> None:
    counts: dict[str, int] = {}
    for product in products.values():
        counts[product["parent"]] = counts.get(product["parent"], 0) + 1
    for area_id, count in counts.items():
        if area_id in areas and count > FULL_CHOICE_MAX_SIBLINGS:
            areas[area_id]["large"] = True
