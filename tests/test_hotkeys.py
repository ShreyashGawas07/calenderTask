import queue
import time
import unittest

from calendardesk import winapi
from calendardesk.winapi import CHORD_ID, WM_HOTKEY, user32

# Combinations nobody uses, so the test never clashes with a running program.
CAS = 0x1 | 0x2 | 0x4  # Ctrl+Alt+Shift
F22, F23, F24 = 0x85, 0x86, 0x87


class HotkeyThreadTests(unittest.TestCase):
    def setUp(self):
        self.fired = queue.Queue()
        self.t = winapi.HotkeyThread([("single", ((CAS, F22),)), ("chord", ((CAS, F23), (0, F24)))],
                                     self.fired.put, chord_ms=150)
        self.t.start()
        self.assertTrue(self.t.registered.wait(2))

    def tearDown(self):
        self.t.stop()
        self.t.join(2)
        self.assertFalse(self.t.is_alive())

    def press(self, hid):
        user32.PostThreadMessageW(self.t.tid, WM_HOTKEY, hid, 0)

    def got(self, wait=0.3):
        try:
            return self.fired.get(timeout=wait)
        except queue.Empty:
            return None

    def test_registers_first_steps(self):
        self.assertEqual(self.t.failed, [])
        self.assertEqual(self.t.active, {(CAS, F22), (CAS, F23)})
        self.assertTrue(winapi.probe_hotkey(CAS, F22))  # ours now, so taken

    def test_single(self):
        self.press(self.t._ids[(CAS, F22)])
        self.assertEqual(self.got(), "single")

    def test_chord_second_key_in_time(self):
        self.press(self.t._ids[(CAS, F23)])
        self.assertIsNone(self.got(0.03))  # waiting for the second key
        self.assertTrue(self.t._chord)
        self.press(CHORD_ID)
        self.assertEqual(self.got(), "chord")
        self.assertEqual(self.t._chord, {})

    def test_chord_times_out_and_releases_keys(self):
        self.press(self.t._ids[(CAS, F23)])
        time.sleep(0.4)
        self.assertEqual(self.t._chord, {})
        self.assertFalse(winapi.probe_hotkey(0, F24))  # the temporary key is free again
        self.press(CHORD_ID)
        self.assertIsNone(self.got())

    def test_set_bindings_replaces_and_reports_failures(self):
        self.assertTrue(user32.RegisterHotKey(None, 77, CAS, F24))  # someone else holds this one
        try:
            failed = self.t.set_bindings([("x", ((CAS, F24),)), ("y", ((CAS, F22),))])
        finally:
            user32.UnregisterHotKey(None, 77)
        self.assertEqual(failed, ["x"])
        self.assertEqual(self.t.active, {(CAS, F22)})
        self.assertFalse(winapi.probe_hotkey(CAS, F23))  # old one released
        self.assertEqual(self.t.set_bindings([]), [])
        self.assertFalse(winapi.probe_hotkey(CAS, F22))

    def test_probe_free_combo(self):
        self.assertFalse(winapi.probe_hotkey(CAS, 0x7F))  # F16
