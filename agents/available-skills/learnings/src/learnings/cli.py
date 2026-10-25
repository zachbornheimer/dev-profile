"""Operator CLI. Sequential bounded calls, fail-closed run report."""

import argparse
import asyncio
from dataclasses import asdict
from pathlib import Path

import httpx
from pydantic import ValidationError

from learnings.consolidation import Recovery
from learnings.edges import Calls, Files, LocalTransport, sanitized
from learnings.pipeline import Settings, run_window
from learnings.report import WindowReport, coverage
from learnings.transcript import load, resolve, windows

DEFAULT_LIMIT = 8000
DEFAULT_OVERLAP = 2000
DEFAULT_TIMEOUT = 90.0


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="Native Claude/Hermes JSONL, normalized JSON, or claude:id")
    parser.add_argument("--out", type=Path, required=True, help="New private artifact directory")
    parser.add_argument("--window-chars", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--overlap-chars", type=int, default=DEFAULT_OVERLAP)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--max-tokens", type=int, default=1800)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--token-cap", type=int, default=3200)
    parser.add_argument("--token-step", type=int, default=700)
    parser.add_argument("--start-line", type=int, default=1)
    parser.add_argument("--end-line", type=int)
    parser.add_argument("--baseline", action="store_true")
    return parser.parse_args()


async def execute(args: argparse.Namespace, files: Files) -> int:
    report: dict[str, object] = {
        "status": "failed",
        "accepted_rules": [],
        "sampled": True,
        "probability_note": "Jev decisions, not calibrated satisfaction probabilities.",
        "thresholds": "experimental: pruning 0.5; support/explicit 0.85; usefulness 0.8",
        "mode": "baseline" if args.baseline else "prune-consolidate-verify",
    }
    reports: list[dict[str, object]] = []
    calls: Calls | None = None
    try:
        path = resolve(args.source, files, Path.home())
        all_messages = load(path, files)
        messages = [
            m
            for m in all_messages
            if m.line >= args.start_line and (args.end_line is None or m.line <= args.end_line)
        ]
        if not messages:
            raise ValueError("selected source range contains no messages")
        if any(sanitized(m.text) != m.text for m in messages):
            raise ValueError("source may contain secrets; select a narrower safe range")
        chunks = windows(messages, args.window_chars, args.overlap_chars)
        if not chunks:
            raise ValueError("selected source range contains no eligible evidence")
        report.update(
            {
                "source": str(path),
                "session_ids": sorted({m.session for m in messages}),
                "line_range": [args.start_line, args.end_line],
                "window_count": len(chunks),
                "excluded_synthetic": sum(m.synthetic for m in messages),
            }
        )
        recovery = Recovery(args.max_attempts, args.token_cap, args.token_step)
        recovery.validate(args.max_tokens)
        report["recovery"] = asdict(recovery)
        settings = Settings(max_tokens=args.max_tokens, baseline=args.baseline, recovery=recovery)
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as client:
            calls = Calls(
                LocalTransport(client, args.timeout),
                lambda name, data: files.write(args.out / f"{name}.json", data),
            )
            for index, chunk in enumerate(chunks):
                result = await run_window(chunk, calls, settings)
                result["window"] = index
                result["source_messages"] = [m.model_dump(exclude={"text"}) for m in chunk]
                reports.append(result)
        report.update(
            {
                "status": "completed",
                "windows": reports,
                "dimension_coverage": coverage([WindowReport.model_validate(w) for w in reports]),
                "cross_window_note": "Independent overlapping candidates; contradictions across "
                "windows require source review, not automatic rule adoption.",
            }
        )
    except (OSError, httpx.HTTPError, ValueError, ValidationError) as exc:
        report.update(
            {
                "error": type(exc).__name__
                if isinstance(exc, (ValidationError, httpx.HTTPError))
                else f"{type(exc).__name__}: {sanitized(str(exc))[:300]}",
                "windows": reports,
                "disposition": "unknown; no accepted rules",
            }
        )
    report["calls"] = calls.records if calls else []
    files.write(args.out / "report.json", report)
    print(f"{report['status']}: {args.out / 'report.json'}")
    return 0 if report["status"] == "completed" else 1


def main() -> None:
    args = arguments()
    if args.out.exists():
        raise SystemExit("--out must be a new directory to prevent stale proof artifacts")
    raise SystemExit(asyncio.run(execute(args, Files())))


if __name__ == "__main__":
    main()
