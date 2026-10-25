from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
ROUTE_PATH = SCRIPTS / "route.py"
INVENTORY_PATH = SCRIPTS / "inventory-project.py"
REQUIRED_IDENTIFIER_PATTERN = r"^([A-Za-z][A-Za-z0-9]*)-(\d+)$"


def load_route():
    scripts = str(SCRIPTS)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = importlib.util.spec_from_file_location("route", ROUTE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {ROUTE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["route"] = module
    spec.loader.exec_module(module)
    return module


def load_inventory():
    load_route()
    spec = importlib.util.spec_from_file_location(
        "inventory_project", INVENTORY_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {INVENTORY_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["inventory_project"] = module
    spec.loader.exec_module(module)
    return module


class WorkspaceRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.route = load_route()

    def test_identifier_pattern_is_the_shipped_regex(self) -> None:
        self.assertEqual(self.route.IDENTIFIER.pattern, REQUIRED_IDENTIFIER_PATTERN)

    def test_zys_identifier_routes_to_personal_linear(self) -> None:
        self.assertEqual(self.route.workspace_for("ZYS-806"), "personal")
        self.assertEqual(self.route.mcp_server_for("ZYS-806"), "linear-personal")

    def test_sah_identifier_routes_to_work_linear(self) -> None:
        self.assertEqual(self.route.workspace_for("SAH-1"), "work")
        self.assertEqual(self.route.mcp_server_for("SAH-1"), "linear-sah")

    def test_prefix_is_case_insensitive(self) -> None:
        self.assertEqual(
            self.route.workspace_for("zys-806"),
            self.route.workspace_for("ZYS-806"),
        )
        self.assertEqual(
            self.route.mcp_server_for("zys-806"),
            self.route.mcp_server_for("ZYS-806"),
        )

    def test_unknown_prefix_raises_named_error(self) -> None:
        with self.assertRaises(self.route.UnknownPrefixError):
            self.route.workspace_for("ABC-1")
        with self.assertRaises(self.route.UnknownPrefixError):
            self.route.mcp_server_for("ABC-1")

    def test_empty_identifier_raises(self) -> None:
        with self.assertRaises(self.route.InvalidIdentifierError):
            self.route.workspace_for("")

    def test_project_identifier_is_not_an_issue(self) -> None:
        with self.assertRaises(self.route.InvalidIdentifierError):
            self.route.workspace_for("P-ENG-123")

    def test_prefix_without_number_raises(self) -> None:
        with self.assertRaises(self.route.InvalidIdentifierError):
            self.route.workspace_for("ZYS")


class InventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.route = load_route()
        cls.inventory = load_inventory()

    def test_argv_emits_json_rows_in_order(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(INVENTORY_PATH), "ZYS-806", "SAH-1"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        rows = json.loads(completed.stdout)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["id"], "ZYS-806")
        self.assertEqual(rows[0]["workspace"], self.route.workspace_for("ZYS-806"))
        self.assertEqual(rows[0]["mcp"], self.route.mcp_server_for("ZYS-806"))
        self.assertEqual(rows[1]["id"], "SAH-1")
        self.assertEqual(rows[1]["workspace"], self.route.workspace_for("SAH-1"))
        self.assertEqual(rows[1]["mcp"], self.route.mcp_server_for("SAH-1"))

    def test_stdin_emits_json_rows(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(INVENTORY_PATH)],
            check=False,
            capture_output=True,
            text=True,
            input="zys-806\nSAH-1\n",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        rows = json.loads(completed.stdout)
        self.assertEqual(
            [row["workspace"] for row in rows],
            [
                self.route.workspace_for("zys-806"),
                self.route.workspace_for("SAH-1"),
            ],
        )

    def test_unknown_prefix_exits_nonzero(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(INVENTORY_PATH), "ABC-1"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertTrue(completed.stderr)

    def test_empty_input_exits_nonzero(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(INVENTORY_PATH)],
            check=False,
            capture_output=True,
            text=True,
            input="",
        )
        self.assertNotEqual(completed.returncode, 0)

    def test_inventory_rows_use_workspace_for(self) -> None:
        rows = self.inventory.inventory(["ZYS-806", "SAH-1"])
        self.assertEqual(
            rows[0],
            {
                "id": "ZYS-806",
                "workspace": self.route.workspace_for("ZYS-806"),
                "mcp": self.route.mcp_server_for("ZYS-806"),
            },
        )


class InventoryStdinCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inventory = load_inventory()

    def test_argv_wins_over_stdin(self) -> None:
        identifiers = self.inventory.collect_identifiers(
            ["SAH-1"], io.StringIO("ZYS-806\n")
        )
        self.assertEqual(identifiers, ["SAH-1"])


if __name__ == "__main__":
    unittest.main()
