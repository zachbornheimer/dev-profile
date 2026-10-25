#!/usr/bin/env python3
"""Behavior tests for relocate-synced-skills SessionStart hook."""

from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

HOOK_PATH = Path(__file__).resolve().parents[1] / "relocate-synced-skills.py"
HOME_ENV = "SYNCED_RELOCATE_HOME"


def load_hook():
    spec = importlib.util.spec_from_file_location("relocate_synced_skills", HOOK_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load hook from {HOOK_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_skill(root: Path, *parts: str) -> Path:
    skill_dir = root.joinpath(*parts)
    skill_dir.mkdir(parents=True)
    path = skill_dir / "SKILL.md"
    path.write_text("---\nname: demo\ndescription: demo\n---\n", encoding="utf-8")
    return path


class RelocateSyncedSkillsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.hook = load_hook()
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        self._old_home = os.environ.get(HOME_ENV)
        os.environ[HOME_ENV] = str(self.home)

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop(HOME_ENV, None)
        else:
            os.environ[HOME_ENV] = self._old_home
        self._tmp.cleanup()

    def test_moves_agents_synced_into_available_skills(self) -> None:
        write_skill(
            self.home,
            ".agents",
            "skills",
            "synced",
            "uuid-folder",
            "pdf",
        )
        core = self.home / ".agents" / "skills" / "prompt-writer"
        core.mkdir(parents=True)
        (core / "SKILL.md").write_text("# core\n", encoding="utf-8")

        code = self.hook.main()

        self.assertEqual(code, 0)
        self.assertFalse((self.home / ".agents" / "skills" / "synced").exists())
        self.assertTrue(
            (
                self.home
                / ".agents"
                / "available-skills"
                / "synced"
                / "uuid-folder"
                / "pdf"
                / "SKILL.md"
            ).is_file()
        )
        self.assertTrue((core / "SKILL.md").is_file())

    def test_moves_claude_local_synced_without_touching_agents_core(self) -> None:
        write_skill(
            self.home,
            ".claude",
            "skills",
            "synced",
            "uuid-folder",
            "xlsx",
        )
        core = self.home / ".agents" / "skills" / "bar"
        core.mkdir(parents=True)
        (core / "SKILL.md").write_text("# bar\n", encoding="utf-8")

        code = self.hook.main()

        self.assertEqual(code, 0)
        self.assertFalse((self.home / ".claude" / "skills" / "synced").exists())
        self.assertTrue(
            (
                self.home
                / ".agents"
                / "available-skills"
                / "synced"
                / "uuid-folder"
                / "xlsx"
                / "SKILL.md"
            ).is_file()
        )
        self.assertTrue((core / "SKILL.md").is_file())

    def test_merges_into_existing_available_synced(self) -> None:
        write_skill(
            self.home,
            ".agents",
            "available-skills",
            "synced",
            "uuid-folder",
            "keep",
        )
        write_skill(
            self.home,
            ".agents",
            "skills",
            "synced",
            "uuid-folder",
            "new",
        )

        self.assertEqual(self.hook.main(), 0)
        dest = self.home / ".agents" / "available-skills" / "synced" / "uuid-folder"
        self.assertTrue((dest / "keep" / "SKILL.md").is_file())
        self.assertTrue((dest / "new" / "SKILL.md").is_file())
        self.assertFalse((self.home / ".agents" / "skills" / "synced").exists())

    def test_missing_trees_exits_zero_silent(self) -> None:
        self.assertEqual(self.hook.main(), 0)
        self.assertFalse((self.home / ".agents" / "skills" / "synced").exists())
        self.assertFalse((self.home / ".claude" / "skills" / "synced").exists())

    def test_removes_claude_trash_skill_without_touching_typesafe(self) -> None:
        trash = write_skill(
            self.home,
            ".claude",
            "skills",
            ".trash",
            "uuid-folder",
            "docx",
        )
        keep = self.home / ".claude" / "skills" / "typesafe-ai"
        keep.mkdir(parents=True)
        (keep / "SKILL.md").write_text("# typesafe-ai\n", encoding="utf-8")

        code = self.hook.main()

        self.assertEqual(code, 0)
        self.assertFalse(trash.exists())
        self.assertFalse((self.home / ".claude" / "skills" / ".trash").exists())
        self.assertTrue((keep / "SKILL.md").is_file())
        remaining = list((self.home / ".claude" / "skills").rglob("SKILL.md"))
        self.assertEqual(remaining, [keep / "SKILL.md"])

    def test_removes_extra_claude_skill_dirs_keeps_typesafe_symlink(self) -> None:
        extra = write_skill(self.home, ".claude", "skills", "morning")
        target = self.home / ".agents" / "skills" / "typesafe-ai"
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text("# typesafe-ai\n", encoding="utf-8")
        link = self.home / ".claude" / "skills" / "typesafe-ai"
        link.symlink_to(target)

        code = self.hook.main()

        self.assertEqual(code, 0)
        self.assertFalse(extra.exists())
        self.assertFalse((self.home / ".claude" / "skills" / "morning").exists())
        self.assertTrue(link.is_symlink())
        self.assertTrue((link / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
