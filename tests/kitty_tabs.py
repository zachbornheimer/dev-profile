"""Run with Kitty's embedded Python via mise run test:kitty-tabs; no UI needed."""

import runpy
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import kitty.fast_data_types as native
from kitty.config import load_config

import kitty.tab_bar as engine

KITTY_CONFIG = Path(__file__).resolve().parents[1] / "kitty"


class KittyTabLabelsTest(unittest.TestCase):
    def test_custom_labels_fill_equal_width_tabs(self):
        options = load_config(str(KITTY_CONFIG / "browser-tabs.conf"))
        tabs = [
            engine.TabBarData("/work/project", tab_id=1, is_active=True),
            engine.TabBarData("Release notes", tab_id=2),
            engine.TabBarData("Thinking - Repair tabs - codex", tab_id=3),
            engine.TabBarData("+", tab_id=-1),
        ]
        active_window = SimpleNamespace(
            get_cwd_of_active_window=lambda: "/work/project",
            get_exe_of_active_window=lambda: "/usr/bin/python3.14",
        )
        boss = SimpleNamespace(
            os_window_map={0: SimpleNamespace(tabs_to_be_shown_in_tab_bar=tabs[:-1])},
            tab_for_id=lambda tab_id: active_window,
            mappings=SimpleNamespace(current_keyboard_mode_name=""),
        )
        # Only host/window state is supplied; Kitty loads the actual config/module,
        # evaluates {custom}, measures tabs and paints its native Screen.
        with (
            patch.object(engine, "config_dir", str(KITTY_CONFIG)),
            patch.object(engine, "get_options", return_value=options),
            patch.object(native, "get_options", return_value=options),
            patch.object(engine, "get_boss", return_value=boss),
            patch.object(native, "get_boss", return_value=boss),
            patch.object(native, "get_window_being_dragged", return_value=(0, 0)),
            patch.object(engine, "pt_to_px", return_value=0),
            patch.object(engine, "cell_size_for_window", return_value=(10, 20)),
            patch.object(engine, "update_tab_bar_edge_colors", return_value=None),
        ):
            engine.load_custom_draw_tab_module.clear_cached()
            engine.load_custom_draw_tab.clear_cached()
            bar = engine.TabBar(0)
            bar.screen.resize(1, 99)
            bar.laid_out_once = True
            bar.update(tabs)
            rendered = str(bar.screen.line(0))
            self.assertIn("project", rendered)
            self.assertIn("Release notes", rendered)
            self.assertIn("Repair tabs", rendered)
            self.assertIn(chr(0xE73C), rendered)
            self.assertTrue(rendered.endswith(" + "), repr(rendered))
            self.assertEqual(
                [(extent.x.start, extent.x.end) for extent in bar.tab_extents],
                [(0, 32), (32, 64), (64, 96), (96, 99)],
            )

    def test_unicode_icon_codepoints_and_literal_glyphs(self):
        module = runpy.run_path(str(KITTY_CONFIG / "tab_bar.py"))
        for value, expected in (
            ("U+E73C", "\ue73c"),
            ("u+e73c", "\ue73c"),
            (" U+F0868 ", "\U000f0868"),
            ("\ue73c", "\ue73c"),
            ("python", ""),
            ("", ""),
        ):
            with self.subTest(glyph=value):
                self.assertEqual(module["_parse_glyph"](value), expected)


if __name__ == "__main__":
    unittest.main(argv=["kitty-tabs"])
