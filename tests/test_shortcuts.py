import unittest

from calendardesk import shortcuts as sc


class ParseTests(unittest.TestCase):
    def test_single_step(self):
        self.assertEqual(sc.parse("ctrl+alt+c"), ((("Ctrl", "Alt"), "C"),))

    def test_chord_and_canonical_text(self):
        steps = sc.parse("shift + ctrl + o ,  d")
        self.assertEqual(steps, ((("Ctrl", "Shift"), "O"), ((), "D")))
        self.assertEqual(sc.fmt(steps), "Ctrl+Shift+O, D")

    def test_named_keys(self):
        for text in ("Home", "Esc", "Ctrl+,", "F5", "Win+Alt+PageDown", "Ctrl+Shift+Right", "Alt+1"):
            self.assertEqual(sc.fmt(sc.parse(text)), text)

    def test_empty(self):
        self.assertEqual(sc.parse(""), ())
        self.assertEqual(sc.fmt(()), "")

    def test_bad(self):
        for text in ("Ctrl+", "Ctrl+Alt", "Ctrl+Foo", "A, B, C", "Ctrl+A+B", "Hyper+A"):
            with self.assertRaises(ValueError, msg=text):
                sc.parse(text)

    def test_win32(self):
        mods, vk = sc.win32(((("Ctrl", "Alt"), "C")))
        self.assertEqual((mods, vk), (0x2 | 0x1, ord("C")))
        self.assertEqual(sc.win32(((), "Home"))[1], 0x24)
        self.assertEqual(sc.win32((("Ctrl",), ","))[1], 0xBC)

    def test_from_vk(self):
        self.assertEqual(sc.key_from_vk(0x41), "A")
        self.assertEqual(sc.key_from_vk(0x70), "F1")
        self.assertIsNone(sc.key_from_vk(0x10))  # Shift itself is not a key


class EffectiveTests(unittest.TestCase):
    def test_defaults_follow_old_hotkey_letter(self):
        eff = sc.effective({"hotkey": "K"})
        self.assertEqual(eff["toggle_front"], {"keys": "Ctrl+Alt+K", "global": True})
        self.assertEqual(eff["open_today"], {"keys": "Ctrl+Shift+O, D", "global": False})
        self.assertEqual(eff["menu"]["keys"], "Ctrl+Shift+C, H")
        self.assertEqual(eff["new_note"]["keys"], "")

    def test_user_values_override(self):
        eff = sc.effective({"hotkey": "C", "shortcuts": {"open_today": {"keys": "ctrl+alt+d", "global": True}}})
        self.assertEqual(eff["open_today"], {"keys": "Ctrl+Alt+D", "global": True})

    def test_broken_value_falls_back_to_default(self):
        eff = sc.effective({"hotkey": "C", "shortcuts": {"search": {"keys": "Ctrl+Nope"}, "zzz": {"keys": "A"}}})
        self.assertEqual(eff["search"]["keys"], "Ctrl+F")
        self.assertNotIn("zzz", eff)

    def test_every_action_listed_once(self):
        ids = [a[0] for a in sc.ACTIONS]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue({"toggle_front", "open_today", "menu", "quick_add", "search", "settings",
                         "next_month", "prev_month", "go_today", "send_back", "toggle_mini", "new_note",
                         "new_countdown", "countdowns", "show_all", "export", "undo_settings",
                         "shortcuts", "quit", "new_task"} <= set(ids))

    def test_defaults_have_no_conflicts(self):
        eff = sc.effective({"hotkey": "C"})
        for action, b in eff.items():
            errors = [m for lvl, m in sc.conflicts(action, b["keys"], b["global"], eff) if lvl == "error"]
            self.assertEqual(errors, [], action)


class ConflictTests(unittest.TestCase):
    def setUp(self):
        self.eff = sc.effective({"hotkey": "C"})

    def levels(self, action, keys, glob, **kw):
        return sc.conflicts(action, keys, glob, self.eff, **kw)

    def test_same_as_other_action(self):
        out = self.levels("search", "Ctrl+N", False)
        self.assertEqual(out[0][0], "error")
        self.assertIn("New task", out[0][1])

    def test_chord_prefix_clash(self):
        self.eff["search"] = {"keys": "Ctrl+Shift+O", "global": False}
        out = self.levels("export", "Ctrl+Shift+O, X", False)
        self.assertTrue(any(l == "error" and "Search" in m for l, m in out))

    def test_two_chords_with_same_prefix_are_fine(self):
        out = self.levels("export", "Ctrl+Shift+O, X", False)
        self.assertEqual([m for l, m in out if l == "error"], [])

    def test_global_overlaps_calendar_scope(self):
        out = self.levels("export", "Ctrl+F", True)
        self.assertTrue(any(l == "error" and "Search" in m for l, m in out))

    def test_windows_reserved(self):
        for keys in ("Win+L", "Ctrl+Shift+Esc", "Alt+Tab", "Alt+F4", "Ctrl+Alt+Delete", "Win+D"):
            out = self.levels("export", keys, True)
            self.assertTrue(any(l == "error" and "Windows" in m for l, m in out), keys)

    def test_global_needs_a_modifier(self):
        out = self.levels("export", "Shift+A", True)
        self.assertEqual(out[0][0], "error")
        out = self.levels("export", "F7", True)
        self.assertEqual(out[0][0], "error")

    def test_calendar_shortcut_cannot_use_win(self):
        self.assertEqual(self.levels("export", "Win+Alt+X", False)[0][0], "error")

    def test_taken_by_other_program(self):
        out = self.levels("export", "Ctrl+Alt+X", True, taken=lambda step: step == (("Ctrl", "Alt"), "X"))
        self.assertTrue(any(l == "error" and "another program" in m for l, m in out))

    def test_taken_only_checked_for_global(self):
        out = self.levels("export", "Ctrl+Alt+X", False, taken=lambda step: True)
        self.assertEqual(out, [])

    def test_start_menu_shortcut_key_warns(self):
        out = self.levels("export", "Ctrl+Alt+X", True, lnk={"Ctrl+Alt+X": "Calculator"})
        self.assertEqual(out, [("warning", "Ctrl+Alt+X is the shortcut key of 'Calculator' (Start menu or desktop).")])

    def test_common_app_keys_warn_when_global(self):
        out = self.levels("export", "Ctrl+Shift+T", True)
        self.assertEqual(out[0][0], "warning")
        self.assertEqual(self.levels("export", "Ctrl+Shift+T", False), [])

    def test_calculator_keys_warn_when_global(self):
        out = self.levels("export", "Alt+2", True)
        self.assertTrue(any(l == "warning" and "Calculator" in m for l, m in out))

    def test_empty_has_no_conflicts(self):
        self.assertEqual(self.levels("export", "", True), [])

    def test_invalid_text(self):
        self.assertEqual(self.levels("export", "Ctrl+", True)[0][0], "error")


class TkEventTests(unittest.TestCase):
    def test_modifiers_from_state(self):
        self.assertEqual(sc.step_from_tk(0x4 | 0x1, 0x4F), (("Ctrl", "Shift"), "O"))
        self.assertEqual(sc.step_from_tk(0x20000, 0x31), (("Alt",), "1"))
        self.assertEqual(sc.step_from_tk(0x8 | 0x2, 0x24), ((), "Home"))  # NumLock / CapsLock ignored
        self.assertEqual(sc.step_from_tk(0, 0x41, win=True), (("Win",), "A"))

    def test_modifier_key_alone_is_none(self):
        self.assertIsNone(sc.step_from_tk(0x4, 0x11))
        self.assertIsNone(sc.step_from_tk(0, 0xFF))


class LnkTests(unittest.TestCase):
    def _lnk(self, folder, name, vk, mods):
        import os
        import struct
        data = bytearray(0x4C)
        data[0:4] = struct.pack("<I", 0x4C)
        data[4:20] = bytes.fromhex("0114020000000000c000000000000046")
        data[0x40] = vk
        data[0x41] = mods
        with open(os.path.join(folder, name), "wb") as f:
            f.write(bytes(data))

    def test_reads_hotkey_field(self):
        import os
        import tempfile
        d = tempfile.mkdtemp(prefix="cd-test-")
        os.makedirs(os.path.join(d, "Accessories"))
        self._lnk(os.path.join(d, "Accessories"), "Calculator.lnk", ord("K"), 0x2 | 0x4)
        self._lnk(d, "NoKey.lnk", 0, 0)
        with open(os.path.join(d, "junk.lnk"), "wb") as f:
            f.write(b"not a link")
        self.assertEqual(sc.lnk_hotkeys([d, os.path.join(d, "missing")]), {"Ctrl+Alt+K": "Calculator"})
