"""Regression contracts for native metadata and source window identity."""

import argparse
import asyncio
import json
from pathlib import Path

from learnings.cli import execute
from learnings.edges import Files
from learnings.models import Message
from learnings.transcript import native_messages, windows


def test_all_synthetic_range_fails_without_inference() -> None:
    saved: dict[str, object] = {}

    class MemoryFiles(Files):
        def read(self, path: Path) -> str:
            return json.dumps(
                [
                    Message(
                        id="hook",
                        session="s",
                        source="s.json",
                        line=1,
                        date=None,
                        role="user",
                        text="Approved",
                        synthetic=True,
                    ).model_dump()
                ]
            )

        def write(self, path: Path, data: object) -> None:
            saved[path.name] = data

    args = argparse.Namespace(
        baseline=False,
        source="s.json",
        start_line=1,
        end_line=None,
        window_chars=100,
        overlap_chars=10,
        out=Path("unused"),
    )
    assert asyncio.run(execute(args, MemoryFiles())) == 1
    report = saved["report.json"]
    assert isinstance(report, dict)
    assert report["status"] == "failed"
    assert "no eligible evidence" in report["error"]
    assert list(saved) == ["report.json"]


def test_native_metadata_marks_synthetic() -> None:
    raw = json.dumps({"role": "user", "content": "Approved", "synthetic": True})
    parsed = native_messages(raw, Path("session.jsonl"))
    assert parsed[0].synthetic
    assert windows(parsed, 100, 10) == []


def test_native_metadata_preserved() -> None:
    raw = json.dumps(
        {
            "role": "user",
            "content": "a  b\nc",
            "uuid": "u",
            "sessionId": "s",
            "timestamp": "2026-10-10T00:00:00Z",
        }
    )
    parsed = native_messages("\n" + raw, Path("session.jsonl"))
    assert parsed[0].line == 2
    assert parsed[0].date == "2026-10-10T00:00:00Z"
    assert parsed[0].id == "u:0"
    assert parsed[0].session == "s"
    assert parsed[0].text == "a  b\nc"


def test_windows_preserve_bounded_overlap_and_metadata() -> None:
    messages = [
        Message(
            id=str(i),
            session="s",
            source="s.json",
            line=i + 1,
            date=None,
            role="user",
            text=str(i) * 3,
        )
        for i in range(5)
    ]
    chunks = windows(messages, 9, 3)
    assert [[m.id for m in chunk] for chunk in chunks] == [["0", "1", "2"], ["2", "3", "4"]]
    assert all(sum(len(m.text) for m in chunk) <= 9 for chunk in chunks)
    assert chunks[1][0] == messages[2]
