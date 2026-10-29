from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Self
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "next_move.py"
FIXTURE = ROOT / "tests" / "fixtures" / "board.json"


def load_next_move():
    spec = importlib.util.spec_from_file_location("diagnose_next_move", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


next_move = load_next_move()
FAKE_KEY = "test-key-not-for-logs"


def getenv_without_key(name: str, default: str | None = None) -> str | None:
    if name == next_move.API_KEY_ENV:
        return None
    return os.getenv(name, default)


def getenv_with_key(name: str, default: str | None = None) -> str | None:
    if name == next_move.API_KEY_ENV:
        return "test-key"
    return os.getenv(name, default)


class FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def choice_answer(choice: str, confidence: float = 0.8, **weights: float) -> dict:
    probabilities = dict(weights) if weights else {choice: confidence}
    return {
        "type": "choice",
        "choice": choice,
        "confidence": confidence,
        "probabilities": probabilities,
    }


def noul_answer(value: float) -> dict:
    return {"type": "noul", "noul": value}


def systemone_payload(
    *,
    next_move_choice: str,
    next_test: str = "sock_ping",
    next_test_confidence: float = 0.8,
    snapshot_enough: float = 0.8,
    mitigation_proven: float = 0.1,
    nfs_wedge: float = 0.81,
    qbit_dead: float = 0.22,
    layer: str = "disk_net",
) -> dict:
    return {
        "model": "jev-latest",
        "answers": {
            "next_move": choice_answer(next_move_choice),
            "next_test": choice_answer(
                next_test,
                next_test_confidence,
                sock_ping=next_test_confidence,
                qbit_ctr=0.1,
                none=0.1,
            ),
            "snapshot_enough": noul_answer(snapshot_enough),
            "mitigation_proven": noul_answer(mitigation_proven),
            "fits__nfs_wedge": noul_answer(nfs_wedge),
            "fits__qbit_dead": noul_answer(qbit_dead),
            "split_layer": choice_answer(layer),
        },
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


class NextMoveTests(unittest.TestCase):
    def test_print_request_includes_next_move_catalog(self) -> None:
        env = os.environ.copy()
        env.pop(next_move.API_KEY_ENV, None)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--print-request", "--board", str(FIXTURE)],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        body = json.loads(result.stdout)
        questions = body["questions"]
        self.assertEqual(questions["next_move"]["type"], "choice")
        self.assertIn("next_move", questions)
        self.assertIn("next_test", questions)
        self.assertIn("fits__nfs_wedge", questions)
        self.assertEqual(body["model"], "jev-latest")

    def test_mitigate_with_low_noul_becomes_run_test(self) -> None:
        payload = systemone_payload(next_move_choice="mitigate", mitigation_proven=0.1)
        stdout = io.StringIO()
        with (
            mock.patch(
                "urllib.request.urlopen", return_value=FakeHTTPResponse(payload)
            ) as urlopen,
            redirect_stdout(stdout),
        ):
            code = next_move.main(["--board", str(FIXTURE)], getenv=getenv_with_key)
        self.assertEqual(code, 0)
        result = json.loads(stdout.getvalue())
        self.assertEqual(result["do"], "run_test")
        self.assertEqual(result["test_id"], "sock_ping")
        self.assertEqual(result["raw"]["mitigation_proven"], 0.1)
        urlopen.assert_called_once()

    def test_declare_cause_with_low_fits_becomes_run_test(self) -> None:
        payload = systemone_payload(
            next_move_choice="declare_cause",
            nfs_wedge=0.4,
            qbit_dead=0.3,
            mitigation_proven=0.2,
        )
        stdout = io.StringIO()
        with (
            mock.patch(
                "urllib.request.urlopen", return_value=FakeHTTPResponse(payload)
            ),
            redirect_stdout(stdout),
        ):
            code = next_move.main(["--board", str(FIXTURE)], getenv=getenv_with_key)
        self.assertEqual(code, 0)
        result = json.loads(stdout.getvalue())
        self.assertEqual(result["do"], "run_test")
        self.assertEqual(result["test_id"], "sock_ping")
        self.assertLess(max(result["fits"].values()), 0.75)

    def test_guessed_colima_restart_never_mitigates(self) -> None:
        payload = systemone_payload(next_move_choice="mitigate", mitigation_proven=0.95)
        stdout = io.StringIO()
        with (
            mock.patch(
                "urllib.request.urlopen", return_value=FakeHTTPResponse(payload)
            ),
            redirect_stdout(stdout),
        ):
            code = next_move.main(["--board", str(FIXTURE)], getenv=getenv_with_key)
        self.assertEqual(code, 0)
        result = json.loads(stdout.getvalue())
        self.assertEqual(result["do"], "run_test")

    def test_keychain_key_composes_without_onepassword(self) -> None:
        payload = systemone_payload(next_move_choice="snapshot_more")
        urlopen = mock.Mock(return_value=FakeHTTPResponse(payload))
        read_onepassword = mock.Mock(return_value=FAKE_KEY)
        write_keychain = mock.Mock()
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = next_move.main(
                ["--board", str(FIXTURE)],
                getenv=getenv_without_key,
                urlopen=urlopen,
                read_keychain=lambda: FAKE_KEY,
                read_onepassword=read_onepassword,
                write_keychain=write_keychain,
            )
        self.assertEqual(code, 0)
        result = json.loads(stdout.getvalue())
        self.assertEqual(result["do"], "snapshot_more")
        urlopen.assert_called_once()
        read_onepassword.assert_not_called()
        write_keychain.assert_not_called()

    def test_onepassword_key_is_written_to_keychain(self) -> None:
        payload = systemone_payload(next_move_choice="snapshot_more")
        urlopen = mock.Mock(return_value=FakeHTTPResponse(payload))
        write_keychain = mock.Mock()
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = next_move.main(
                ["--board", str(FIXTURE)],
                getenv=getenv_without_key,
                urlopen=urlopen,
                read_keychain=lambda: None,
                read_onepassword=lambda: FAKE_KEY,
                write_keychain=write_keychain,
            )
        self.assertEqual(code, 0)
        result = json.loads(stdout.getvalue())
        self.assertEqual(result["do"], "snapshot_more")
        urlopen.assert_called_once()
        write_keychain.assert_called_once_with(FAKE_KEY)

    def test_missing_key_from_all_sources_exits_2_without_export(self) -> None:
        stderr = io.StringIO()
        stdout = io.StringIO()
        read_onepassword = mock.Mock(return_value=None)
        write_keychain = mock.Mock()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = next_move.main(
                ["--board", str(FIXTURE)],
                getenv=getenv_without_key,
                read_keychain=lambda: None,
                read_onepassword=read_onepassword,
                write_keychain=write_keychain,
            )
        self.assertEqual(code, 2)
        err = stderr.getvalue()
        self.assertNotIn("export", err.lower())
        self.assertIn("keychain", err.lower())
        self.assertIn("1password", err.lower())
        self.assertEqual(stdout.getvalue(), "")
        read_onepassword.assert_called_once()
        write_keychain.assert_not_called()


if __name__ == "__main__":
    unittest.main()
