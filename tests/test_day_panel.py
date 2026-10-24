import gc
import json
import tempfile
import time
import traceback
import unittest
from datetime import date

from calendardesk import model
from calendardesk.store import Store

DAY = date(2026, 10, 24)


def pump(root, ms=50):
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        root.update()
        time.sleep(0.005)


class PanelTestCase(unittest.TestCase):
    def make(self, *tasks):
        from calendardesk.app import App
        self.store = Store(tempfile.mkdtemp(prefix="cd-test-"))
        self.store.settings["hotkey"] = "K"  # leave Ctrl+Alt+C to a running CalendarDesk
        self.store.data["tasks"].extend(tasks)
        self.app = App(self.store, tray=False)
        self.errors = []
        self.app.root.report_callback_exception = lambda *exc: self.errors.append(
            "".join(traceback.format_exception(*exc)))
        pump(self.app.root, 200)
        return self.app

    def tearDown(self):
        if getattr(self, "app", None) and not getattr(self, "quit_done", False):
            self.app.quit()

    def task(self, title, **kw):
        t = model.new_task(title, DAY)
        t.update(kw)
        return t


class ClickAfterDeferredRefreshTests(PanelTestCase):
    """BUG-1: a click that commits an edit while a refresh is pending must not kill the panel."""

    def _dirty_and_pending(self, edit):
        a, b = self.task("A", items=[model.new_item("x")]), self.task("B", items=[model.new_item("y")])
        app = self.make(a, b)
        p = app.open_day(DAY)
        pump(app.root, 200)
        edit(p.cards[a["id"]])
        app.set_date_color(DAY, "#ff6b6b")  # a swatch click: refresh deferred while A is unsaved
        pump(app.root)
        self.assertTrue(p._pending)
        return app, p, a, b

    def test_task_check(self):
        def edit(card):
            card.title.focus_force()
            pump(self.app.root)
            card.title.insert("end", " edited")
        app, p, a, b = self._dirty_and_pending(edit)
        p.cards[b["id"]].check.event_generate("<Button-1>", x=5, y=5)
        pump(app.root, 800)
        self.assertEqual(a["title"], "A edited")
        self.assertTrue(b["done"])
        self.assertEqual(p.animating, set())
        self.assertEqual(self.errors, [])
        app.toggle_done(a, DAY, True)  # the panel keeps refreshing afterwards
        pump(app.root, 200)
        self.assertFalse(p._pending)
        p.cards[b["id"]].check.event_generate("<Button-1>", x=5, y=5)
        pump(app.root, 600)
        self.assertFalse(b["done"])

    def test_item_check(self):
        def edit(card):
            card.note.insert("end", "note")
        app, p, a, b = self._dirty_and_pending(edit)
        iid = b["items"][0]["id"]
        p.cards[b["id"]].item_checks[iid].event_generate("<Button-1>", x=5, y=5)
        pump(app.root, 800)
        self.assertEqual(a["note"], "note")
        self.assertTrue(model.item_done(b, b["items"][0], DAY))
        self.assertEqual(p.animating, set())
        self.assertEqual(self.errors, [])


class PanelLeakTests(PanelTestCase):
    def test_closed_panels_are_freed(self):
        """BUG-2: closing a panel frees it (and its fonts)."""
        from calendardesk.day_panel import DayPanel
        ts = [self.task(f"T{i}", note="n", items=[model.new_item("i")]) for i in range(3)]
        app = self.make(*ts)
        fonts = len(app.root.tk.splitlist(app.root.tk.call("font", "names")))
        for _ in range(3):
            p = app.open_day(DAY)
            pump(app.root, 60)
            p.close()
            pump(app.root, 20)
        del p
        gc.collect()
        self.assertEqual(sum(isinstance(o, DayPanel) and o.app is app for o in gc.get_objects()), 0)
        self.assertEqual(len(app.root.tk.splitlist(app.root.tk.call("font", "names"))), fonts)


class AddBoxTests(PanelTestCase):
    def test_add_box_text_survives_refresh(self):
        """BUG-3: typing in a card's add-item box is kept when the panel rebuilds."""
        a, b = self.task("A", items=[model.new_item("x")]), self.task("B")
        app = self.make(a, b)
        p = app.open_day(DAY)
        pump(app.root, 200)
        ca = p.cards[a["id"]]
        ca.add_entry.focus_force()
        pump(app.root)
        ca.add_entry.insert(0, "buy milk")
        p.cards[b["id"]].check.event_generate("<Button-1>", x=5, y=5)
        pump(app.root, 700)
        self.assertTrue(b["done"])
        na = p.cards[a["id"]]
        self.assertIsNot(na, ca)  # really rebuilt
        self.assertEqual(na.add_entry.get(), "buy milk")
        self.assertEqual([i["text"] for i in a["items"]], ["x"])

    def test_added_item_leaves_box_empty(self):
        a = self.task("A", items=[model.new_item("x")])
        app = self.make(a)
        p = app.open_day(DAY)
        pump(app.root, 200)
        p.cards[a["id"]].add_entry.insert(0, "y")
        p.cards[a["id"]].add_item()
        pump(app.root, 50)
        self.assertEqual([i["text"] for i in a["items"]], ["x", "y"])
        self.assertEqual(p.cards[a["id"]].add_entry.get(), "")


class DialogDateChangeTests(PanelTestCase):
    def test_item_ticks_reset_with_task_ticks(self):
        """BUG-7: moving a repeating task's start date clears its items' ticks too."""
        from calendardesk.dialogs import TaskDialog
        r = self.task("daily", repeat="daily", items=[model.new_item("x"), model.new_item("y")])
        app = self.make(r)
        app.toggle_done(r, DAY, True)
        dlg = TaskDialog(app, r, DAY)
        pump(app.root, 100)
        dlg.v_date.set("23-10-2026")
        dlg.save()
        pump(app.root, 100)
        self.assertFalse(model.is_done(r, DAY))
        self.assertEqual(model.progress(r, DAY), (0, 2))


class QuitSavesPanelTests(PanelTestCase):
    def test_quit_commits_open_panel_edits(self):
        """EXTRA-1: Exit saves typing that is still inside a day panel."""
        a = self.task("A", note="n")
        app = self.make(a)
        p = app.open_day(DAY)
        pump(app.root, 200)
        card = p.cards[a["id"]]
        card.title.focus_force()
        pump(app.root)
        card.title.insert("end", " edited")
        card.note.insert("end", " more")
        app.quit()
        self.quit_done = True
        with open(self.store.path, encoding="utf-8") as f:
            saved = json.load(f)["tasks"][0]
        self.assertEqual((saved["title"], saved["note"]), ("A edited", "n more"))


if __name__ == "__main__":
    unittest.main()
