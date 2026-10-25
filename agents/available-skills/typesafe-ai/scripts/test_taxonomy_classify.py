"""Unit tests for S4 (beam search, round planning) and S5 (shortlist/strong-match
rewired onto taxonomy leaves) -- design contract section 7."""

from __future__ import annotations

import importlib
import itertools
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

taxonomy = importlib.import_module("taxonomy")
tc = importlib.import_module("taxonomy_classify")
classify_file = importlib.import_module("classify_file")
constants = importlib.import_module("constants")

REAL_TAXONOMY_PATH = SCRIPTS.parent.parent / "organize-files" / "data" / "taxonomy.json"


def _node(node_id, parent, depth, node_type, **kw):
    base = {
        "id": node_id,
        "parent": parent,
        "depth": depth,
        "type": node_type,
        "label": node_id,
        "criteria": kw.pop("criteria", f"criteria for {node_id}"),
        "tokens": kw.pop("tokens", []),
    }
    base.update(kw)
    return base


def _small_taxonomy() -> taxonomy.Taxonomy:
    """One small area (homelab, 1 multi-leaf product) and one large area
    (insurance-software, >12 products) so both request-shape branches are covered."""
    nodes = [
        _node("area:homelab", None, 1, "area", tokens=["homelab", "nas"]),
        _node("product:homelab", "area:homelab", 2, "product"),
        _node(
            "leaf:repo:a/homelab",
            "product:homelab",
            3,
            "leaf",
            leaf_kind="repo",
            project_key="a/homelab",
            local_path="/x/homelab",
            tokens=["homelab", "nas", "gorillabank"],
        ),
        _node(
            "leaf:repo:a/nas-recovery",
            "product:homelab",
            3,
            "leaf",
            leaf_kind="repo",
            project_key="a/nas-recovery",
            local_path="/x/nas-recovery",
            tokens=["nas-recovery", "nas"],
        ),
        _node("area:big", None, 1, "area", tokens=[], large=True),
    ]
    for i in range(14):
        product_id = f"product:p{i}"
        nodes.append(_node(product_id, "area:big", 2, "product", tokens=[f"tok{i}"]))
        nodes.append(
            _node(
                f"leaf:repo:a/p{i}",
                product_id,
                3,
                "leaf",
                leaf_kind="repo",
                project_key=f"a/p{i}",
                local_path=f"/x/p{i}",
                tokens=[f"tok{i}"],
            )
        )
    nodes.append(_node("area:solo", None, 1, "area", tokens=["solo"]))
    nodes.append(_node("product:solo", "area:solo", 2, "product"))
    nodes.append(
        _node(
            "leaf:repo:a/solo",
            "product:solo",
            3,
            "leaf",
            leaf_kind="repo",
            project_key="a/solo",
            local_path="/x/solo",
            tokens=["solo"],
        )
    )
    payload = {
        "schema_version": 1,
        "taxonomy_version": "1.test",
        "generated_at": "2026-01-01T00:00:00Z",
        "nodes": nodes,
    }
    return taxonomy.parse_taxonomy(payload)


def _observation(filename="notes.md", excerpt=""):
    return {
        "path": f"/Users/z/Desktop/{filename}",
        "filename": filename,
        "extension": ".md",
        "size": 10,
        "mtime": "2026-01-01T00:00:00Z",
        "is_dir": False,
        "excerpt": excerpt,
        "entries": [],
    }


class RequestShapeTests(unittest.TestCase):
    def test_round1_has_area_kind_flags_and_at_most_two_product_questions(self):
        tx = _small_taxonomy()
        state = tc._RoundState(observation=_observation(), taxonomy=tx)
        state.scored_leaves = []
        state.strong_match = None
        questions, _slugs = tc._build_round_1(state)
        self.assertIn("area", questions)
        self.assertIn(classify_file.QUESTION_KIND, questions)
        for flag_id in constants.FILE_FLAGS:
            self.assertIn(flag_id, questions)
        self.assertNotIn("disposition", questions)
        product_questions = [q for q in questions if q.startswith("product@")]
        self.assertLessEqual(len(product_questions), constants.FILE_TAXONOMY_SPECULATIVE_AREAS)

    def test_strong_match_round1_is_kind_and_flags_only(self):
        tx = _small_taxonomy()
        state = tc._RoundState(observation=_observation(), taxonomy=tx)
        state.scored_leaves = []
        state.strong_match = "leaf:repo:a/homelab"
        questions, _slugs = tc._build_round_1(state)
        self.assertNotIn("area", questions)
        self.assertFalse([q for q in questions if q.startswith("product@")])
        self.assertIn(classify_file.QUESTION_KIND, questions)
        for flag_id in constants.FILE_FLAGS:
            self.assertIn(flag_id, questions)

    def test_large_area_product_question_offers_four_to_eight_plus_other(self):
        tx = _small_taxonomy()
        question, _slugs = tc._product_question(tx, "area:big", [])
        non_other = [k for k in question["criteria"] if k != constants.FILE_TAXONOMY_OTHER]
        self.assertGreaterEqual(len(non_other), constants.FILE_TAXONOMY_LARGE_AREA_MIN_OPTIONS)
        self.assertLessEqual(len(non_other), constants.FILE_PROJECT_CANDIDATE_LIMIT)
        self.assertIn(constants.FILE_TAXONOMY_OTHER, question["criteria"])

    def test_every_choice_question_has_other(self):
        tx = _small_taxonomy()
        area_q, _ = tc._area_question(tx)
        product_q, _ = tc._product_question(tx, "area:homelab", [])
        leaf_q, _ = tc._leaf_question(tx, "product:homelab")
        for question in (area_q, product_q, leaf_q):
            self.assertIn(constants.FILE_TAXONOMY_OTHER, question["criteria"])


class BeamAndBackoffTests(unittest.TestCase):
    def test_geometric_mean_excludes_single_child_edges(self):
        counted = tc.Edge("area", "n1", 0.5, 0.5, counted=True)
        implied = tc.Edge("", "n2", 1.0, 1.0, counted=False)
        # Single-child edge would drag a naive mean toward 1.0; excluding it must
        # leave the score exactly at the one counted edge's probability.
        self.assertAlmostEqual(tc.geometric_mean_score([counted, implied]), 0.5)

    def test_leaf_mass_split_evenly_resolves_at_product(self):
        area = tc.Edge("area", "area:x", 1.0, 1.0)
        product_a = tc.Edge("product@area:x", "product:a", 0.45, 0.45)
        product_b = tc.Edge("product@area:x", "product:b", 0.45, 0.45)
        depth, mass = tc.resolve_depth([area, product_a], {1: 0.55, 2: 0.40, 3: 0.30})
        self.assertEqual(depth, 2)
        self.assertAlmostEqual(mass, 0.45)
        del product_b  # documents the sibling that split the mass; not on this path

    def test_area_other_argmax_resolves_to_root(self):
        # "other" never becomes an Edge (no node_id to walk to) -- an empty edge list
        # must resolve to root, never raise.
        depth, mass = tc.resolve_depth([])
        self.assertEqual((depth, mass), (0, 1.0))

    def test_top_k_trimming_is_deterministic(self):
        candidates = [
            ([tc.Edge("q", "z", 0.5, 0.5)], 0.5),
            ([tc.Edge("q", "a", 0.5, 0.5)], 0.5),
            ([tc.Edge("q", "b", 0.9, 0.9)], 0.9),
        ]
        top = tc.top_k_by_score(candidates, k=2)
        self.assertEqual([edges[0].node_id for edges, _ in top], ["b", "a"])
        # Same input, same output on a repeated call.
        self.assertEqual(tc.top_k_by_score(candidates, k=2), top)

    def test_round2_judgment_error_still_resolves_from_round1(self):
        tx = _small_taxonomy()

        def flaky_ask(request):
            answers = _answer_everything(request, favor="a/homelab")
            if "leaf@product:homelab" in request["questions"]:
                raise ValueError("round 2 broke")
            return answers

        result = tc.classify(
            _observation("homelab-notes.md", "homelab nas gorillabank"), tx, flaky_ask
        )
        self.assertTrue(result.file.reason.startswith("partial:") or result.resolved_depth >= 1)


def _answer_everything(request, *, favor: str) -> dict:
    answers = {}
    for question_id, question in request["questions"].items():
        if question["type"] == "noul":
            answers[question_id] = {"type": "noul", "noul": 0.05}
            continue
        keys = list(question["criteria"])
        target = None
        for key, text in question["criteria"].items():
            if favor in text.lower():
                target = key
                break
        if target is None:
            target = keys[0]
        n = len(keys)
        probabilities = {k: (0.8 if k == target else 0.2 / max(n - 1, 1)) for k in keys}
        choice = "spec" if question_id == "kind" and "spec" in keys else target
        if question_id == "kind":
            choice = "document" if "document" in keys else keys[0]
            probabilities = {k: (0.8 if k == choice else 0.2 / max(n - 1, 1)) for k in keys}
        answers[question_id] = {
            "type": "choice",
            "choice": choice,
            "confidence": 0.8,
            "probabilities": probabilities,
        }
    return answers


class LegalityPropertyTests(unittest.TestCase):
    """Every node type x kind x flag-grid combination must produce a disposition
    inside `legal(node)`, and trash must never fire while flag_private >= 0.5."""

    def test_personal_docs_product_allows_personal_docs_disposition(self):
        """R6 (design section 4.1): a file resolved only to the personal-docs
        product (not a specific personal leaf) must still be able to file to
        ~/Documents rather than being vetoed to `keep` by the legality gate --
        caught on the real Desktop run (2026-09-23): all 38 personal files
        resolving to `product:personal-docs` came out `keep 0.00`."""
        taxonomy_obj = _small_taxonomy()
        payload = {
            "schema_version": 1,
            "taxonomy_version": "1.test",
            "generated_at": "x",
            "nodes": [
                {
                    "id": "area:personal-life",
                    "parent": None,
                    "depth": 1,
                    "type": "area",
                    "label": "l",
                    "criteria": "c",
                    "tokens": [],
                },
                {
                    "id": "product:personal-docs",
                    "parent": "area:personal-life",
                    "depth": 2,
                    "type": "product",
                    "label": "l",
                    "criteria": "c",
                    "tokens": [],
                },
                {
                    "id": "leaf:personal:life",
                    "parent": "product:personal-docs",
                    "depth": 3,
                    "type": "leaf",
                    "leaf_kind": "personal",
                    "project_key": "personal:life",
                    "destination": "~/Documents",
                    "criteria": "c",
                    "tokens": [],
                },
            ],
        }
        del taxonomy_obj
        tx = taxonomy.parse_taxonomy(payload)
        node = tx.node("product:personal-docs")
        legal = tc._legal_dispositions(tx, node)
        self.assertIn(constants.FILE_DISPOSITION_PERSONAL_DOCS, legal)

    def setUp(self):
        self.taxonomy = _small_taxonomy()

    def _resolution_for(self, node_id):
        node = self.taxonomy.node(node_id) if node_id else None
        depth = node.depth if node else 0
        tree_path = ()
        return tc.TaxonomyResolution(node_id, tree_path, depth, 0.9, (), (), "selected")

    def test_every_node_kind_flag_combination_is_legal(self):
        node_ids = [
            None,
            "area:homelab",
            "product:homelab",
            "leaf:repo:a/homelab",
            "product:solo",
        ]
        levels = (0.1, 0.5, 0.9)
        for (
            node_id,
            kind,
            backup,
            issue_list,
            evidence,
            private,
            regenerable,
            loss_record,
        ) in itertools.product(
            node_ids, constants.FILE_KINDS, levels, levels, levels, levels, levels, levels
        ):
            flags = {
                constants.FILE_FLAG_BACKUP: backup,
                constants.FILE_FLAG_ISSUE_LIST: issue_list,
                constants.FILE_FLAG_EVIDENCE: evidence,
                constants.FILE_FLAG_PRIVATE: private,
                constants.FILE_FLAG_REGENERABLE: regenerable,
                constants.FILE_FLAG_LOSS_RECORD: loss_record,
            }
            resolution = self._resolution_for(node_id)
            result = tc._decide(resolution, flags, kind, self.taxonomy, "/x")
            node = self.taxonomy.node(node_id) if node_id else None
            legal = tc._legal_dispositions(self.taxonomy, node)
            self.assertIn(
                result.disposition,
                legal + (constants.FILE_DISPOSITION_KEEP,),
                f"{node_id} {kind} {flags} -> {result.disposition} not in {legal}",
            )
            if private >= 0.5 or loss_record >= 0.5:
                self.assertNotEqual(result.disposition, constants.FILE_DISPOSITION_TRASH_CANDIDATE)

    def test_loss_record_resolved_to_its_repo_leaf_routes_to_move_to_repo(self):
        # Tree-mode mirror of classify_file's loss-record guard: a coverage/gap
        # report resolved to its owning repo leaf (a/nas-recovery) is never trashed,
        # and continues down the rule chain to move-to-repo (design section 11).
        flags = {
            constants.FILE_FLAG_BACKUP: 0.85,
            constants.FILE_FLAG_ISSUE_LIST: 0.0,
            constants.FILE_FLAG_EVIDENCE: 0.0,
            constants.FILE_FLAG_PRIVATE: 0.0,
            constants.FILE_FLAG_REGENERABLE: 0.85,
            constants.FILE_FLAG_LOSS_RECORD: 0.85,
        }
        resolution = self._resolution_for("leaf:repo:a/nas-recovery")
        result = tc._decide(resolution, flags, "data-dump", self.taxonomy, "/x")
        self.assertEqual(result.disposition, constants.FILE_DISPOSITION_MOVE_TO_REPO)
        self.assertEqual(result.reason, "loss record blocks trash")
        self.assertTrue(result.important)


class NamedCaseTests(unittest.TestCase):
    """Section 7's RED fixtures against the real taxonomy.json (built by S3, fixed
    by the P2 family-rule repair) -- proves S4/S5 resolve the cases the flat pipeline
    got wrong."""

    @classmethod
    def setUpClass(cls):
        if not REAL_TAXONOMY_PATH.exists():
            raise unittest.SkipTest("taxonomy.json not built")
        cls.taxonomy = taxonomy.load_taxonomy(str(REAL_TAXONOMY_PATH))

    def _classify(self, filename, excerpt, favor):
        observation = _observation(filename, excerpt)

        def ask(request):
            return _answer_everything(request, favor=favor)

        return tc.classify(observation, self.taxonomy, ask)

    def test_nas_rebuild_goal_resolves_under_homelab_not_personal(self):
        result = self._classify(
            "NAS-Rebuild-GOAL.md",
            "Rebuild the homelab NAS with gorillabank and docker compose.",
            favor="homelab",
        )
        self.assertTrue(result.tree_path)
        self.assertEqual(result.tree_path[0], "area:homelab")
        self.assertNotIn("personal", result.tree_path[0])

    def test_rapidsign_attorney_brief_resolves_to_rapidsign_product_or_deeper(self):
        result = self._classify(
            "RapidSign-CIP-attorney-brief.md",
            "This brief discusses RapidSign e-signature compliance for CIP.",
            favor="rapidsign",
        )
        self.assertTrue(result.tree_path)
        self.assertTrue(any("rapidsign" in node for node in result.tree_path))
        self.assertNotEqual(result.file.reason, "disposition illegal for node")

    def test_zbbio_readable_resolves_to_personal_docs(self):
        result = self._classify(
            "ZBbio-readable.md", "Zach Bornheimer biography draft for career use.", favor="personal"
        )
        self.assertTrue(result.tree_path)
        self.assertTrue(
            any(node.startswith("area:personal-life") for node in result.tree_path)
            or any(node == "product:personal-docs" for node in result.tree_path)
        )


if __name__ == "__main__":
    unittest.main()
