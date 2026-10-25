from pathlib import Path
import unittest

from chatgpt_control_claude.files_list import (
    FileRow,
    is_executable_runner,
    pick_runner,
    runner_argv,
    visible_rows,
)
from chatgpt_control_claude.provider import harness_command, require_provider


def _row(name: str, y: float) -> FileRow:
    return FileRow(name=name, y=y)


class RequireProviderTests(unittest.TestCase):
    def test_returns_stripped_value(self) -> None:
        self.assertEqual(require_provider({"PROVIDER": " grok "}), "grok")

    def test_missing_dies(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "PROVIDER is required"):
            require_provider({})

    def test_blank_dies(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "PROVIDER is required"):
            require_provider({"PROVIDER": "  "})

    def test_unknown_provider_dies(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "unknown PROVIDER"):
            harness_command(
                prompt="task",
                cwd=Path("/tmp"),
                env={"PROVIDER": "not-a-harness"},
            )

    def test_grok_command_shape(self) -> None:
        from unittest.mock import patch

        with patch("chatgpt_control_claude.provider.shutil.which", return_value="/bin/grok"):
            command = harness_command(
                prompt="Do the bounded task.",
                cwd=Path("/tmp/repo"),
                env={"PROVIDER": "grok"},
            )
        self.assertEqual(command[0], "grok")
        self.assertEqual(command[-2:], ["-p", "Do the bounded task."])


class VisibleRowsTests(unittest.TestCase):
    def test_stops_at_recycle_pile(self) -> None:
        rows = [
            _row("a.zip", 93),
            _row("run-5a0b318b-a970-4380-85bd-9959d3b5b5ff.py", 181),
            _row("b.zip", 251),
            _row("c.zip", 668),
            _row("a.zip", 671),
            _row("run-5a0b318b-a970-4380-85bd-9959d3b5b5ff.py", 671),
        ]
        visible = visible_rows(rows)
        self.assertEqual([r.name for r in visible], ["a.zip", "run-5a0b318b-a970-4380-85bd-9959d3b5b5ff.py", "b.zip", "c.zip"])


class PickRunnerTests(unittest.TestCase):
    UID_OLD = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    UID_NEW = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

    def setUp(self) -> None:
        self.downloads = Path("/tmp/fake-downloads")
        self.rows = [
            _row("notes.txt", 90),
            _row(f"run-{self.UID_OLD}.py", 180),
            _row("evidence.zip", 250),
            _row(f"run-{self.UID_NEW}.py", 600),
            _row(f"run-{self.UID_NEW}.py", 671),
        ]

    def test_bottom_picks_newest_run_py(self) -> None:
        chosen = pick_runner(
            self.rows,
            processed={},
            downloads=self.downloads,
            newest="bottom",
            exists=lambda _p: False,
        )
        assert chosen is not None
        self.assertEqual(chosen.name, f"run-{self.UID_NEW}.py")

    def test_top_picks_oldest_run_py(self) -> None:
        chosen = pick_runner(
            self.rows,
            processed={},
            downloads=self.downloads,
            newest="top",
            exists=lambda _p: False,
        )
        assert chosen is not None
        self.assertEqual(chosen.name, f"run-{self.UID_OLD}.py")

    def test_skips_existing_downloads_file(self) -> None:
        existing = {self.downloads / f"run-{self.UID_NEW}.py"}
        chosen = pick_runner(
            self.rows,
            processed={},
            downloads=self.downloads,
            newest="bottom",
            exists=lambda p: p in existing,
        )
        assert chosen is not None
        self.assertEqual(chosen.name, f"run-{self.UID_OLD}.py")

    def test_skips_processed_uuid(self) -> None:
        chosen = pick_runner(
            self.rows,
            processed={self.UID_NEW: {"status": "returned"}},
            downloads=self.downloads,
            newest="bottom",
            exists=lambda _p: False,
        )
        assert chosen is not None
        self.assertEqual(chosen.name, f"run-{self.UID_OLD}.py")

    def test_zip_and_py_are_executable(self) -> None:
        uid = "dddddddd-dddd-dddd-dddd-dddddddddddd"
        self.assertTrue(is_executable_runner(f"run-{uid}.py"))
        self.assertTrue(is_executable_runner(f"run-{uid}.zip"))
        self.assertFalse(is_executable_runner(f"run-{uid}.txt"))

    def test_zip_runs_as_uv_run_python(self) -> None:
        path = Path.home() / "Downloads" / "run-dddddddd-dddd-dddd-dddd-dddddddddddd.zip"
        self.assertEqual(
            runner_argv("/opt/uv", path),
            ["/opt/uv", "run", "python", str(path)],
        )

    def test_py_runs_as_uv_run_dashdash(self) -> None:
        path = Path.home() / "Downloads" / "run-dddddddd-dddd-dddd-dddd-dddddddddddd.py"
        self.assertEqual(
            runner_argv("/opt/uv", path),
            ["/opt/uv", "run", "--", str(path)],
        )

    def test_accepts_zip_artifact(self) -> None:
        uid = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        rows = [_row("a.zip", 10), _row(f"run-{uid}.zip", 80)]
        chosen = pick_runner(
            rows,
            processed={},
            downloads=self.downloads,
            newest="bottom",
            exists=lambda _p: False,
        )
        assert chosen is not None
        self.assertEqual(chosen.name, f"run-{uid}.zip")

    def test_none_when_all_skipped(self) -> None:
        chosen = pick_runner(
            self.rows,
            processed={self.UID_OLD: {}, self.UID_NEW: {}},
            downloads=self.downloads,
            newest="bottom",
            exists=lambda _p: False,
        )
        self.assertIsNone(chosen)


if __name__ == "__main__":
    unittest.main()
