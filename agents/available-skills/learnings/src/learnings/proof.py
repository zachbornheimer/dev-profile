"""Offline replay proof against real saved local phases and original source."""

import argparse
import asyncio
import json
from pathlib import Path

from pydantic import TypeAdapter

from learnings.consolidation import GENERATOR, Recovery
from learnings.edges import Calls, Files
from learnings.models import Extraction, Message
from learnings.pipeline import JEV, Settings, run_window
from learnings.report import CompletedReport, coverage
from learnings.transcript import load

DEFAULT_REPORT = Path.home() / (
    ".hermes/profiles/zach/cache/scratch/learnings/dev-profile-2/report.json"
)


class Replay:
    def __init__(self, directory: Path, files: Files) -> None:
        self.directory = directory
        self.files = files
        self.count = 0
        self.elapsed = 0.0

    def artifact(self, index: int, phase: str, kind: str) -> dict[str, object]:
        path = self.directory / f"{index:03d}-{phase}-{kind}.json"
        data: object = json.loads(self.files.read(path))
        if not isinstance(data, dict):
            raise ValueError(f"invalid phase artifact: {path.name}")
        return data

    async def post(self, path: str, payload: dict[str, object]) -> object:
        self.count += 1
        if path == "/v1/chat/completions":
            phase = "consolidate"
            expected_model = GENERATOR
        elif isinstance(payload.get("state"), list):
            phase = "prune"
            expected_model = JEV
        else:
            phase = "verify"
            expected_model = JEV
        request = self.artifact(self.count, phase, "request")
        if request != payload or request.get("model") != expected_model:
            raise ValueError(f"saved request differs from replay: {self.count}-{phase}")
        response = self.artifact(self.count, phase, "response")
        seconds = response.get("seconds")
        if not isinstance(seconds, (int, float)) or seconds < 0:
            raise ValueError(f"missing phase timing: {self.count}-{phase}")
        self.elapsed += seconds
        return response["raw"]

    def check_validation(self, name: str, data: object) -> None:
        if name.endswith("-validation"):
            saved: object = json.loads(self.files.read(self.directory / f"{name}.json"))
            if data != saved:
                raise ValueError("saved validation differs from replay")


def source_check(messages: list[Message], originals: list[Message]) -> None:
    for message in messages:
        matches = [original for original in originals if original.id == message.id]
        if len(matches) != 1:
            raise ValueError(f"ambiguous or missing source message: {message.id}")
        original = matches[0]
        if (
            message.text not in original.text
            or original.synthetic
            or original.role == "system"
            or message.synthetic
            or message.model_dump(exclude={"text"}) != original.model_dump(exclude={"text"})
        ):
            raise ValueError(f"source text/metadata mismatch: {message.id}")


async def prove(path: Path, files: Files) -> dict[str, object]:
    report = CompletedReport.model_validate_json(files.read(path))
    if report.window_count != len(report.windows):
        raise ValueError("report window count mismatch")
    originals = load(Path(report.source), files)
    replay = Replay(path.parent, files)
    calls = Calls(replay, replay.check_validation, lambda: replay.elapsed)
    for index, window in enumerate(report.windows):
        first_phase = "consolidate" if report.mode == "baseline" else "prune"
        first = replay.artifact(replay.count + 1, first_phase, "request")
        if first_phase == "prune":
            raw_messages = first["state"]
            generation = replay.artifact(replay.count + 2, "consolidate", "request")
        else:
            generation = first
            chat = TypeAdapter(list[dict[str, str]]).validate_python(first["messages"])
            raw_messages = json.loads(chat[-1]["content"])
        messages = TypeAdapter(list[Message]).validate_python(raw_messages)
        source_check(messages, originals)
        start, end = report.line_range
        if any(m.line < start or (end is not None and m.line > end) for m in messages):
            raise ValueError("window outside selected source range")
        if not {m.session for m in messages} <= set(report.session_ids):
            raise ValueError("window session mismatch")
        settings = Settings(
            legacy=report.recovery is None,
            recovery=Recovery(**report.recovery) if report.recovery else Recovery(),
            max_tokens=TypeAdapter(int).validate_python(generation["max_tokens"]),
            baseline=report.mode == "baseline",
            instructions=TypeAdapter(list[dict[str, str]])
            .validate_python(generation["messages"])[0]["content"]
            .split("\nSCHEMA:\n", 1)[0],
        )
        if settings.legacy:
            response_format = TypeAdapter(dict[str, object]).validate_python(
                generation["response_format"]
            )
            schema = TypeAdapter(dict[str, object]).validate_python(response_format["json_schema"])[
                "schema"
            ]
            if schema != Extraction.model_json_schema():
                raise ValueError("unknown historical generation schema")
        result = await run_window(messages, calls, settings)
        result["window"] = index
        result["source_messages"] = [m.model_dump(exclude={"text"}) for m in messages]
        if result != window.model_dump():
            raise ValueError(f"report does not match real phase replay: window {index}")
    artifacts = files.locate(path.parent, "*-request.json")
    if len(artifacts) != replay.count:
        raise ValueError("unconsumed phase artifacts")
    if report.calls is not None:
        if len(report.calls) != len(calls.records):
            raise ValueError("report call count mismatch")
        for expected, actual in zip(report.calls, calls.records, strict=True):
            if (
                expected.keys() != actual.keys()
                or any(expected[key] != actual[key] for key in expected if key != "seconds")
                or abs(float(str(expected["seconds"])) - float(str(actual["seconds"]))) > 1e-9
            ):
                raise ValueError("report call timing/validation mismatch")
    result = report.model_dump()
    result["dimension_coverage"] = coverage(report.windows)
    result["proof"] = {
        "mode": "offline saved-phase replay; no inference",
        "phase_calls": replay.count,
        "limits": "Artifact consistency, not model authenticity or semantic truth.",
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", nargs="?", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--out", type=Path, help="Optional derived full report; never overwrites input"
    )
    args = parser.parse_args()
    try:
        result = asyncio.run(prove(args.report, Files()))
        if args.out:
            if args.out.exists() or args.out.resolve() == args.report.resolve():
                raise ValueError("proof output must be a new path distinct from input")
            Files().write(args.out, result)
    except (OSError, ValueError, KeyError) as exc:
        raise SystemExit(f"proof failed: {exc}") from exc
    print(
        json.dumps(
            {
                "status": "verified",
                "proof": result["proof"],
                "dimension_coverage": result["dimension_coverage"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
