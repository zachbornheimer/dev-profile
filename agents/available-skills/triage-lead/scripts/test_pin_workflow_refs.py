# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for pin_workflow_refs.rewrite (pure function, no network/git)."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


def _load_pin_workflow_refs_module():
    module_path = Path(__file__).parent / "pin_workflow_refs.py"
    spec = importlib.util.spec_from_file_location("pin_workflow_refs", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pin_workflow_refs = _load_pin_workflow_refs_module()
rewrite = pin_workflow_refs.rewrite

SOURCE = "Software-Automation-Holdings-LLC/dev-config"
SHA = "a" * 40


class RewriteTests(unittest.TestCase):
    def test_pins_floating_main_ref_and_replaces_trailing_comment(self) -> None:
        text = (
            "      uses: Software-Automation-Holdings-LLC/dev-config/"
            ".github/workflows/ci.yml@main # sprint: tracks main\n"
        )
        rewritten, count = rewrite(text, SOURCE, {"main"}, SHA)
        self.assertEqual(count, 1)
        self.assertEqual(
            rewritten,
            f"      uses: {SOURCE}/.github/workflows/ci.yml@{SHA} # main\n",
        )

    def test_pins_floating_version_ref(self) -> None:
        text = f"    uses: {SOURCE}/.github/workflows/release.yml@v1\n"
        rewritten, count = rewrite(text, SOURCE, {"v1"}, SHA)
        self.assertEqual(count, 1)
        self.assertEqual(
            rewritten,
            f"    uses: {SOURCE}/.github/workflows/release.yml@{SHA} # v1\n",
        )

    def test_leaves_already_pinned_sha_untouched(self) -> None:
        pinned_sha = "b" * 40
        text = f"    uses: {SOURCE}/.github/workflows/ci.yml@{pinned_sha}\n"
        rewritten, count = rewrite(text, SOURCE, {"main"}, SHA)
        self.assertEqual(count, 0)
        self.assertEqual(rewritten, text)

    def test_leaves_unrelated_action_untouched(self) -> None:
        text = "    uses: actions/checkout@v4\n"
        rewritten, count = rewrite(text, SOURCE, {"main", "v4"}, SHA)
        self.assertEqual(count, 0)
        self.assertEqual(rewritten, text)

    def test_leaves_different_owner_repo_untouched(self) -> None:
        text = "    uses: some-other-org/dev-config/.github/workflows/ci.yml@main\n"
        rewritten, count = rewrite(text, SOURCE, {"main"}, SHA)
        self.assertEqual(count, 0)
        self.assertEqual(rewritten, text)

    def test_preserves_indentation(self) -> None:
        text = f"        uses: {SOURCE}/.github/workflows/ci.yml@main\n"
        rewritten, count = rewrite(text, SOURCE, {"main"}, SHA)
        self.assertEqual(count, 1)
        self.assertTrue(rewritten.startswith("        uses: "))

    def test_counts_multiple_replacements_across_lines(self) -> None:
        text = (
            f"    uses: {SOURCE}/.github/workflows/ci.yml@main\n"
            f"    uses: {SOURCE}/.github/workflows/release.yml@main\n"
            "    uses: actions/checkout@v4\n"
        )
        rewritten, count = rewrite(text, SOURCE, {"main"}, SHA)
        self.assertEqual(count, 2)
        self.assertIn(f"@{SHA} # main", rewritten)
        self.assertIn("actions/checkout@v4", rewritten)

    def test_ref_not_in_floating_refs_is_left_untouched(self) -> None:
        text = f"    uses: {SOURCE}/.github/workflows/ci.yml@master\n"
        rewritten, count = rewrite(text, SOURCE, {"main"}, SHA)
        self.assertEqual(count, 0)
        self.assertEqual(rewritten, text)


if __name__ == "__main__":
    unittest.main()
