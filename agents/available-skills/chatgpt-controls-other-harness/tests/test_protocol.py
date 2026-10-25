import unittest
import uuid

from chatgpt_control_claude.protocol import (
    new_run_id,
    runner_filename,
    evidence_zip_filename,
    parse_runner_id,
)


class ProtocolTests(unittest.TestCase):
    def test_new_run_id_is_uuid(self):
        value = new_run_id()
        self.assertEqual(str(uuid.UUID(value)), value)

    def test_round_trip_runner_filename(self):
        value = new_run_id()
        name = runner_filename(value)
        self.assertEqual(parse_runner_id(name), value)

    def test_evidence_zip_filename(self):
        value = new_run_id()
        self.assertEqual(evidence_zip_filename(value), f"{value}.zip")

    def test_rejects_non_runner_filename(self):
        with self.assertRaises(ValueError):
            parse_runner_id("runner.py")


if __name__ == "__main__":
    unittest.main()
