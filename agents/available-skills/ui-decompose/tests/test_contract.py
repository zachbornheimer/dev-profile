"""Contract tests for the deterministic UI decomposition workflow."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate.py"
RENDERER = ROOT / "scripts" / "render.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
DECOMPOSITION = FIXTURES / "valid-decomposition.json"
PASSING_REVIEW = FIXTURES / "passing-review.json"
REQUEST = FIXTURES / "request.txt"


class ContractTests(unittest.TestCase):
    """Verify certification, audit binding, corrections, and rendering."""

    def run_command(self, *args: str) -> subprocess.CompletedProcess[str]:
        """Run a command and capture diagnostics for assertions."""

        return subprocess.run([*args], check=False, capture_output=True, text=True)

    def test_valid_decomposition_certifies(self) -> None:
        result = self.run_command(
            "python3", str(VALIDATOR), "decomposition", str(DECOMPOSITION), "--certify", "--request", str(REQUEST)
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("certified=yes", result.stdout)

    def test_passing_review_is_bound_and_exhaustive(self) -> None:
        result = self.run_command(
            "python3",
            str(VALIDATOR),
            "review",
            str(PASSING_REVIEW),
            "--pass-number",
            "1",
            "--decomposition",
            str(DECOMPOSITION),
            "--request",
            str(REQUEST),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("changeRequested=false", result.stdout)
        self.assertIn("surfaceAudits=1", result.stdout)

    def test_review_rejects_stale_decomposition_digest(self) -> None:
        review = json.loads(PASSING_REVIEW.read_text(encoding="utf-8"))
        review["reviewedArtifacts"]["decompositionSha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "review.json"
            path.write_text(json.dumps(review), encoding="utf-8")
            result = self.run_command(
                "python3",
                str(VALIDATOR),
                "review",
                str(path),
                "--decomposition",
                str(DECOMPOSITION),
                "--request",
                str(REQUEST),
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("digest mismatch", result.stderr)

    def test_review_rejects_incomplete_surface_audit(self) -> None:
        review = json.loads(PASSING_REVIEW.read_text(encoding="utf-8"))
        review["surfaceAudits"][0]["nodeAudits"] = [
            item for item in review["surfaceAudits"][0]["nodeAudits"]
            if item["matchedId"] != "node.button"
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "review.json"
            path.write_text(json.dumps(review), encoding="utf-8")
            result = self.run_command(
                "python3",
                str(VALIDATOR),
                "review",
                str(path),
                "--decomposition",
                str(DECOMPOSITION),
                "--request",
                str(REQUEST),
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("did not independently audit node ids: node.button", result.stderr)

    def test_decomposition_requires_exactly_one_default_surface_state(self) -> None:
        data = json.loads(DECOMPOSITION.read_text(encoding="utf-8"))
        extra = copy.deepcopy(data["states"][0])
        extra["id"] = "state.main.default-2"
        data["states"].append(extra)
        data["coverage"]["stateIds"].append(extra["id"])
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "decomposition.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            result = self.run_command(
                "python3", str(VALIDATOR), "decomposition", str(path), "--certify"
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exactly one default surface state", result.stderr)

    def test_correction_report_must_resolve_every_review_finding(self) -> None:
        before = json.loads(DECOMPOSITION.read_text(encoding="utf-8"))
        request_hash = hashlib.sha256(REQUEST.read_bytes()).hexdigest()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            before_path = temp / "before.json"
            after_path = temp / "after.json"
            review_path = temp / "review.json"
            correction_path = temp / "correction.json"
            before_path.write_text(json.dumps(before, indent=2) + "\n", encoding="utf-8")
            before_hash = hashlib.sha256(before_path.read_bytes()).hexdigest()

            review = {
                "schemaVersion": "1.1",
                "reviewPass": 1,
                "reviewedArtifacts": {
                    "requestSha256": request_hash,
                    "decompositionSha256": before_hash,
                },
                "changeRequested": True,
                "certification": "incomplete",
                "summary": "Heading text evidence needs correction.",
                "sourceFilesInspected": ["example.html"],
                "surfaceAudits": [
                    {
                        "auditKey": "audit.main",
                        "observedName": "Main",
                        "observedType": "page",
                        "matchedSurfaceId": "surface.main",
                        "evidence": [
                            {"kind": "selector", "source": "example.html", "locator": "body"}
                        ],
                        "nodeAudits": [
                            {
                                "auditKey": "audit.node.root",
                                "observedName": "MainPage",
                                "matchedId": "node.root",
                                "evidence": [{"kind": "selector", "source": "example.html", "locator": "body"}],
                            },
                            {
                                "auditKey": "audit.node.heading",
                                "observedName": "Heading",
                                "matchedId": "node.heading",
                                "evidence": [{"kind": "selector", "source": "example.html", "locator": "h1"}],
                            },
                            {
                                "auditKey": "audit.node.button",
                                "observedName": "ActionButton",
                                "matchedId": "node.button",
                                "evidence": [{"kind": "selector", "source": "example.html", "locator": "button"}],
                            },
                        ],
                        "stateAudits": [
                            {
                                "auditKey": "audit.state.default",
                                "observedName": "Default",
                                "matchedId": "state.main.default",
                                "evidence": [{"kind": "selector", "source": "example.html", "locator": "body"}],
                            }
                        ],
                        "interactionAudits": [
                            {
                                "auditKey": "audit.interaction.button",
                                "observedName": "Activate continue",
                                "matchedId": "interaction.button.click",
                                "evidence": [{"kind": "selector", "source": "example.html", "locator": "button"}],
                            }
                        ],
                    }
                ],
                "findings": [
                    {
                        "id": "finding.heading",
                        "severity": "minor",
                        "category": "missing-visible-content",
                        "description": "Heading text differs from source.",
                        "affectedIds": ["node.heading"],
                        "evidence": [
                            {"kind": "selector", "source": "example.html", "locator": "h1"}
                        ],
                        "requiredChanges": [
                            {
                                "operation": "update",
                                "targetId": "node.heading",
                                "instructions": "Correct the heading text from source evidence."
                            }
                        ],
                    }
                ],
            }
            review_path.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")

            after = copy.deepcopy(before)
            after["nodes"][1]["visibleText"] = ["Example corrected"]
            after_path.write_text(json.dumps(after, indent=2) + "\n", encoding="utf-8")
            after_hash = hashlib.sha256(after_path.read_bytes()).hexdigest()

            correction = {
                "schemaVersion": "1.0",
                "reviewPass": 1,
                "baseDecompositionSha256": before_hash,
                "resultDecompositionSha256": after_hash,
                "resolutions": [
                    {
                        "findingId": "finding.heading",
                        "disposition": "applied",
                        "rationale": "Updated the source-observed heading text.",
                        "affectedIds": ["node.heading"],
                        "evidence": [
                            {"kind": "selector", "source": "example.html", "locator": "h1"}
                        ],
                    }
                ],
            }
            correction_path.write_text(
                json.dumps(correction, indent=2) + "\n", encoding="utf-8"
            )

            result = self.run_command(
                "python3",
                str(VALIDATOR),
                "correction",
                str(correction_path),
                "--review",
                str(review_path),
                "--before",
                str(before_path),
                "--after",
                str(after_path),
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS correction", result.stdout)

    def test_renderer_emits_every_surface_and_certification(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "decomposition.md"
            result = self.run_command(
                "python3",
                str(RENDERER),
                str(DECOMPOSITION),
                str(output),
                "--review",
                str(PASSING_REVIEW),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            rendered = output.read_text(encoding="utf-8")
            self.assertIn("## Surface decompositions", rendered)
            self.assertIn("ActionButton", rendered)
            self.assertIn("Activate continue", rendered)
            self.assertIn("## Certification", rendered)
            self.assertIn("COMPLETE", rendered)


if __name__ == "__main__":
    unittest.main()
