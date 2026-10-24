"""Smart typing in the + Task (New task) dialog."""
import os
import tempfile
import time
import unittest
from datetime import date, timedelta
from unittest import mock

from calendardesk.store import Store


def pump(root, ms=50):
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        root.update()
        time.sleep(0.005)


class NewTaskSmartTypingTests(unittest.TestCase):
    def setUp(self):
        from calendardesk.app import App
        from calendardesk.dialogs import TaskDialog
        self.store = Store(tempfile.mkdtemp(prefix="cd-test-"))
        self.store.settings["hotkey"] = "K"  # leave Ctrl+Alt+C to a running CalendarDesk
        self.app = App(self.store, tray=False)
        self.today = date.today()
        self.d = TaskDialog(self.app, day=self.today)
        pump(self.app.root)

    def tearDown(self):
        if self.d.winfo_exists():
            self.d.close()
        self.app.quit()
        log = os.path.join(self.store.folder, "error.log")
        self.assertFalse(os.path.exists(log), open(log).read() if os.path.exists(log) else "")

    def type(self, text):
        self.d.v_title.set(text)
        pump(self.app.root, 30)

    def test_call_mom_at_7_am(self):
        self.type("call mom at 7 am")
        self.assertEqual(self.d.v_time.get(), "07:00")
        self.assertIn("07:00", self.d.smart["text"])
        self.d.save()
        [t] = self.store.data["tasks"]
        self.assertEqual((t["title"], t["time"], t["date"]), ("call mom", "07:00", self.today.isoformat()))

    def test_date_repeat_and_reminder_fill_in(self):
        self.type("standup every mon and thu 9:30 remind me")
        self.assertEqual(self.d.v_repeat.get(), "weekly")
        self.assertEqual([v.get() for v in self.d.v_days], [True, False, False, True, False, False, False])
        self.assertTrue(self.d.v_remind.get())
        self.type("dentist tomorrow 3pm")
        self.assertEqual(self.d.v_date.get(), (self.today + timedelta(days=1)).strftime("%d-%m-%Y"))
        self.assertEqual(self.d.v_repeat.get(), "none")  # undone as the words went away
        self.assertFalse(self.d.v_remind.get())

    def test_fields_typed_by_hand_are_kept(self):
        self.d.v_time.set("08:15")
        self.type("call mom 7pm")
        self.assertEqual(self.d.v_time.get(), "08:15")
        self.d.save()
        self.assertEqual(self.store.data["tasks"][0]["time"], "08:15")

    def test_plain_text_is_saved_as_typed(self):
        self.type("buy 3/4 cup flour")
        self.assertEqual(self.d.smart["text"], "")
        self.d.save()
        self.assertEqual(self.store.data["tasks"][0]["title"], "buy 3/4 cup flour")

    def test_editing_an_existing_task_never_reparses(self):
        from calendardesk import model
        from calendardesk.dialogs import TaskDialog
        t = model.new_task("meet at 7", self.today)
        self.store.data["tasks"].append(t)
        e = TaskDialog(self.app, task=t)
        pump(self.app.root)
        e.v_title.set("meet at 8 tomorrow")
        e.save()
        self.assertEqual((t["title"], t.get("time"), t["date"]), ("meet at 8 tomorrow", None, self.today.isoformat()))

    def test_half_typed_interval_does_not_break_typing(self):
        self.d.v_interval.set("")  # what an emptied spinbox holds
        with mock.patch("calendardesk.dialogs.messagebox"):
            self.type("water every 2 days")
