"""Unit tests for the taxonomy builder (section 7, item 1 of
/tmp/organize/taxonomy-design.md) plus a snapshot test on the real catalog."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_taxonomy import DEFAULT_DATA_DIR, build_taxonomy, load_inputs
from taxonomy_rules import BuildInputs, build_nodes

OVERRIDES = {
    "org_areas": {
        "Software-Automation-Holdings-LLC": {"area": "area:insurance-software", "why": "t"},
    },
    "area_labels": {
        "area:insurance-software": "Insurance Software",
        "area:personal-life": "Personal Life",
        "area:ventures": "Ventures",
    },
    "repo_area": {},
    "product_merge": [],
    "linear_area": {},
    "criteria": {},
}


def _repo(full_name, keywords, *, archived=False, pushed_at="2026-01-01T00:00:00Z", local_path="/x", language="Go"):
    return {
        "full_name": full_name,
        "description_proposed": f"{full_name} test fixture repo.",
        "description_current": full_name,
        "language": language,
        "pushed_at": pushed_at,
        "archived": archived,
        "local_path": None if archived else local_path,
        "keywords": keywords,
    }


def _inputs(repos, linear_projects=None, personal_areas=None, overrides=None):
    return BuildInputs(
        repos=repos,
        linear_projects=linear_projects or [],
        personal_areas=personal_areas or [],
        overrides=overrides or OVERRIDES,
    )


class ProductFamilyTests(unittest.TestCase):
    """P2: repos sharing a rare, area-local keyword group into one product."""

    def test_groups_rapidsign_family(self):
        repos = [
            _repo("Software-Automation-Holdings-LLC/rapidsign", ["rapidsign", "signing", "go", "api"]),
            _repo("Software-Automation-Holdings-LLC/rapidsign-sdk-go", ["rapidsign", "sdk", "go", "generated"]),
            _repo("Software-Automation-Holdings-LLC/rapidsign-sdk-php", ["rapidsign", "sdk", "php", "generated"]),
            # Noise repos sharing "generated" with the two SDKs but not
            # "rapidsign" — without them, "generated" would accidentally
            # out-rank "rapidsign" by having a lower *local* DF than a
            # keyword shared by all three real members; a realistic catalog
            # has enough breadth that a throwaway descriptor like
            # "generated" is common elsewhere too.
            _repo("Software-Automation-Holdings-LLC/noise-tool-a", ["noise-tool-a", "generated", "misc-a", "x"]),
            _repo("Software-Automation-Holdings-LLC/noise-tool-b", ["noise-tool-b", "generated", "misc-b", "y"]),
        ]
        nodes = build_nodes(_inputs(repos))
        by_id = {n["id"]: n for n in nodes}
        leaves = [n for n in nodes if n["type"] == "leaf" and n["parent"] == "product:rapidsign"]
        self.assertIn("product:rapidsign", by_id)
        rapidsign_repos = {r["full_name"] for r in repos if "rapidsign" in r["full_name"]}
        self.assertEqual({leaf["project_key"] for leaf in leaves}, rapidsign_repos)

    def test_groups_zyins_family(self):
        repos = [
            _repo("Software-Automation-Holdings-LLC/zyins", ["zyins", "insurance", "platform-core", "go"]),
            _repo("Software-Automation-Holdings-LLC/zyins-plan-generator", ["zyins", "plan-generator", "go", "pdf"]),
        ]
        nodes = build_nodes(_inputs(repos))
        leaves = [n for n in nodes if n["type"] == "leaf" and n["parent"] == "product:zyins"]
        self.assertEqual(
            {leaf["project_key"] for leaf in leaves},
            {r["full_name"] for r in repos},
        )

    def test_sdk_lang_mirrors_rejoin_parent_by_basename_prefix(self):
        """`<product>-sdk-<lang>` repos whose first keywords are generic
        mirror/build tags ("sdk", "generated", "packagist") must group with
        their parent product by basename prefix, not split three ways on
        whichever tag has the lowest catalog-wide document frequency."""
        repos = [
            _repo("Software-Automation-Holdings-LLC/isa-platform", ["isa", "analytics", "eapp", "bpp"]),
            _repo("Software-Automation-Holdings-LLC/isa-dashboard", ["isa-dashboard", "isa", "bpp", "subscriber"]),
            _repo(
                "Software-Automation-Holdings-LLC/isa-sdk-csharp",
                ["isa-sdk-csharp", "sdk", "csharp", "nuget", "generated", "mirror"],
                language=None,
            ),
            _repo(
                "Software-Automation-Holdings-LLC/isa-sdk-php",
                ["isa-sdk-php", "sdk", "php", "packagist", "generated", "mirror"],
                language="PHP",
            ),
            _repo(
                "Software-Automation-Holdings-LLC/isa-sdk-ts",
                ["isa-sdk-ts", "sdk", "typescript", "npm", "generated", "mirror"],
                language=None,
            ),
        ]
        nodes = build_nodes(_inputs(repos))
        by_id = {n["id"]: n for n in nodes}
        self.assertIn("product:isa", by_id)
        self.assertNotIn("product:generated", by_id)
        self.assertNotIn("product:packagist", by_id)
        leaves = [n for n in nodes if n["type"] == "leaf" and n["parent"] == "product:isa"]
        self.assertEqual(
            {leaf["project_key"] for leaf in leaves},
            {r["full_name"] for r in repos},
        )

    def test_generated_packagist_laravel_never_become_family_keys(self):
        """The generic mirror/framework stoplist blocks these words from
        forming a product even when a repo's own basename prefix does not
        already rescue the grouping."""
        repos = [
            _repo("Software-Automation-Holdings-LLC/noise-a", ["noise-a", "generated", "packagist", "laravel"]),
            _repo("Software-Automation-Holdings-LLC/noise-b", ["noise-b", "generated", "packagist", "laravel"]),
        ]
        nodes = build_nodes(_inputs(repos))
        ids = {n["id"] for n in nodes}
        self.assertNotIn("product:generated", ids)
        self.assertNotIn("product:packagist", ids)
        self.assertNotIn("product:laravel", ids)

    def test_family_max_df_rejects_overcommon_keyword(self):
        """A keyword shared catalog-wide by more than FAMILY_MAX_DF repos
        (e.g. "wordpress") must not become a family key."""
        repos = [
            _repo(f"Software-Automation-Holdings-LLC/wp-{i}", ["wordpress", f"wp-{i}", "php", "plugin"])
            for i in range(14)
        ]
        nodes = build_nodes(_inputs(repos))
        self.assertNotIn("product:wordpress", {n["id"] for n in nodes})


class ArchivedFoldTests(unittest.TestCase):
    """P3: an archived repo is never a leaf when a live sibling exists."""

    def test_bpp_ui_archived_folds_as_alias_under_live_bpp_leaf(self):
        repos = [
            _repo("Software-Automation-Holdings-LLC/bpp-online", ["bpp", "web-app", "react", "billing"]),
            _repo(
                "Software-Automation-Holdings-LLC/bpp-ui",
                ["bpp", "ui-kit", "react", "legacy"],
                archived=True,
            ),
        ]
        nodes = build_nodes(_inputs(repos))
        live_leaf = next(
            n for n in nodes
            if n["type"] == "leaf" and n["project_key"] == "Software-Automation-Holdings-LLC/bpp-online"
        )
        self.assertIn("Software-Automation-Holdings-LLC/bpp-ui", live_leaf["aliases"])
        archived_ids = {
            n["project_key"] for n in nodes if n["type"] == "leaf" and n.get("archived")
        }
        self.assertNotIn("Software-Automation-Holdings-LLC/bpp-ui", archived_ids)

    def test_archived_repo_never_a_leaf_with_move_to_repo_legal(self):
        """No leaf is both `archived` and carries a `local_path` a mover
        could target — the two are mutually exclusive by construction."""
        repos = [
            _repo("zachbornheimer/only-archived", ["only-archived", "tool"], archived=True),
        ]
        nodes = build_nodes(_inputs(repos, overrides={
            **OVERRIDES,
            "org_areas": {"zachbornheimer": {"area": "area:insurance-software", "why": "t"}},
        }))
        leaf = next(n for n in nodes if n["type"] == "leaf")
        self.assertTrue(leaf["archived"])
        self.assertIsNone(leaf.get("local_path"))


class LinearAttachTests(unittest.TestCase):
    """P4: Linear projects attach to the product their tokens identify."""

    def _nodes(self, extra_repos=None):
        repos = [
            _repo("ZAB-AI-LLC/book-bestie", ["book-bestie", "react-native", "expo", "book-tracking"]),
            _repo("zachbornheimer/portal-builder", ["portal-builder", "dragongate", "wordpress", "forms"]),
        ] + (extra_repos or [])
        linear_projects = [
            {"name": "Book Bestie Launch", "id": "P-1"},
            {"name": "DragonGate Portals", "id": "P-2"},
            {"name": "Hypeddit Exit — Music Landing + Meta Tracking", "id": "P-3"},
        ]
        overrides = {
            **OVERRIDES,
            "org_areas": {
                "ZAB-AI-LLC": {"area": "area:zab-ai", "why": "t"},
                "zachbornheimer": {"area": "area:personal-software", "why": "t"},
            },
            "area_labels": {
                "area:zab-ai": "ZAB AI",
                "area:personal-software": "Personal Software",
                "area:ventures": "Ventures",
            },
        }
        return build_nodes(_inputs(repos, linear_projects, overrides=overrides))

    def test_book_bestie_launch_attaches_to_book_bestie(self):
        nodes = self._nodes()
        leaf = next(n for n in nodes if n.get("project_key") == "linear:Book Bestie Launch")
        self.assertEqual(leaf["parent"], "product:book-bestie")

    def test_dragongate_portals_attaches_via_keyword_dragongate(self):
        nodes = self._nodes()
        leaf = next(n for n in nodes if n.get("project_key") == "linear:DragonGate Portals")
        self.assertEqual(leaf["parent"], "product:portal-builder")

    def test_hypeddit_exit_goes_to_ventures_unattached(self):
        """A buried, generic keyword fragment ("tracking", from
        book-bestie's "book-tracking" keyword) must not falsely connect an
        unrelated Linear project — Hypeddit has no real product match."""
        nodes = self._nodes()
        leaf = next(n for n in nodes if n.get("project_key") == "linear:Hypeddit Exit — Music Landing + Meta Tracking")
        product = next(n for n in nodes if n["id"] == leaf["parent"])
        self.assertEqual(product["parent"], "area:ventures")


class VersionHashTests(unittest.TestCase):
    def test_version_hash_is_stable_and_changes_with_one_byte(self):
        data_dir = DEFAULT_DATA_DIR
        _, meta_a = load_inputs(data_dir, Path("/nonexistent"))
        _, meta_b = load_inputs(data_dir, Path("/nonexistent"))
        self.assertEqual(meta_a["version_hash"], meta_b["version_hash"])

        catalog_path = data_dir / "repo-catalog.json"
        original = catalog_path.read_bytes()
        try:
            mutated = json.loads(original)
            mutated["generated_at"] = "1970-01-01T00:00:00Z"
            catalog_path.write_text(json.dumps(mutated))
            _, meta_changed = load_inputs(data_dir, Path("/nonexistent"))
            self.assertNotEqual(meta_a["version_hash"], meta_changed["version_hash"])
        finally:
            catalog_path.write_bytes(original)


class RealCatalogSnapshotTests(unittest.TestCase):
    """Structural guarantees on the real repo-catalog.json (no Developer-clone
    lookup: developer_root points nowhere, so local_path is unaffected)."""

    @classmethod
    def setUpClass(cls):
        cls.document = build_taxonomy(DEFAULT_DATA_DIR, Path("/nonexistent"))
        cls.nodes = cls.document["nodes"]
        cls.by_id = {n["id"]: n for n in cls.nodes}
        catalog = json.loads((DEFAULT_DATA_DIR / "repo-catalog.json").read_text())
        cls.live_repos = [r for r in catalog["repos"] if not r.get("archived")]

    def test_area_count_at_most_ten(self):
        areas = [n for n in self.nodes if n["depth"] == 1]
        self.assertLessEqual(len(areas), 10)

    def test_every_live_repo_placed_exactly_once(self):
        leaf_project_keys = [
            n["project_key"] for n in self.nodes if n["type"] == "leaf" and n["leaf_kind"] == "repo"
        ]
        self.assertEqual(len(leaf_project_keys), len(set(leaf_project_keys)))
        placed = set(leaf_project_keys)
        missing = [r["full_name"] for r in self.live_repos if r["full_name"] not in placed]
        self.assertEqual(missing, [])

    def test_every_parent_exists_and_depth_is_consistent(self):
        for node in self.nodes:
            if node["parent"] is not None:
                self.assertIn(node["parent"], self.by_id, node["id"])
                self.assertEqual(self.by_id[node["parent"]]["depth"], node["depth"] - 1)

    def test_every_non_leaf_has_at_least_one_child(self):
        children = {n["parent"] for n in self.nodes if n["parent"]}
        for node in self.nodes:
            if node["type"] != "leaf":
                self.assertIn(node["id"], children, node["id"])


if __name__ == "__main__":
    unittest.main()
