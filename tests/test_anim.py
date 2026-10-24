import tempfile
import time
import tkinter as tk
import unittest
from datetime import date
from types import SimpleNamespace

from calendardesk import model, theme
from calendardesk.anim import TickAnimation
from calendardesk.store import Store


def pump(root, ms):
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        root.update()
        time.sleep(0.005)


class TickAnimationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def _run(self, ticking):
        c = tk.Canvas(self.root, width=200, height=40)
        text = c.create_text(30, 10, text="Submit report", anchor="nw")
        calls = []
        a = TickAnimation(c, (10, 10, 24, 24), text, "#4dabf7", "#888888", lambda: calls.append(1), ticking=ticking)
        a.start()
        self.assertTrue(a.running)
        self.assertEqual(calls, [])
        return c, a, calls

    def test_tick_finishes_once_and_cleans_up(self):
        c, a, calls = self._run(True)
        pump(self.root, 150)
        self.assertEqual(calls, [])  # still animating at 150 ms
        pump(self.root, 400)
        self.assertEqual(calls, [1])
        self.assertFalse(a.running)
        self.assertEqual(c.find_withtag("tickanim"), ())
        pending = self.root.tk.splitlist(self.root.tk.call("after", "info"))
        self.assertNotIn(a._job, pending)
        pump(self.root, 100)
        self.assertEqual(calls, [1])
        c.destroy()

    def test_untick_is_quick(self):
        c, a, calls = self._run(False)
        pump(self.root, 250)
        self.assertEqual(calls, [1])
        c.destroy()

    def test_canvas_destroyed_mid_animation(self):
        c, a, calls = self._run(True)
        pump(self.root, 50)
        c.destroy()
        pump(self.root, 400)  # must not raise
        self.assertFalse(a.running)


class CalendarClickTests(unittest.TestCase):
    def test_double_click_on_check_during_animation_toggles_once(self):
        from calendardesk.app import App
        store = Store(tempfile.mkdtemp(prefix="cd-test-"))
        store.settings["hotkey"] = "K"  # leave Ctrl+Alt+C to a running CalendarDesk
        today = date.today()
        t = model.new_task("Submit report", today)
        t["items"] = [model.new_item("a"), model.new_item("b"), model.new_item("c")]
        store.data["tasks"].append(t)
        app = App(store, tray=False)
        try:
            cal = app.calendar
            pump(app.root, 300)
            check = next(h for h in cal.hits if h[4] == "check" and h[6]["id"] == t["id"])
            e = SimpleNamespace(x=(check[0] + check[2]) / 2, y=(check[1] + check[3]) / 2)
            cal._click(e)
            pump(app.root, 60)
            cal._click(e)
            pump(app.root, 600)
            self.assertTrue(model.is_done(t, today))
            self.assertEqual(cal.animating, set())
            self.assertEqual(model.progress(t, today), (3, 3))
        finally:
            app.quit()

    def test_progress_count_is_drawn(self):
        from calendardesk.app import App
        store = Store(tempfile.mkdtemp(prefix="cd-test-"))
        store.settings["hotkey"] = "K"  # leave Ctrl+Alt+C to a running CalendarDesk
        today = date.today()
        t = model.new_task("Submit report", today)
        t["items"] = [model.new_item("a"), model.new_item("b"), model.new_item("c")]
        model.set_item_done(t, t["items"][0], today, True)
        store.data["tasks"].append(t)
        app = App(store, tray=False)
        try:
            pump(app.root, 300)
            c = app.calendar.canvas
            texts = [c.itemcget(i, "text") for i in c.find_all() if c.type(i) == "text"]
            self.assertIn("1/3", texts)
        finally:
            app.quit()
