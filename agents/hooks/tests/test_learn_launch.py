"""learn-launch: /learn runs the learn-from-transcript workflow on the named source."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

LAUNCHER = Path(__file__).resolve().parents[2] / "bin" / "learn-launch"
TARGET = "01a163ee-d96e-7370-8136-b743e0bc1855"


def launch(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(LAUNCHER), *args, "--dry-run"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def plan(run: subprocess.CompletedProcess[str]) -> dict:
    assert run.returncode == 0, run.stderr
    document = json.loads(run.stdout)
    assert document["command"][:3] == ["capability", "run", "learn-from-transcript"]
    assert json.loads(document["command"][4]) == {
        "source": document["source"],
        "dispatch": document["dispatch"],
    }
    return document


def test_dispatch_is_on_by_default() -> None:
    document = plan(launch(f"omp:{TARGET}"))
    assert document["dispatch"] is True
    assert json.loads(document["command"][4])["dispatch"] is True


def test_dispatch_flag_remains_accepted() -> None:
    document = plan(launch(f"omp:{TARGET}", "--dispatch"))
    assert document["dispatch"] is True
    assert json.loads(document["command"][4])["dispatch"] is True


def test_no_dispatch_flag_turns_dispatch_off() -> None:
    document = plan(launch(f"omp:{TARGET}", "--no-dispatch"))
    assert document["dispatch"] is False
    assert json.loads(document["command"][4])["dispatch"] is False
def test_a_harness_id_is_the_workflow_source() -> None:
    assert plan(launch(f"omp:{TARGET}"))["source"] == f"omp:{TARGET}"


def test_a_bare_omp_id_names_the_omp_session() -> None:
    assert plan(launch(TARGET))["source"] == f"omp:{TARGET}"


def test_a_mastra_url_normalizes_to_the_thread_ref() -> None:
    url = f"https://studio.example.com/agents/forensics/threads/{TARGET}"
    assert plan(launch(url))["source"] == f"mastra:thread:{TARGET}"


def test_a_non_source_word_is_refused() -> None:
    run = launch("why does it retry")
    assert run.returncode == 1
    assert "ref must be <harness>:<id> or a Mastra thread URL" in run.stderr


def test_a_missing_ref_is_refused() -> None:
    run = launch()
    assert run.returncode != 0
    assert run.stderr.strip() != ""


def test_failure_releases_the_claimed_cooldown_stamp(tmp_path: Path) -> None:
    stamp = tmp_path / "omp_session"
    stamp.write_text("1700000000\n")
    run = subprocess.run(
        [str(LAUNCHER), "not-a-valid-ref"],
        capture_output=True,
        text=True,
        timeout=30,
        env={
            "PATH": f"{Path.home() / '.local/share/mise/shims'}:/usr/bin:/bin:/opt/homebrew/bin",
            "HOME": str(Path.home()),
            "LEARN_STAMP_FILE": str(stamp),
        },
        check=False,
    )
    assert run.returncode == 1
    assert not stamp.exists()


def test_find_local_transcript_locates_omp_session(tmp_path: Path) -> None:
    import importlib.machinery
    import importlib.util

    loader = importlib.machinery.SourceFileLoader("learn_launch_mod", str(LAUNCHER))
    spec = importlib.util.spec_from_loader("learn_launch_mod", loader)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    session_dir = tmp_path / ".omp" / "agent" / "sessions" / "--repo--"
    session_dir.mkdir(parents=True)
    session_file = session_dir / f"2026-10-31T00-00-00-000Z_{TARGET}.jsonl"
    session_file.write_text('{"id":"1"}\n', encoding="utf-8")

    found = mod.find_local_transcript(f"omp:{TARGET}", home=tmp_path)
    assert found == session_file
    assert mod.fleet_command(f"omp:{TARGET}", True, platform="linux") is None
