"""Deterministic saved retry sequence proof, using explicitly fake local responses."""

import asyncio
import json
from pathlib import Path

import pytest
from test_consolidation import Sequence, chat, invalid, valid
from test_contract import message

from learnings.edges import Calls, Files
from learnings.pipeline import Settings, run_window
from learnings.proof import prove
from learnings.report import WindowReport, coverage


class Artifacts(Files):
    def __init__(self) -> None:
        self.data: dict[Path, object] = {}

    def read(self, path: Path) -> str:
        if path not in self.data:
            raise FileNotFoundError(path.name)
        return json.dumps(self.data[path])

    def write(self, path: Path, data: object) -> None:
        self.data[path] = data

    def locate(self, root: Path, pattern: str) -> list[Path]:
        return sorted(path for path in self.data if path.parent == root and path.match(pattern))


def saved_retry() -> Artifacts:
    files = Artifacts()
    root = Path("retry-fixture")
    turns = [message("read skill")]
    files.data[Path("fixture.json")] = [m.model_dump() for m in turns]
    scores = {
        "answers": {
            key: {"type": "noul", "noul": 0.01} for key in ("supported", "useful", "explicit")
        }
    }
    calls = Calls(
        Sequence([invalid("length"), chat(valid()), scores]),
        lambda name, data: files.write(root / f"{name}.json", data),
        lambda: 0.0,
    )
    window = asyncio.run(run_window(turns, calls, Settings(baseline=True)))
    window.update(window=0, source_messages=[m.model_dump(exclude={"text"}) for m in turns])
    files.data[root / "report.json"] = {
        "status": "completed",
        "accepted_rules": [],
        "sampled": True,
        "probability_note": "Explicitly fake responses; regression only",
        "thresholds": "experimental",
        "mode": "baseline",
        "source": "fixture.json",
        "session_ids": ["fixture"],
        "line_range": [1, None],
        "window_count": 1,
        "excluded_synthetic": 0,
        "windows": [window],
        "cross_window_note": "fixture",
        "dimension_coverage": coverage([WindowReport.model_validate(window)]),
        "recovery": {"attempts": 3, "token_cap": 3200, "token_step": 700},
        "calls": calls.records,
    }
    return files


def test_saved_retry_sequence_matches_every_request() -> None:
    result = asyncio.run(prove(Path("retry-fixture/report.json"), saved_retry()))
    assert result["proof"] == {
        "mode": "offline saved-phase replay; no inference",
        "phase_calls": 3,
        "limits": "Artifact consistency, not model authenticity or semantic truth.",
    }


@pytest.mark.parametrize("fault", ["retry-request", "timing", "missing-validation"])
def test_retry_proof_rejects_tampering(fault: str) -> None:
    files = saved_retry()
    root = Path("retry-fixture")
    if fault == "retry-request":
        value = files.data[root / "002-consolidate-request.json"]
        assert isinstance(value, dict)
        value["max_tokens"] = 999
    elif fault == "timing":
        value = files.data[root / "report.json"]
        assert isinstance(value, dict)
        value["calls"][0]["seconds"] = 99
    else:
        del files.data[root / "001-consolidate-validation.json"]
    with pytest.raises((ValueError, OSError)):
        asyncio.run(prove(root / "report.json", files))
