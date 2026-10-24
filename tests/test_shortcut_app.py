"""Shortcuts inside the running app: calendar keys, chords, global keys, Settings and the recorder."""
import tempfile
import time
import unittest
from datetime import date
from types import SimpleNamespace
from unittest import mock

from calendardesk import shortcuts, winapi
from calendardesk.store import Store

CTRL, SHIFT, ALT = 0x4, 0x1, 0x20000
VK = shortcuts.KEYS


def pump(root, ms=50):
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        root.update()
        time.sleep(0.005)


class AppShortcutTests(unittest.TestCase):
    def setUp(self):
        from calendardesk.app import App
        self.store = Store(tempfile.mkdtemp(prefix="cd-test-"))
        self.store.settings["hotkey"] = "K"  # leave Ctrl+Alt+C to a running CalendarDesk
        self.app = App(self.store, tray=False)
        self.errors = []
        self.app.root.report_callback_exception = lambda *exc: self.errors.append(exc)
        self.cal = self.app.calendar
        pump(self.app.root, 200)

    def tearDown(self):
        self.app.quit()
        self.assertEqual(self.errors, [])

    def key(self, state, key, view=None, widget=None):
        view = view or self.cal
        e = SimpleNamespace(widget=widget or view.canvas, state=state, keycode=VK[key])
        return self.app._key(e, view)

    def panels(self):
        from calendardesk.day_panel import DayPanel
        return [v for v in self.app.views if isinstance(v, DayPanel)]

    # -- calendar keys ---------------------------------------------------------
    def test_arrows_and_home_move_the_month(self):
        start = (self.cal.year, self.cal.month)
        self.assertEqual(self.key(0, "Right"), "break")
        self.assertNotEqual((self.cal.year, self.cal.month), start)
        self.key(0, "Left")
        self.key(0, "Left")
        self.key(0, "Home")
        self.assertEqual((self.cal.year, self.cal.month), start)

    def test_chord_opens_today(self):
        self.assertEqual(self.key(CTRL | SHIFT, "O"), "break")
        self.assertEqual(self.panels(), [])
        self.key(CTRL | SHIFT, "D")  # second key with the modifiers still held
        pump(self.app.root, 100)
        self.assertEqual([p.day for p in self.panels()], [date.today()])

    def test_chord_second_key_released_modifiers(self):
        self.key(CTRL | SHIFT, "O")
        self.key(0, "D")
        pump(self.app.root, 100)
        self.assertEqual(len(self.panels()), 1)

    def test_chord_times_out(self):
        self.key(CTRL | SHIFT, "O")
        pump(self.app.root, shortcuts.CHORD_MS + 200)
        self.assertIsNone(self.key(0, "D"))  # plain D is not a shortcut
        self.assertEqual(self.panels(), [])

    def test_wrong_second_key_cancels_chord_and_counts_as_a_new_key(self):
        start = (self.cal.year, self.cal.month)
        self.key(CTRL | SHIFT, "O")
        self.key(0, "Right")
        self.assertNotEqual((self.cal.year, self.cal.month), start)
        self.assertIsNone(self.app._key_wait)

    def test_modifier_alone_keeps_chord_waiting(self):
        self.key(CTRL | SHIFT, "O")
        e = SimpleNamespace(widget=self.cal.canvas, state=CTRL, keycode=0x11)
        self.assertIsNone(self.app._key(e, self.cal))
        self.assertIsNotNone(self.app._key_wait)

    def test_typing_in_a_box_is_never_a_shortcut(self):
        self.cal.quick_add_today()
        pump(self.app.root)
        box = self.cal.quick
        self.assertIsNotNone(box)
        start = (self.cal.year, self.cal.month)
        self.assertIsNone(self.key(0, "Right", widget=box))
        self.assertEqual((self.cal.year, self.cal.month), start)

    def test_quick_add_opens_on_today_from_another_month(self):
        self.cal.go(3)
        self.key(CTRL | SHIFT, "N")
        pump(self.app.root)
        t = date.today()
        self.assertEqual((self.cal.year, self.cal.month), (t.year, t.month))
        self.assertIsNotNone(self.cal.quick)

    def test_real_key_event_reaches_the_binding(self):
        self.cal.to_front()
        pump(self.app.root, 100)
        start = (self.cal.year, self.cal.month)
        self.cal.canvas.focus_force()
        pump(self.app.root, 50)
        self.cal.win.event_generate("<KeyPress>", keysym="Right", keycode=VK["Right"], when="now")
        pump(self.app.root, 50)
        self.assertNotEqual((self.cal.year, self.cal.month), start)

    def test_mini_calendar_navigates_itself(self):
        self.app.toggle_mini()
        pump(self.app.root, 100)
        mini = self.app.mini
        cal_month, mini_month = (self.cal.year, self.cal.month), (mini.year, mini.month)
        self.key(0, "Right", view=mini, widget=mini.canvas)
        self.assertEqual((self.cal.year, self.cal.month), cal_month)
        self.assertNotEqual((mini.year, mini.month), mini_month)
        self.key(0, "Home", view=mini, widget=mini.canvas)
        self.assertEqual((mini.year, mini.month), mini_month)

    def test_escape_sends_back(self):
        self.cal.to_front()
        pump(self.app.root, 50)
        self.key(0, "Esc")
        self.assertFalse(self.cal.front)

    # -- global keys -------------------------------------------------------------
    def test_toggle_front_is_registered_and_runs(self):
        step = shortcuts.parse("Ctrl+Alt+K")[0]
        self.assertIn(shortcuts.win32(step), self.app.hotkey.active)
        self.assertFalse(self.app.shortcut_taken(step))  # ours does not count as taken
        hid = self.app.hotkey._ids[shortcuts.win32(step)]
        winapi.user32.PostThreadMessageW(self.app.hotkey.tid, winapi.WM_HOTKEY, hid, 0)
        # Other threads hand actions over through Tk's main loop, so run the real one.
        self.app.root.after(400, self.app.root.quit)
        self.app.root.mainloop()
        self.assertTrue(self.cal.front)

    def test_global_switch_off_frees_every_key(self):
        values = self.settings_values()
        self.app.apply_settings({**values, "global_shortcuts": False}, undo=self.app.settings_snapshot())
        self.assertEqual(self.app.hotkey.active, set())
        self.assertFalse(winapi.probe_hotkey(*shortcuts.win32(shortcuts.parse("Ctrl+Alt+K")[0])))
        self.app.undo_settings()
        self.assertEqual(len(self.app.hotkey.active), 1)

    def settings_values(self):
        from calendardesk.dialogs import SettingsDialog
        d = SettingsDialog(self.app)
        v = d.values()
        d.close()
        return v

    # -- Settings ------------------------------------------------------------------
    def open_settings(self):
        from calendardesk.dialogs import SettingsDialog
        d = self.app._single(SettingsDialog)
        pump(self.app.root, 50)
        return d

    def test_save_new_shortcut_applies_and_stores_only_changes(self):
        d = self.open_settings()
        d.shortcuts._set("open_today", "Ctrl+Alt+Shift+F20", True)
        d.shortcuts._set("next_month", "Ctrl+Right", False)
        d.save()
        pump(self.app.root, 50)
        self.assertEqual(self.store.settings["shortcuts"],
                         {"open_today": {"keys": "Ctrl+Alt+Shift+F20", "global": True},
                          "next_month": {"keys": "Ctrl+Right", "global": False}})
        self.assertIn(shortcuts.win32(shortcuts.parse("Ctrl+Alt+Shift+F20")[0]), self.app.hotkey.active)
        start = (self.cal.year, self.cal.month)
        self.assertIsNone(self.key(0, "Right"))  # the old key does nothing now
        self.key(CTRL, "Right")
        self.assertNotEqual((self.cal.year, self.cal.month), start)
        # Undo puts the old shortcuts back, registration included.
        self.app.undo_settings()
        self.assertEqual(self.store.settings["shortcuts"], {})
        self.assertNotIn(shortcuts.win32(shortcuts.parse("Ctrl+Alt+Shift+F20")[0]), self.app.hotkey.active)
        self.assertEqual(self.key(0, "Right"), "break")

    def test_cancel_keeps_old_shortcuts(self):
        d = self.open_settings()
        d.shortcuts._set("search", "", False)
        d.close()
        self.assertEqual(shortcuts.effective(self.store.settings)["search"]["keys"], "Ctrl+F")

    def test_save_refused_on_conflict(self):
        d = self.open_settings()
        d.shortcuts._set("search", "Ctrl+N", False)
        with mock.patch("calendardesk.dialogs.messagebox.showerror") as err:
            d.save()
        self.assertTrue(err.called)
        self.assertIn("New task", err.call_args[0][1])
        self.assertIn(d, self.app.views)  # still open
        self.assertEqual(d.shortcuts.tree.selection(), ("search",))
        self.assertEqual(self.store.settings["shortcuts"], {})
        d.close()

    def test_old_hotkey_letter_still_counts(self):
        d = self.open_settings()
        self.assertEqual(d.shortcuts.current["toggle_front"]["keys"], "Ctrl+Alt+K")
        d.shortcuts.reset_all()
        self.assertEqual(d.shortcuts.changed_values(), {})
        d.close()

    def test_shortcuts_menu_item_opens_the_tab(self):
        self.app.shortcuts_dialog()
        pump(self.app.root, 50)
        d = next(v for v in self.app.views if hasattr(v, "shortcuts"))
        self.assertEqual(d.nb.select(), str(d.shortcuts))
        d.close()

    # -- recorder -------------------------------------------------------------------
    def press(self, rec, state, key, keysym=None):
        return rec._press(SimpleNamespace(keysym=keysym or key, state=state, keycode=VK[key]))

    def test_recorder_records_a_chord_and_pauses_global_keys(self):
        from calendardesk.shortcut_ui import KeyRecorder
        d = self.open_settings()
        d.shortcuts.select("export")
        rec = KeyRecorder(d.shortcuts, "export")
        self.assertEqual(self.app.hotkey.active, set())  # paused while recording
        self.press(rec, CTRL | SHIFT, "E")
        self.press(rec, CTRL | SHIFT, "E")  # auto-repeat of the held key is not a second step
        self.press(rec, 0, "X")
        self.assertEqual(rec.keys(), "Ctrl+Shift+E, X")
        self.assertEqual(str(rec.use_btn["state"]), "normal")
        rec.use()
        self.assertEqual(d.shortcuts.current["export"], {"keys": "Ctrl+Shift+E, X", "global": False})
        self.assertEqual(len(self.app.hotkey.active), 1)  # resumed with the saved ones
        d.close()

    def test_recorder_blocks_a_taken_key(self):
        from calendardesk.shortcut_ui import KeyRecorder
        d = self.open_settings()
        rec = KeyRecorder(d.shortcuts, "export")
        self.press(rec, CTRL, "N")
        pump(self.app.root, shortcuts.CHORD_MS + 200)
        self.assertEqual(str(rec.use_btn["state"]), "disabled")
        self.assertIn("New task", rec.status["text"])
        rec.close()
        d.close()
