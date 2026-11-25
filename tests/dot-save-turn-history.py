#!/usr/bin/env python3
"""Exercise the wrapper's provenance boundary without live history or credentials."""

import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CheckpointHistory(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.index = self.root / "state/history/index"
        (self.index / "meta").mkdir(parents=True)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        mise = self.bin / "mise"
        mise.write_text("""#!/usr/bin/env python3
import os, sys
if sys.argv[1:3] != ["dot", "save"]:
    sys.exit("history enumeration is forbidden in the bounded wrapper")
print(os.environ.get("RECEIPT", "mise history: saved checkpoint 10001: agent: ZYS-11254"))
sys.exit(int(os.environ.get("SAVE_EXIT", "0")))
""")
        mise.chmod(0o755)
        self.uuid = "a" * 40
        self.record = {
            "schema_version": 2,
            "uuid": self.uuid,
            "trigger": "agent",
            "task": "ZYS-11254",
            "description_source": "agent",
            "description": "agent: ZYS-11254",
            "tree": {"available": True},
            "changes": {
                "modified": ["~/.named"],
                "added": ["~/.swept"],
                "removed": ["~/.deleted"],
                "truncated": False,
            },
        }
        self.entries = [{"id": 10001, "uuid": self.uuid, "commit": self.uuid}]
        self.env = dict(
            os.environ,
            HOME=str(self.root),
            MISE_STATE_DIR=str(self.root / "state"),
            PATH=f"{self.bin}:{os.environ['PATH']}",
        )

    def run_wrapper(self):
        (self.index / "checkpoints.json").write_text(
            json.dumps({"entries": self.entries})
        )
        (self.index / f"meta/{self.uuid}.json").write_text(json.dumps(self.record))
        return subprocess.run(
            [
                str(ROOT / "bin/dev-profile-dot-save-turn"),
                "ZYS-11254",
                str(self.root / ".named"),
            ],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=5,
        )

    def test_large_history_and_concurrent_latest(self):
        # Unreadable unrelated records make any metadata traversal fail. The
        # newest entry belongs to another writer, not the receipt's checkpoint.
        self.entries = [
            {"id": i, "uuid": f"{i:040x}", "commit": f"{i:040x}"}
            for i in range(1, 10001)
        ] + self.entries
        for entry in self.entries[:-1]:
            (self.index / f"meta/{entry['uuid']}.json").write_text(
                "invalid unused metadata"
            )
        self.entries.append({"id": 10002, "uuid": "b" * 40, "commit": "b" * 40})
        start = time.monotonic()
        result = self.run_wrapper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(time.monotonic() - start, 5)
        self.assertIn("checkpoint 10001  trigger=agent  task=ZYS-11254", result.stdout)
        authored, swept = result.stdout.split("captured-not-authored:\n")
        self.assertIn("  ~/.named\n", authored)
        self.assertNotIn("~/.swept", authored)
        self.assertIn("  ~/.swept\n", swept)
        self.assertIn("  ~/.deleted\n", swept)

    def test_wrong_provenance_is_not_reported(self):
        for field, value in [
            ("task", "ZYS-1"),
            ("trigger", "save"),
            ("description_source", "computed"),
            ("uuid", "b" * 40),
            ("schema_version", 3),
        ]:
            with self.subTest(field=field):
                original = self.record[field]
                self.record[field] = value
                result = self.run_wrapper()
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("authored:", result.stdout)
                self.record[field] = original

    def test_incomplete_changes_are_not_reported(self):
        self.record["changes"]["truncated"] = True
        result = self.run_wrapper()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("authored:", result.stdout)

    def test_no_receipt_cannot_reuse_old_checkpoint(self):
        self.env["RECEIPT"] = "history: nothing changed since the latest checkpoint"
        result = self.run_wrapper()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("authored:", result.stdout)

    def test_failed_save_cannot_reuse_old_checkpoint(self):
        self.env["SAVE_EXIT"] = "1"
        result = self.run_wrapper()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("authored:", result.stdout)


if __name__ == "__main__":
    unittest.main()
