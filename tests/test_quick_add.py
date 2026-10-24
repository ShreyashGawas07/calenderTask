"""The calendar's inline quick-add box."""
import tempfile
import time
import unittest
from types import SimpleNamespace

from calendardesk.store import Store


def pump(root, ms=50):
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        root.update()
        time.sleep(0.005)


class QuickAddBoxTests(unittest.TestCase):
    def setUp(self):
        from calendardesk.app import App
        self.store = Store(tempfile.mkdtemp(prefix="cd-test-"))
        self.store.settings["hotkey"] = "K"  # leave Ctrl+Alt+C to a running CalendarDesk
        self.app = App(self.store, tray=False)
        self.cal = self.app.calendar
        pump(self.app.root, 200)
        self.cal.quick_add_today()
        pump(self.app.root)

    def tearDown(self):
        self.app.quit()

    def click_elsewhere(self):
        self.cal._click(SimpleNamespace(x=5, y=self.cal.canvas.winfo_height() - 5))
        pump(self.app.root)

    def test_empty_box_closes_on_a_click_elsewhere(self):
        self.assertIsNotNone(self.cal.quick)
        self.click_elsewhere()
        self.assertIsNone(self.cal.quick)
        self.assertEqual(self.store.data["tasks"], [])
        self.assertEqual(self.cal.canvas.winfo_children(), [])  # box and its preview line are gone

    def test_typed_text_is_added_on_a_click_elsewhere(self):
        self.cal.quick.insert(0, "buy milk")
        self.click_elsewhere()
        self.assertIsNone(self.cal.quick)
        self.assertEqual([t["title"] for t in self.store.data["tasks"]], ["buy milk"])

    def test_click_only_closes_the_box(self):
        self.click_elsewhere()
        self.assertIsNone(self.cal._click_job)  # nothing else was started by that click

    def test_opening_again_replaces_the_box(self):
        first = self.cal.quick
        self.cal.quick_add_today()
        pump(self.app.root)
        self.assertIsNot(self.cal.quick, first)
        self.assertEqual(len(self.cal.canvas.winfo_children()), 2)  # one box and one preview line
