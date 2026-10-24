"""Round 2: timers and Tcl callbacks — the minute tick, stale `after` jobs, traces and the foreground hook."""
import gc
import tempfile
import time
import traceback
import unittest
from datetime import date, datetime
from unittest import mock

from calendardesk import model
from calendardesk.store import Store


def pump(root, ms=50):
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        root.update()
        time.sleep(0.005)


def fake_now(hour, minute, second=0):
    """A datetime class whose now() is today at the given time."""
    fixed = datetime.combine(date.today(), datetime.min.time()).replace(hour=hour, minute=minute, second=second)

    class Fake(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed
    return Fake


def dangling_after_jobs(root):
    """Pending `after` jobs whose Tcl command no longer exists (they would fail, or call a stranger)."""
    tk = root.tk
    bad = []
    for job in tk.splitlist(tk.call("after", "info")):
        script = tk.splitlist(tk.call("after", "info", job))[0]
        cmd = tk.splitlist(script)[0]
        if not tk.call("info", "commands", cmd):
            bad.append(script)
    return bad


class AppTestCase(unittest.TestCase):
    def make(self, *tasks, **settings):
        from calendardesk.app import App
        self.store = Store(tempfile.mkdtemp(prefix="cd-test-"))
        self.store.settings["hotkey"] = "K"  # leave Ctrl+Alt+C to a running CalendarDesk
        self.store.settings.update(settings)
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


class MinuteTickTests(AppTestCase):
    """R2-1: the minute tick moves today's progress bar without rebuilding the whole calendar."""

    def tick_at(self, hour, minute, second=0):
        fake = fake_now(hour, minute, second)
        with mock.patch("calendardesk.app.datetime", fake), mock.patch("calendardesk.desktop_cal.datetime", fake):
            self.app._tick()

    def bar(self):
        c = self.app.calendar.canvas
        items = c.find_withtag("progress")
        self.assertEqual(len(items), 1)
        return items[0], c.coords(items[0])

    def test_minute_tick_moves_bar_only(self):
        app = self.make(*[model.new_task(f"t{i}", date.today()) for i in range(5)])
        c = app.calendar.canvas
        self.tick_at(10, 0)
        before = c.find_all()
        item, (x0, y0, x1, y1) = self.bar()
        self.tick_at(10, 30)
        self.assertEqual(c.find_all(), before)  # nothing was rebuilt
        item2, (nx0, ny0, nx1, ny1) = self.bar()
        self.assertEqual(item2, item)
        self.assertEqual((nx0, ny0, ny1), (x0, y0, y1))
        self.assertGreater(nx1, x1)

    def test_bar_follows_redraw_and_resize(self):
        app = self.make()
        cal = app.calendar
        fake = fake_now(18, 0)
        with mock.patch("calendardesk.desktop_cal.datetime", fake):
            cal.redraw()
        item, (x0, _, x1, _) = self.bar()
        track = [i for i in cal.canvas.find_all() if cal.canvas.type(i) == "line"
                 and cal.canvas.coords(i)[1] == cal.canvas.coords(item)[1] and i != item]
        tx0, _, tx1, _ = cal.canvas.coords(track[0])
        self.assertAlmostEqual((x1 - x0) / (tx1 - tx0), 0.75, places=2)
        cal.win.geometry(f"{cal.win.winfo_width() + 60}x{cal.win.winfo_height() + 40}")
        pump(app.root, 150)  # <Configure> -> full redraw with new items
        self.tick_at(6, 0)
        item, (x0, _, x1, _) = self.bar()
        track = [i for i in cal.canvas.find_all() if cal.canvas.type(i) == "line"
                 and cal.canvas.coords(i)[1] == cal.canvas.coords(item)[1] and i != item]
        tx0, _, tx1, _ = cal.canvas.coords(track[0])
        self.assertAlmostEqual((x1 - x0) / (tx1 - tx0), 0.25, places=2)
        self.assertEqual(self.errors, [])

    def test_next_tick_is_at_the_minute_or_snooze(self):
        app = self.make()
        now = datetime(2026, 10, 24, 10, 0, 45)
        self.assertEqual(app._next_tick_ms(now), 15_000 + 200)
        app.store.data["reminders"]["x|2026-10-24"] = "snooze:2026-10-24T10:00:50"
        self.assertEqual(app._next_tick_ms(now), 5_000 + 200)
        app.store.data["reminders"]["x|2026-10-24"] = "snooze:2026-10-24T09:00:00"  # long past
        self.assertEqual(app._next_tick_ms(now), 15_000 + 200)

    def test_reminder_fires_at_its_minute(self):
        t = model.new_task("call", date.today())
        t.update(time="10:01", remind=True)
        app = self.make(t)
        fired = []
        with mock.patch("calendardesk.app.ReminderPopup", lambda *a: fired.append(a)):
            self.tick_at(10, 0, 59)
            self.assertEqual(fired, [])
            self.tick_at(10, 1, 0)
            self.assertEqual(len(fired), 1)


class StaleTimerTests(AppTestCase):
    """R2-2 / R2-5: closing a window (or the app) leaves no `after` job pointing at a deleted command."""

    def test_dialogs_closed_at_once_leave_no_stale_jobs(self):
        from calendardesk.dialogs import CountdownDialog, CountdownManager, SearchDialog, TaskDialog
        from calendardesk.day_panel import DayPanel
        app = self.make(model.new_task("A", date.today()))
        for make in (lambda: TaskDialog(app), lambda: CountdownDialog(app), lambda: CountdownManager(app),
                     lambda: SearchDialog(app), lambda: DayPanel(app, date.today())):
            make().close()
            app.root.update_idletasks()
            self.assertEqual(dangling_after_jobs(app.root), [])
        pump(app.root, 400)
        self.assertEqual(self.errors, [])

    def test_quit_leaves_no_pending_jobs(self):
        app = self.make()
        app.watch_raised()
        app.calendar.to_front(focus=False)
        root = app.root
        app.quit()
        self.quit_done = True
        self.assertEqual(root.tk.splitlist(root.tk.call("after", "info")), ())


class SettingsLeakTests(AppTestCase):
    """R2-4: a closed Settings window is freed (its variable traces are removed)."""

    def test_closed_settings_are_freed(self):
        from calendardesk.dialogs import SettingsDialog
        app = self.make()
        for _ in range(2):
            d = SettingsDialog(app)
            pump(app.root, 50)
            d.vars["font_size"].set(10)  # a live preview
            pump(app.root, 200)
            d.close()
            pump(app.root, 20)
        del d
        gc.collect()
        self.assertEqual(sum(isinstance(o, SettingsDialog) and o.app is app for o in gc.get_objects()), 0)
        self.assertEqual(self.errors, [])


class ForegroundHookTests(AppTestCase):
    """R2-3: the foreground hook is always removed, and only binds to the Tcl library already loaded."""

    def test_quit_unhooks_even_if_saving_fails(self):
        app = self.make()
        hook = app.calendar._fg_hook
        self.assertTrue(hook.handle)
        with mock.patch.object(app, "save", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                app.quit()
        self.assertIsNone(hook.handle)

    def test_uses_only_the_loaded_tcl_library(self):
        from calendardesk import winapi
        app = self.make()
        with mock.patch.object(winapi.kernel32, "GetModuleHandleW", return_value=None), \
                mock.patch.object(winapi.ctypes, "CDLL", side_effect=AssertionError("must not load a DLL")):
            hook = winapi.ForegroundHook(app.calendar.win, lambda: None)
        self.assertIsNone(hook.handle)  # falls back to the 1 s check

    def test_failed_hook_deletes_its_command(self):
        from calendardesk import winapi
        app = self.make()
        before = set(app.root.tk.splitlist(app.root.tk.call("info", "commands")))
        with mock.patch.object(winapi.user32, "SetWinEventHook", return_value=None):
            hook = winapi.ForegroundHook(app.calendar.win, lambda: None)
        self.assertIsNone(hook.handle)
        self.assertEqual(set(app.root.tk.splitlist(app.root.tk.call("info", "commands"))), before)


if __name__ == "__main__":
    unittest.main()
