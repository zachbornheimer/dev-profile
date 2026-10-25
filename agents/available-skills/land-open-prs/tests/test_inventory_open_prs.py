from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "inventory-open-prs.py"
FAKE_GHX = ROOT / "tests" / "support" / "fake-ghx.py"
REPO = "acme/widgets"
TOP_KEYS = {"repo", "defaultBranch", "prs", "inventoryComplete", "openPrCount"}
PR_KEYS = {
    "number",
    "title",
    "body",
    "url",
    "author",
    "isDraft",
    "baseRefName",
    "headRefName",
    "mergeable",
    "mergeStateStatus",
    "reviewDecision",
    "additions",
    "deletions",
    "changedFiles",
    "labels",
    "ageDays",
    "staleDays",
    "paths",
    "pathsComplete",
    "pathCount",
}


class PublicCommand:
    def __init__(self, scenario: str = "complete") -> None:
        self.temporary = tempfile.TemporaryDirectory()
        temporary = Path(self.temporary.name)
        self.log = temporary / "calls.jsonl"
        binary = temporary / "bin" / "ghx"
        binary.parent.mkdir()
        shutil.copyfile(FAKE_GHX, binary)
        binary.chmod(0o755)
        self.environment = os.environ.copy()
        self.environment.update(
            {
                "PATH": f"{binary.parent}{os.pathsep}{self.environment['PATH']}",
                "FAKE_GHX_SCENARIO": scenario,
                "FAKE_GHX_LOG": str(self.log),
                "UV_CACHE_DIR": str(temporary / "uv-cache"),
            }
        )

    def run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=ROOT,
            env=self.environment,
            text=True,
            capture_output=True,
            check=False,
        )

    def calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def close(self) -> None:
        self.temporary.cleanup()


class InventoryOpenPullRequestsTests(unittest.TestCase):
    def fixture(self, scenario: str = "complete") -> PublicCommand:
        fixture = PublicCommand(scenario)
        self.addCleanup(fixture.close)
        return fixture

    def test_direct_command_inventories_all_pr_and_file_pages(self) -> None:
        fixture = self.fixture()

        result = fixture.run([str(SCRIPT), REPO])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        output = json.loads(result.stdout)
        self.assertEqual(set(output), TOP_KEYS)
        self.assertEqual(output["repo"], REPO)
        self.assertEqual(output["defaultBranch"], "main")
        self.assertIs(output["inventoryComplete"], True)
        self.assertEqual(output["openPrCount"], 101)
        self.assertEqual(len(output["prs"]), 101)
        self.assertEqual(set(output["prs"][0]), PR_KEYS)
        first = output["prs"][0]
        self.assertIs(first["pathsComplete"], True)
        self.assertEqual(first["pathCount"], 101)
        self.assertEqual(first["changedFiles"], 101)
        self.assertEqual(first["paths"][0], "src/pr-1/file-000.txt")
        self.assertEqual(first["paths"][-1], "src/pr-1/file-100.txt")

        calls = fixture.calls()
        paged = [call for call in calls if call[:1] == ["api"] and "--paginate" in call]
        self.assertTrue(paged)
        self.assertTrue(all("--slurp" in call for call in paged))
        self.assertIn(
            f"repos/{REPO}/pulls?state=open&per_page=100",
            [call[-1] for call in paged],
        )
        self.assertIn(
            f"repos/{REPO}/pulls/1/files?per_page=100",
            [call[-1] for call in paged],
        )
        open_endpoint = f"repos/{REPO}/pulls?state=open&per_page=100"
        self.assertEqual(sum(call[-1] == open_endpoint for call in paged), 2)
        detail_calls = [call for call in calls if call[:2] == ["pr", "view"]]
        self.assertEqual(len(detail_calls), 101)
        self.assertTrue(all("--json" in call for call in detail_calls))

    def test_uv_run_public_form_uses_the_same_schema(self) -> None:
        fixture = self.fixture()

        result = fixture.run(["uv", "run", str(SCRIPT), REPO])

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(set(output), TOP_KEYS)
        self.assertEqual(output["openPrCount"], 101)
        self.assertEqual(set(output["prs"][-1]), PR_KEYS)

    def test_incomplete_file_inventory_fails_without_stdout(self) -> None:
        fixture = self.fixture("incomplete-files")

        result = fixture.run([str(SCRIPT), REPO])

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("PR #1 file inventory", result.stderr)
        self.assertIn("expected 101, got 100", result.stderr)

    def test_shifted_open_pr_cohort_fails_without_stdout(self) -> None:
        fixture = self.fixture("shifted-cohort")

        result = fixture.run([str(SCRIPT), REPO])

        self.assertNotEqual(
            result.returncode,
            0,
            "a page-shifted cohort must not be reported as inventoryComplete",
        )
        self.assertEqual(result.stdout, "")
        self.assertIn("open PR cohort changed", result.stderr)

    def test_malformed_file_record_fails_without_stdout(self) -> None:
        fixture = self.fixture("malformed-files")

        result = fixture.run([str(SCRIPT), REPO])

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("PR #1 file path", result.stderr)
        self.assertIn("expected text", result.stderr)

    def test_duplicate_file_path_fails_without_stdout(self) -> None:
        fixture = self.fixture("duplicate-files")

        result = fixture.run([str(SCRIPT), REPO])

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("duplicate path", result.stderr)

    def test_malformed_json_fails_without_stdout(self) -> None:
        fixture = self.fixture("malformed-json")

        result = fixture.run([str(SCRIPT), REPO])

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("malformed JSON from open PR inventory", result.stderr)

    def test_provider_command_failure_has_context_and_no_stdout(self) -> None:
        fixture = self.fixture("command-failure")

        result = fixture.run([str(SCRIPT), REPO])

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("ghx command failed", result.stderr)
        self.assertIn("fixture provider failure", result.stderr)

    def test_missing_ghx_fails_with_context_and_no_stdout(self) -> None:
        fixture = self.fixture()
        environment = fixture.environment.copy()
        environment["PATH"] = "/usr/bin:/bin"
        result = subprocess.run(
            [sys.executable, str(SCRIPT), REPO],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("ghx is required", result.stderr)


if __name__ == "__main__":
    unittest.main()
