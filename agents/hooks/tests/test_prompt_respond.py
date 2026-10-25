"""prompt-respond.py: one question call, then the route table, and nothing else."""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest
from hook_harness import HOOKS_DIR, HookRunner

sys.path.insert(0, str(HOOKS_DIR / "lib"))
from prompt_routes import Route, routes_for

HOOK = "prompt-respond.py"
CALM_P = 0.04
ANGRY_P = 0.91


def envelope(probability: float) -> str:
    return json.dumps({"output": {"answers": {"Frustrated": probability}}})


def answers_script(tmp_path: Path, probability: float) -> Path:
    script = tmp_path / "answers"
    script.write_text(f"#!/bin/sh\nprintf '%s\\n' '{envelope(probability)}'\n")
    script.chmod(0o755)
    return script


def route_script(tmp_path: Path) -> tuple[Path, Path, Path]:
    record = tmp_path / "routed.txt"
    script = tmp_path / "route"
    script.write_text(textwrap.dedent(f"""\
        #!/bin/sh
        printf '%s\\n' "$*" >> {record}
        cat >> {record}
        """))
    script.chmod(0o755)
    routes = tmp_path / "routes.json"
    routes.write_text(json.dumps([{
        "field": "Frustrated",
        "at_least": 0.7,
        "argv": [str(script), "--judged", "{Frustrated}"],
    }]))
    return script, record, routes


def env_for(answers: Path, routes: Path, **extra: str) -> dict[str, str]:
    return {
        "PROMPT_ANSWERS_CMD": str(answers),
        "PROMPT_RESPOND_ROUTES": str(routes),
        "LEARNER": "",
        "AGENTMUX_NESTED_RUN": "",
        **extra,
    }


def test_a_frustrated_answer_runs_the_routed_script_with_the_probability(
    hooks: HookRunner, tmp_path: Path
) -> None:
    _script, record, routes = route_script(tmp_path)
    payload = {"prompt": "please add a test", "session_id": "s"}
    run = hooks.session(HOOK, env_for(answers_script(tmp_path, ANGRY_P), routes)).run_payload(
        HOOK, payload
    )
    assert run.exit_code == 0 and "routes=Frustrated" in run.log
    lines = record.read_text().splitlines()
    assert lines[0] == f"--judged {ANGRY_P:.2f}"
    assert json.loads(lines[1])["prompt"] == payload["prompt"]


def test_an_answer_under_the_bar_starts_nothing(hooks: HookRunner, tmp_path: Path) -> None:
    _script, record, routes = route_script(tmp_path)
    run = hooks.session(HOOK, env_for(answers_script(tmp_path, CALM_P), routes)).run_payload(
        HOOK, {"prompt": "please add a test"}
    )
    assert run.exit_code == 0 and "routes=none" in run.log
    assert not record.exists()


def test_a_learner_session_neither_asks_nor_routes(hooks: HookRunner, tmp_path: Path) -> None:
    calls = tmp_path / "asked"
    answers = tmp_path / "answers"
    answers.write_text(f"#!/bin/sh\necho asked >> {calls}\nprintf '%s\\n' '{envelope(ANGRY_P)}'\n")
    answers.chmod(0o755)
    _script, record, routes = route_script(tmp_path)
    run = hooks.session(HOOK, env_for(answers, routes, LEARNER="1")).run_payload(
        HOOK, {"prompt": "why did you ignore that"}
    )
    assert run.exit_code == 0 and run.log == ""
    assert not calls.exists() and not record.exists()


def test_a_failed_call_starts_nothing(hooks: HookRunner, tmp_path: Path) -> None:
    answers = tmp_path / "answers"
    answers.write_text("#!/bin/sh\nexit 1\n")
    answers.chmod(0o755)
    _script, record, routes = route_script(tmp_path)
    run = hooks.session(HOOK, env_for(answers, routes)).run_payload(HOOK, {"prompt": "add a test"})
    assert run.exit_code == 0 and "routes=none" in run.log
    assert not record.exists()


@pytest.mark.parametrize(
    ("value", "fires"),
    [(0.7, True), (0.69, False), (True, False), ({"Value": "yes"}, False)],
)
def test_only_a_number_at_the_bar_matches(value: object, fires: bool) -> None:
    route = Route("Frustrated", 0.7, ("learn", "--judged", "{Frustrated}"))
    matched = routes_for({"Frustrated": value}, [route])
    assert bool(matched) is fires
    if fires:
        assert matched[0].argv == ("learn", "--judged", "0.70")
