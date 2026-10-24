"""Round 3: repeated redraws must not leave Tcl callback commands behind (memory creeping up)."""
import unittest
from datetime import date

from calendardesk import model
from tests.test_timers import AppTestCase, pump


def tcl_commands(root):
    return len(root.tk.splitlist(root.tk.call("info", "commands")))


class RedrawLeakTests(AppTestCase):
    """R3-1: `canvas.delete("all")` frees items but not the Python callbacks of their tag binds."""

    def growth(self, redraw, times=50):
        root = self.app.root
        redraw()
        pump(root, 50)
        before = tcl_commands(root)
        for _ in range(times):
            redraw()
        pump(root, 50)
        return tcl_commands(root) - before

    def test_calendar_redraw_registers_no_commands(self):
        app = self.make(*[model.new_task(f"t{i}", date.today()) for i in range(30)])
        app.calendar.go(1)  # not this month, so the "Today" button is drawn too
        self.assertLessEqual(self.growth(app.calendar.redraw), 1)  # was +20 per redraw
        self.assertEqual(self.errors, [])

    def test_mini_calendar_and_cards_register_no_commands(self):
        app = self.make(model.new_task("A", date.today()))
        app.toggle_mini()
        pump(app.root, 100)
        self.assertLessEqual(self.growth(app.mini.redraw), 1)
        self.assertLessEqual(self.growth(app.refresh_all), 1)  # a pending `after` may fire meanwhile

    def test_day_panel_commands_are_freed_with_it(self):
        app = self.make(*[model.new_task(f"t{i}", date.today()) for i in range(10)])

        def open_close():
            panel = app.open_day(date.today())
            pump(app.root, 30)
            panel.close()
        self.assertLessEqual(self.growth(open_close, times=10), 1)


class HeaderButtonTests(AppTestCase):
    """The header buttons still work, with a hand cursor, after the binds moved to __init__."""

    def button(self, label):
        c = self.app.calendar.canvas
        item = next(i for i in c.find_all() if c.type(i) == "text" and c.itemcget(i, "text") == label)
        x0, y0, x1, y1 = c.bbox(item)
        return c, (x0 + x1) // 2, (y0 + y1) // 2

    def click(self, label):
        c, x, y = self.button(label)
        c.event_generate("<Motion>", x=x, y=y)
        c.event_generate("<ButtonPress-1>", x=x, y=y)
        c.event_generate("<ButtonRelease-1>", x=x, y=y)
        pump(self.app.root, 30)

    def test_next_prev_today_buttons(self):
        app = self.make()
        cal = app.calendar
        start = (cal.year, cal.month)
        self.click("›")
        self.assertEqual((cal.year, cal.month), model_shift(start, 1))
        self.click("›")
        self.assertEqual((cal.year, cal.month), model_shift(start, 2))
        self.click("‹")
        self.assertEqual((cal.year, cal.month), model_shift(start, 1))
        self.click("Today")
        self.assertEqual((cal.year, cal.month), start)
        self.assertEqual(self.errors, [])

    def test_hand_cursor_on_buttons_and_size_cursor_on_grip(self):
        app = self.make()
        c, x, y = self.button("+ Task")
        c.event_generate("<Motion>", x=x, y=y)
        pump(app.root, 20)
        self.assertEqual(str(c.cget("cursor")), "hand2")
        c.event_generate("<Motion>", x=c.winfo_width() // 2, y=c.winfo_height() // 2)
        pump(app.root, 20)
        self.assertEqual(str(c.cget("cursor")), "")
        c.event_generate("<Motion>", x=c.winfo_width() - 3, y=c.winfo_height() - 3)
        pump(app.root, 20)
        self.assertEqual(str(c.cget("cursor")), "size_nw_se")
        self.assertEqual(self.errors, [])

    def test_task_and_search_buttons_call_the_app(self):
        app = self.make()
        calls = []
        app.edit_task = lambda **kw: calls.append(("task", kw.get("day")))
        app.search = lambda: calls.append(("search", None))
        app.calendar.redraw()  # the buttons pick up the replaced methods
        self.click("+ Task")
        self.click("Search")
        self.assertEqual(calls, [("task", date.today()), ("search", None)])


def model_shift(ym, delta):
    from calendardesk.desktop_cal import shift_month
    return shift_month(ym[0], ym[1], delta)


if __name__ == "__main__":
    unittest.main()
