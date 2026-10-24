"""Scripted UI check for the day panel (a script, not part of unittest discovery).

    .venv\\Scripts\\python tests\\ui_day_panel.py

Runs on a temporary data folder. Exits 1 on the first failed check.
"""
import os
import sys
import tempfile
import time
import traceback
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calendardesk import model  # noqa: E402
from calendardesk.app import App  # noqa: E402
from calendardesk.day_panel import DayPanel  # noqa: E402
from calendardesk.dialogs import TaskDialog  # noqa: E402
from calendardesk.store import Store  # noqa: E402

DAY = date(2026, 10, 24)
errors = []


def pump(app, ms=50):
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        app.root.update()
        time.sleep(0.005)


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        errors.append(what)


def find(app, title):
    return next(t for t in app.store.data["tasks"] if t["title"] == title)


def press_return(widget, app):
    widget.focus_force()
    pump(app, 30)
    widget.event_generate("<Return>")
    pump(app, 30)


def main():
    store = Store(tempfile.mkdtemp(prefix="cd-ui-"))
    store.settings["hotkey"] = "K"
    app = App(store, tray=False)
    app.root.report_callback_exception = lambda *exc: errors.append("".join(traceback.format_exception(*exc)))
    try:
        pump(app, 200)
        panel = app.open_day(DAY)
        check(isinstance(panel, DayPanel), "open_day opens a DayPanel")
        check(app.open_day(DAY) is panel, "re-opening the same day focuses the existing panel")

        # smart add
        panel.add_box.entry.insert(0, "report 10am")
        pump(app)
        check("10:00" in panel.add_box.preview.cget("text"), "preview shows the understood time")
        press_return(panel.add_box.entry, app)
        panel.add_box.entry.insert(0, "call mom 7pm")
        panel.add_box.submit()
        pump(app)
        report, mom = find(app, "report"), find(app, "call mom")
        check((report["time"], report["date"], mom["time"]) == ("10:00", "2026-10-24", "19:00"),
              "smart add saved title, date and time")

        # checklist items
        panel.cards[report["id"]].expand()  # a task without items or notes starts collapsed
        for text in ("a", "b", "c"):
            card = panel.cards[report["id"]]
            card.add_entry.insert(0, text)
            press_return(card.add_entry, app)
        check([i["text"] for i in report.get("items", [])] == ["a", "b", "c"], "items a, b, c added")
        card = panel.cards[report["id"]]
        check(app.root.focus_get() is card.add_entry, "focus stays in '+ add item' after adding")

        a = report["items"][0]
        card.click_item(a["id"])
        card.click_item(a["id"])  # second click during the animation is ignored
        pump(app, 500)
        check(model.progress(report, DAY) == (1, 3), "ticking item a gives 1/3")
        cal = app.calendar.canvas
        texts = [cal.itemcget(i, "text") for i in cal.find_all() if cal.type(i) == "text"]
        if DAY.month == date.today().month and DAY.year == date.today().year:
            check("1/3" in texts, "calendar shows 1/3")

        panel.cards[report["id"]].click_check()
        pump(app, 500)
        check(model.is_done(report, DAY) and model.progress(report, DAY) == (3, 3), "ticking the task ticks all items")

        # title edit in place
        card = panel.cards[mom["id"]]
        card.title.delete(0, "end")
        card.title.insert(0, "call mom tonight")
        press_return(card.title, app)
        check(mom["title"] == "call mom tonight", "title edited in place")
        card = panel.cards[mom["id"]]
        card.title.delete(0, "end")
        press_return(card.title, app)
        check(mom["title"] == "call mom tonight", "an emptied title is not saved")

        # notes with a numbered list
        card = panel.cards[mom["id"]]
        card.expand()
        card = panel.cards[mom["id"]]
        card.note.focus_force()
        card.note.insert("end", "1. x")
        card.note.newline()
        pump(app, 800)
        check(mom["note"] == "1. x", f"numbered note saved as '1. x' (got {mom['note']!r})")

        # move to next day
        panel.cards[report["id"]].move_next_day()
        pump(app)
        check(report["date"] == "2026-10-25", "move to next day")
        check(report["id"] not in panel.cards, "moved task leaves the panel")

        # same task in the dialog and the panel: last save wins, panel follows
        dlg = TaskDialog(app, mom, DAY)
        dlg.v_title.set("dialog title")
        card = panel.cards[mom["id"]]
        card.title.delete(0, "end")
        card.title.insert(0, "panel title")
        press_return(card.title, app)
        dlg.save()
        pump(app, 100)
        check(mom["title"] == "dialog title", "dialog save wins")
        check(panel.cards[mom["id"]].title.get() == "dialog title", "panel shows the dialog's title")

        # speed with 30 tasks
        for i in range(30):
            t = model.new_task(f"task {i}", DAY)
            t["items"] = [model.new_item("x"), model.new_item("y")]
            t["note"] = "- one\n- **two**"
            app.store.data["tasks"].append(t)
        panel.close()
        t0 = time.perf_counter()
        panel = app.open_day(DAY)
        app.root.update_idletasks()
        ms = (time.perf_counter() - t0) * 1000
        check(ms < 300, f"panel opens with 30+ tasks in {ms:.0f} ms (< 300)")
        panel.close()
        pump(app, 100)
    except Exception:
        errors.append(traceback.format_exc())
    finally:
        app.quit()
    for e in errors:
        if "\n" in e:
            print(e)
    print("PASS" if not errors else f"FAIL ({len(errors)})")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
