"""suggested-timeout-for.py: p95 decision plus the public CLI JSON list."""

from __future__ import annotations

import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import hook_path

HOOKS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOOKS_DIR / "lib"))

from suggested_timeout import (
    RunLog,
    SpeedObservation,
    decide_timeout,
    observation_from_hyperfine,
    percentile,
    suggested_timeout_seconds,
)

CLI = hook_path("suggested-timeout-for.py")


def test_percentile_is_linear_interpolation_of_sorted_samples() -> None:
    series = (1.0, 2.0, 3.0, 4.0, 5.0)
    assert percentile(series, 0) == 1.0
    assert percentile(series, 100) == 5.0
    assert percentile(series, 50) == 3.0
    assert percentile(series, 95) == pytest.approx(4.8)


def test_percentile_of_one_sample_is_that_sample() -> None:
    assert percentile((0.04,), 95) == 0.04


def test_percentile_rejects_empty_and_out_of_range() -> None:
    with pytest.raises(ValueError, match="at least one sample"):
        percentile((), 95)
    with pytest.raises(ValueError, match="outside 0..100"):
        percentile((1.0,), 101)


def test_suggested_timeout_ceils_p95_to_whole_seconds_with_floor_one() -> None:
    assert suggested_timeout_seconds(0.04) == 1
    assert suggested_timeout_seconds(1.0) == 1
    assert suggested_timeout_seconds(1.01) == 2
    assert suggested_timeout_seconds(5.0) == 5


def test_decide_timeout_uses_p95_of_run_logs() -> None:
    samples = tuple(RunLog(seconds=float(n), exit_code=0) for n in range(1, 21))
    observation = SpeedObservation(
        path="/tmp/hook.py",
        command=("/tmp/hook.py",),
        payload=None,
        runs=20,
        warmup=3,
        mean_seconds=10.5,
        stddev_seconds=1.0,
        median_seconds=10.5,
        min_seconds=1.0,
        max_seconds=20.0,
        samples=samples,
    )
    report = decide_timeout(observation)
    assert report.p95_seconds == pytest.approx(
        percentile(tuple(float(n) for n in range(1, 21)), 95)
    )
    assert report.suggested_timeout_seconds == suggested_timeout_seconds(report.p95_seconds)
    assert len(report.to_json()["runs_log"]) == 20
    assert report.to_json()["runs_log"][0] == {"seconds": 1.0, "exit_code": 0}


def test_observation_from_hyperfine_keeps_every_sample() -> None:
    payload = {
        "mean": 0.02,
        "stddev": 0.001,
        "median": 0.02,
        "min": 0.019,
        "max": 0.021,
        "times": [0.019, 0.02, 0.021],
        "exit_codes": [0, 0, 1],
    }
    observed = observation_from_hyperfine("/bin/true", ("/bin/true",), None, 3, 1, payload)
    assert observed.samples == (
        RunLog(0.019, 0),
        RunLog(0.02, 0),
        RunLog(0.021, 1),
    )


def test_observation_from_hyperfine_reads_version_2_measurements() -> None:
    payload = {
        "command": "/usr/bin/true",
        "measurements": [
            {
                "time_wall_clock": {"value": 0.019, "unit": "second"},
                "exit_code": 0,
            },
            {
                "time_wall_clock": {"value": 0.021, "unit": "second"},
                "exit_code": 1,
            },
        ],
        "summary": {
            "time_wall_clock": {
                "unit": "second",
                "count": 2,
                "mean": 0.02,
                "stddev": 0.001,
                "median": 0.02,
                "min": 0.019,
                "max": 0.021,
            }
        },
    }
    observed = observation_from_hyperfine(
        "/usr/bin/true", ("/usr/bin/true",), None, 2, 0, payload
    )
    assert observed.samples == (RunLog(0.019, 0), RunLog(0.021, 1))
    assert observed.mean_seconds == 0.02
    assert observed.stddev_seconds == 0.001
    assert observed.median_seconds == 0.02
    assert observed.min_seconds == 0.019
    assert observed.max_seconds == 0.021


def test_cli_emits_json_list_with_runs_log_for_true(tmp_path: Path) -> None:
    done = subprocess.run(
        [str(CLI), "--runs", "5", "--warmup", "1", "--", "/usr/bin/true"],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )
    assert done.returncode == 0, done.stderr
    payload = json.loads(done.stdout)
    assert isinstance(payload, list)
    assert len(payload) == 1
    row = payload[0]
    assert row["path"] == "/usr/bin/true"
    assert row["command"] == ["/usr/bin/true"]
    assert row["payload"] is None
    assert row["runs"] == 5
    assert row["warmup"] == 1
    assert len(row["runs_log"]) == 5
    assert {sample["exit_code"] for sample in row["runs_log"]} == {0}
    assert all(sample["seconds"] > 0 for sample in row["runs_log"])
    assert row["suggested_timeout_seconds"] == 1
    assert row["p95_seconds"] > 0


def test_cli_rejects_missing_path() -> None:
    done = subprocess.run(
        [str(CLI), "--", "/tmp/definitely-not-a-hook-executable"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 1
    assert "not a file" in done.stderr
    assert done.stdout == ""


def test_cli_times_a_local_executable_and_records_exit_codes(tmp_path: Path) -> None:
    hook = tmp_path / "flaky-hook"
    hook.write_text("#!/bin/sh\nexit 3\n")
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
    done = subprocess.run(
        [str(CLI), "--runs", "3", "--warmup", "0", "--", str(hook)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    row = json.loads(done.stdout)[0]
    assert row["path"] == str(hook.resolve())
    assert [sample["exit_code"] for sample in row["runs_log"]] == [3, 3, 3]


def test_cli_passes_hook_args_and_records_them(tmp_path: Path) -> None:
    hook = tmp_path / "need-arg"
    hook.write_text('#!/bin/sh\n[ "$1" = expected ] || exit 9\nexit 0\n')
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
    done = subprocess.run(
        [str(CLI), "--runs", "3", "--warmup", "0", "--", str(hook), "expected"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    row = json.loads(done.stdout)[0]
    assert row["command"] == [str(hook.resolve()), "expected"]
    assert [sample["exit_code"] for sample in row["runs_log"]] == [0, 0, 0]


def test_cli_feeds_payload_file_as_stdin(tmp_path: Path) -> None:
    hook = tmp_path / "read-stdin"
    hook.write_text('#!/bin/sh\nread -r line\n[ "$line" = \'{"ok":true}\' ] || exit 4\n')
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
    payload = tmp_path / "event.json"
    payload.write_text('{"ok":true}\n')
    done = subprocess.run(
        [
            str(CLI),
            "--runs",
            "3",
            "--warmup",
            "0",
            "--payload",
            str(payload),
            "--",
            str(hook),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    row = json.loads(done.stdout)[0]
    assert row["payload"] == str(payload.resolve())
    assert [sample["exit_code"] for sample in row["runs_log"]] == [0, 0, 0]
