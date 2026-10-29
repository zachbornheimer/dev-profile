"""Offline real-artifact proof and fail-closed tampering regression."""

import asyncio
import json
from pathlib import Path

import pytest

from learnings.edges import Files
from learnings.proof import DEFAULT_REPORT, prove


class AlteredFiles(Files):
    def __init__(self, fault: str) -> None:
        self.fault = fault

    def read(self, path: Path) -> str:
        raw = super().read(path)
        if self.fault == "missing-phase" and path.name == "003-verify-response.json":
            raise FileNotFoundError("fixture missing saved phase")
        if path == DEFAULT_REPORT:
            report = json.loads(raw)
            window = report["windows"][0]
            if self.fault == "quote":
                window["observations"][0]["candidate"]["evidence"][0]["quote"] = (
                    "invented quote"
                )
            elif self.fault == "disposition":
                window["observations"][0]["status"] = "review-candidate"
            elif self.fault == "count":
                report["window_count"] = 9
            elif self.fault == "schema":
                report["status"] = "failed"
            return json.dumps(report)
        return raw


def test_real_completed_artifact_offline() -> None:
    result = asyncio.run(prove(DEFAULT_REPORT, Files()))
    assert result["status"] == "completed"
    assert result["accepted_rules"] == []
    assert result["dimension_coverage"] == dict.fromkeys(
        (
            "satisfaction",
            "quality",
            "communication",
            "prompt_act",
            "task_family",
            "goal",
            "decision",
            "lesson",
            "contradiction",
        ),
        "unknown",
    )


@pytest.mark.parametrize(
    "fault", ["quote", "disposition", "count", "schema", "missing-phase"]
)
def test_proof_rejects_corrupt_artifacts(fault: str) -> None:
    with pytest.raises((ValueError, OSError)):
        asyncio.run(prove(DEFAULT_REPORT, AlteredFiles(fault)))
