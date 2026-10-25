"""Run logs, percentiles, and the p95 timeout decision for one hook.

Observation (hyperfine samples) is assembled by the CLI. This module owns
the closed report shape and the pure decision: p95 of the run logs, then
ceil to a whole-second Claude hook timeout.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

P95 = 95.0
P99 = 99.0
MINIMUM_TIMEOUT_SECONDS = 1


@dataclass(frozen=True, slots=True)
class RunLog:
    """One hyperfine sample: wall time and the process exit status."""

    seconds: float
    exit_code: int

    def to_json(self) -> dict[str, float | int]:
        return {"seconds": self.seconds, "exit_code": self.exit_code}


@dataclass(frozen=True, slots=True)
class SpeedObservation:
    """Facts hyperfine reported for one hook command."""

    path: str
    command: tuple[str, ...]
    payload: str | None
    runs: int
    warmup: int
    mean_seconds: float
    stddev_seconds: float
    median_seconds: float
    min_seconds: float
    max_seconds: float
    samples: tuple[RunLog, ...]


@dataclass(frozen=True, slots=True)
class TimeoutReport:
    """Speed observation plus the p95 timeout decision."""

    observation: SpeedObservation
    p95_seconds: float
    p99_seconds: float
    suggested_timeout_seconds: int

    def to_json(self) -> dict[str, object]:
        observed = self.observation
        return {
            "path": observed.path,
            "command": list(observed.command),
            "payload": observed.payload,
            "runs": observed.runs,
            "warmup": observed.warmup,
            "mean_seconds": observed.mean_seconds,
            "stddev_seconds": observed.stddev_seconds,
            "median_seconds": observed.median_seconds,
            "min_seconds": observed.min_seconds,
            "max_seconds": observed.max_seconds,
            "p95_seconds": self.p95_seconds,
            "p99_seconds": self.p99_seconds,
            "suggested_timeout_seconds": self.suggested_timeout_seconds,
            "runs_log": [sample.to_json() for sample in observed.samples],
        }


def percentile(sorted_values: tuple[float, ...], p: float) -> float:
    """Linear-interpolation percentile of a non-empty sorted series.

    ``p`` is in 0..100. One sample returns that sample.
    """
    if not sorted_values:
        raise ValueError("percentile requires at least one sample")
    if p < 0 or p > 100:
        raise ValueError(f"percentile {p} is outside 0..100")
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (p / 100.0) * (len(sorted_values) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return sorted_values[low]
    weight = rank - low
    return sorted_values[low] * (1.0 - weight) + sorted_values[high] * weight


def suggested_timeout_seconds(p95_seconds: float) -> int:
    """Claude hook timeout: whole seconds, ceil of p95, never below 1."""
    if p95_seconds < 0:
        raise ValueError(f"p95 seconds cannot be negative: {p95_seconds}")
    return max(MINIMUM_TIMEOUT_SECONDS, math.ceil(p95_seconds))


def decide_timeout(observation: SpeedObservation) -> TimeoutReport:
    """p95/p99 of the run logs, then the suggested whole-second timeout."""
    if not observation.samples:
        raise ValueError("observation has no run logs")
    times = tuple(sorted(sample.seconds for sample in observation.samples))
    p95_seconds = percentile(times, P95)
    p99_seconds = percentile(times, P99)
    return TimeoutReport(
        observation=observation,
        p95_seconds=p95_seconds,
        p99_seconds=p99_seconds,
        suggested_timeout_seconds=suggested_timeout_seconds(p95_seconds),
    )


def observation_from_hyperfine(
    path: str,
    command: tuple[str, ...],
    payload_path: str | None,
    runs: int,
    warmup: int,
    payload: dict[str, object],
) -> SpeedObservation:
    """Translate one hyperfine --export-json result object into an observation.

    Hyperfine 1.x reports ``times`` and ``exit_codes``. Hyperfine 2.0 reports
    ``measurements`` and ``summary.time_wall_clock``.
    """
    times, exit_codes = _hyperfine_times_and_exit_codes(payload)
    if not isinstance(times, list) or not times:
        raise ValueError("hyperfine JSON is missing a non-empty times list")
    if not isinstance(exit_codes, list) or len(exit_codes) != len(times):
        raise ValueError("hyperfine JSON times and exit_codes must be the same length")
    samples = tuple(
        RunLog(seconds=float(seconds), exit_code=int(code))
        for seconds, code in zip(times, exit_codes, strict=True)
    )
    summary = _hyperfine_clock_summary(payload)
    return SpeedObservation(
        path=path,
        command=command,
        payload=payload_path,
        runs=runs,
        warmup=warmup,
        mean_seconds=_clock_seconds(summary, "mean"),
        stddev_seconds=_clock_seconds(summary, "stddev"),
        median_seconds=_clock_seconds(summary, "median"),
        min_seconds=_clock_seconds(summary, "min"),
        max_seconds=_clock_seconds(summary, "max"),
        samples=samples,
    )


def _hyperfine_times_and_exit_codes(payload: dict[str, object]) -> tuple[object, object]:
    """Sample wall times and exit codes from a 1.x or 2.0 result object."""
    if "times" in payload or "exit_codes" in payload:
        return payload.get("times"), payload.get("exit_codes")
    measurements = payload.get("measurements")
    if not isinstance(measurements, list):
        return None, None
    times: list[object] = []
    exit_codes: list[object] = []
    for sample in measurements:
        if not isinstance(sample, dict):
            times.append(None)
            continue
        wall = sample.get("time_wall_clock")
        value = wall.get("value") if isinstance(wall, dict) else None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            times.append(value)
        if "exit_code" in sample:
            exit_codes.append(sample["exit_code"])
    return times, exit_codes


def _hyperfine_clock_summary(payload: dict[str, object]) -> dict[str, object]:
    """1.x stats sit on the result. 2.0 stats sit on summary.time_wall_clock."""
    if "times" in payload or "exit_codes" in payload:
        return payload
    summary = payload.get("summary")
    if isinstance(summary, dict):
        clock = summary.get("time_wall_clock")
        if isinstance(clock, dict):
            return clock
    return {}


def _clock_seconds(summary: dict[str, object], name: str) -> float:
    value = summary.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"hyperfine JSON {name} must be a number, got {type(value).__name__}")
    return float(value)
