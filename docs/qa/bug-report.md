# Bug report — round 1

Summary line: 8 findings (0 critical, 2 high, 4 medium, 2 low).

All scripts import this helper (`qa-scratch/h.py`). It uses a temp data folder, sets hotkey "K", and collects callback exceptions in `errors`:

```python
import os, sys, tempfile, time, traceback, json
sys.path.insert(0, r"C:/Users/shreyash/Downloads/CalenderTask")
from datetime import date, timedelta
from calendardesk import model
from calendardesk.app import App
from calendardesk.store import Store
DAY = date(2026, 10, 24)
errors = []
def make(tasks=()):
    store = Store(tempfile.mkdtemp(prefix="cd-qa-")); store.settings["hotkey"] = "K"
    store.data["tasks"].extend(tasks)
    app = App(store, tray=False)
    app.root.report_callback_exception = lambda *exc: errors.append("".join(traceback.format_exception(*exc)))
    return app
def pump(app, ms=50):
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end: app.root.update(); time.sleep(0.005)
def task(title, **kw):
    t = model.new_task(title, DAY); t.update(kw); return t
```

---

### BUG-1: Panel checkbox crashes, then the panel stops ticking and refreshing until it is closed
- Severity: high
- Where: calendardesk/day_panel.py:245-252 (`click_check`), 259-268 (`click_item`); trigger at day_panel.py:406-407 (`own_save` rebuilds while a refresh is pending)
- Steps to reproduce: in a panel, type in card A's title (don't press Enter) or in its note (within 600 ms). Then click a date-colour swatch or "Clear". These buttons don't take focus, so A stays dirty and the refresh is deferred (`_pending = True`). Then click card B's checkbox (or one of its item boxes). `click_check` calls `commit_all()`, then `own_save()` sees `_pending` and rebuilds the panel. This destroys B's CheckBox canvas. `TickAnimation(self.check, …).start()` then draws on a dead widget. `start()` does not catch the TclError (only `_step` does). The key stays in `panel.animating` for good, so `refresh()` defers every later change, `own_save` never rebuilds, and B's checkbox is ignored.
  ```python
  from h import *
  a, b = task("A"), task("B")
  app = make([a, b]); pump(app, 200)
  p = app.open_day(DAY); pump(app, 200)
  ca = p.cards[a["id"]]; ca.title.focus_force(); pump(app)
  ca.title.insert("end", " edited")
  app.set_date_color(DAY, "#ff6b6b"); pump(app)          # swatch click
  print("pending:", p._pending, "dirty:", p._dirty())
  p.cards[b["id"]].check.event_generate("<Button-1>", x=5, y=5); pump(app, 800)
  print("B done:", b["done"], "| A title:", a["title"], "| animating:", p.animating)
  app.toggle_done(a, DAY, True); pump(app, 200)
  print("A done in data:", a["done"], "| panel pending (refresh skipped):", p._pending)
  p.cards[b["id"]].check.event_generate("<Button-1>", x=5, y=5); pump(app, 800)
  print("second click on B -> B done:", b["done"]); print(len(errors), errors[0].splitlines()[-1])
  app.quit()
  ```
- Expected: B is ticked with the animation, and the panel keeps refreshing.
- Actual:
  ```
  pending: True dirty: True
  B done: False | A title: A edited | animating: {('726bc4e59524', datetime.date(2026, 10, 24))}
  A done in data: True | panel pending (refresh skipped): True
  second click on B -> B done: False
  ERRORS: 1  _tkinter.TclError: invalid command name ".!daypanel.!frame3.!canvas.!frame.!taskcard2.!frame.!checkbox"
  ```
  The item variant (note dirty + swatch, then click an item box of another card) behaves the same way: the item is not ticked, its key is stuck in `animating`, and the same TclError is logged.
- Suggested fix direction: in `click_check` / `click_item`, look up the card and box again after `commit_all()` (or don't rebuild from `own_save` while a click is being handled). Make `TickAnimation.start()` survive a dead canvas: catch TclError, call `on_done`, and always discard the key.

### BUG-2: Every day-panel open leaks the whole panel (widgets' Python objects + 17 Tk fonts per open)
- Severity: high (breaks the "keep the PC fast" rule; memory grows the longer the app runs)
- Where: calendardesk/day_panel.py:48 (`self.var.trace_add("write", …)` in SmartEntry). The trace callback is registered with Tcl and never removed, so the Tcl interpreter keeps SmartEntry, and through it the DayPanel, all TaskCards and their fonts (5 panel fonts + 1 bold font per RichNote).
- Steps to reproduce:
  ```python
  from h import *; import gc
  from calendardesk.day_panel import DayPanel
  ts = [task(f"T{i}", note="n", items=[model.new_item("i1")]) for i in range(12)]
  app = make(ts); pump(app, 300)
  for n in range(20):
      p = app.open_day(DAY); pump(app, 60); p.close(); pump(app, 20)
  del p; gc.collect()
  print("DayPanel alive:", sum(isinstance(o, DayPanel) for o in gc.get_objects()),
        "fonts:", len(app.root.tk.splitlist(app.root.tk.call("font", "names"))))
  app.quit()
  ```
- Expected: 0 DayPanel objects alive after closing; the font count goes back to the baseline (23).
- Actual: `DayPanel alive after 20 cycles: 20 fonts: 363`. Over 100 open/close cycles with 12 tasks: working set 52.9 MB → 72.6 MB, private bytes 34.9 MB → 53.1 MB, 1200 TaskCards alive, 1723 Tk fonts. When the traces are removed in `close()` (`for m, cb in var.trace_info(): var.trace_remove(m, cb)`), the same run gives `DayPanel alive: 0 fonts: 23`.
- Suggested fix direction: remove the trace in `DayPanel.close()`/`destroy()`, or have SmartEntry use a `<KeyRelease>` binding instead of a variable trace.

### BUG-3: Typing a new checklist item is wiped when anything refreshes the panel (e.g. ticking another task)
- Severity: medium (typed text lost)
- Where: calendardesk/day_panel.py:177. The add-item box is registered with `dirty = lambda: False`, so `refresh()` → `rebuild()` destroys it and its text right away.
- Steps to reproduce:
  ```python
  from h import *
  a, b = task("A", items=[model.new_item("x")]), task("B")
  app = make([a, b]); pump(app, 200)
  p = app.open_day(DAY); pump(app, 200)
  ca = p.cards[a["id"]]; ca.add_entry.focus_force(); pump(app)
  ca.add_entry.insert(0, "buy milk")                       # Enter not pressed yet
  p.cards[b["id"]].check.event_generate("<Button-1>", x=5, y=5); pump(app, 700)
  na = p.cards[a["id"]]
  print("B done:", b["done"], "| A add box now:", repr(na.add_entry.get()), "| items:", [i["text"] for i in a["items"]])
  app.quit()
  ```
- Expected: "buy milk" is still in the add box (or the refresh waits).
- Actual: `B done: True | A add box now: '' | focus: True | items: ['x']`. The same happens after any non-own refresh: item ticks in the panel (`click_item` → `app.changed()`), date colour, a TaskDialog save, or a tick on the desktop calendar.
- Suggested fix direction: count a non-empty add box as dirty (`lambda: bool(self.add_entry.get().strip())`), or carry its text across the rebuild.

### BUG-4: Notes with a line starting with a number + ". " are rewritten ("2024. was a good year" → "1. was a good year")
- Severity: medium (the user's note text changes on the next edit)
- Where: calendardesk/richnote.py:7, 32, 54-55, 92-93. Any line matching `\d+\. ` is turned into a numbered-list item and renumbered from 1 in both `load()` and `to_markdown()`.
- Steps to reproduce: a task with note `2024. was a good year` (or `100. items`, or an old list `3. third\n4. fourth`). Open the day panel and type anything in the note:
  ```python
  from h import *
  notes = ["2024. was a good year", "100. items", "3. third\n4. fourth"]
  ts = [task(f"T{i}", note=n) for i, n in enumerate(notes)]
  app = make(ts); pump(app, 200); p = app.open_day(DAY); pump(app, 400)
  for t, orig in zip(ts, notes):
      c = p.cards[t["id"]]; shown = c.note.get("1.0", "end-1c")
      c.note.insert("1.end", " X"); c.commit_note()
      print(repr(orig), "shown=", repr(shown), "saved=", repr(t["note"]))
  app.quit()
  ```
- Expected: the original text is kept, and only " X" is added.
- Actual:
  ```
  '2024. was a good year' shown= '1. was a good year'  saved= '1. was a good year X'
  '100. items'            shown= '1. items'            saved= '1. items X'
  '3. third\n4. fourth'   shown= '1. third\n2. fourth'  saved= '1. third X\n2. fourth'
  ```
- Suggested fix direction: only treat a line as a numbered item when it is part of a list the user made, for example by accepting only the expected number in sequence (1, then n+1). Otherwise keep the line's own number.

### BUG-5: Smart typing turns ordinary numbers into dates/times and removes them from the title
- Severity: medium (the task silently lands on another day, possibly months away, and words are lost from the title)
- Where: calendardesk/model.py:254-257 (`d/m` and `d-m` date), 279-280 (`h.mm` time with `.`), 261/270 (ISO dates not handled)
- Steps to reproduce (`parse_quick(text, date(2026,10,24))`):
  ```
  'buy 3/4 cup flour'     -> title='buy cup flour' date=2027-04-03
  'read pages 1-12'       -> title='read pages'    date=2026-12-01
  'chapter 2/3 done'      -> title='chapter done'  date=2027-03-02
  'score 3-1'             -> title='score'         date=2027-01-03
  'pay 2.50 for coffee'   -> title='pay for coffee' time=02:50
  'version 2.10 release'  -> title='version release' time=02:10
  '2026-11-05 dentist'    -> title='2026- dentist' date=2027-05-11   (ISO date read as 11 May 2027)
  ```
- Expected: fractions, page ranges, scores and prices stay in the title. An ISO date `2026-11-05` gives 5 Nov 2026, the format TaskDialog accepts.
- Actual: as above. The item appears on a far-away day ("added to Sat 03 Apr" in the panel).
- Suggested fix direction: recognise `YYYY-MM-DD` before `d-m`. Accept a bare `d/m` or `d-m` only with a date-like context (`on`, a year, or at the end of the text). Don't treat `h.mm` as a time without `at` or am/pm.

### BUG-6: Smart typing reads the common words "sun" and "sat" as weekdays
- Severity: medium
- Where: calendardesk/model.py:156 (`_WD`) and 268 (bare weekday `take`)
- Steps to reproduce (`parse_quick(text, date(2026,10,24))`):
  ```
  'buy sun cream'          -> title='buy cream'       date=2026-10-25  found=['Tomorrow']
  'the sun also rises'     -> title='the also rises'  date=2026-10-25
  'sat with grandma'       -> title='with grandma'    date=2026-10-24  found=['Today']
  ```
  (verified: `'sun cream' -> title='cream' date=2026-10-25`; `'sat exam prep' -> title='exam prep'`)
- Expected: these words stay in the title. The parser already guards "monday.com" against this kind of false match.
- Actual: the word is deleted and the date changes.
- Suggested fix direction: accept only full weekday names for a bare weekday, and allow 3-letter forms only after `on`/`every`/`next` (or followed by a time/date).

### BUG-7: Changing a repeating task's date in TaskDialog clears its ticks but not its items' ticks (shows 2/2 but open)
- Severity: low
- Where: calendardesk/dialogs.py:229-230 (`rule_changed` resets `done_dates`/`skip_dates` but not `items[*].done_dates` or `items[*].done`)
- Steps to reproduce:
  ```python
  from h import *; from calendardesk.dialogs import TaskDialog
  r = task("daily", repeat="daily", items=[model.new_item("x"), model.new_item("y")])
  app = make([r]); pump(app, 200)
  app.toggle_done(r, DAY, True)
  dlg = TaskDialog(app, r, DAY); pump(app, 100); dlg.v_date.set("23-10-2026"); dlg.save(); pump(app, 100)
  print(model.is_done(r, DAY), model.progress(r, DAY), r["done_dates"], [i["done_dates"] for i in r["items"]])
  app.quit()
  ```
- Expected: the item ticks are reset along with the task's ticks, so the state stays consistent.
- Actual: `after date change: done False progress (2, 2) done_dates [] item dd [['2026-10-24'], ['2026-10-24']]`. The calendar shows "2/2" in accent on an open task.
- Suggested fix direction: when `rule_changed`, also reset each item's `done_dates` (and `done`).

### BUG-8: Export writes titles/notes that start with "=" as Excel formulas
- Severity: low (a local, single-user app, but a title like "= finish report" breaks the cell or makes Excel show a repair/formula warning)
- Where: calendardesk/export.py:31-34, 51 (titles, notes and desktop notes are written raw; openpyxl stores any string starting with "=" as a formula)
- Steps to reproduce:
  ```python
  t = model.new_task('=HYPERLINK("http://x","click")', D); t["note"] = "=cmd|' /C calc'!A0"
  export_xlsx({"tasks":[t], "countdowns":[], "notes":[{"text":"=2+3"}]}, p, D)
  load_workbook(p)["Tasks"]["C2"].data_type   # 'f'
  ```
- Expected: the text is stored as text.
- Actual: `C3 f E3 f` (task title and note are formulas) and `Notes A2: =2+3 f`. This was already the case before this branch (it is not new).
- Suggested fix direction: prefix cells starting with `=`, `+`, `-`, `@` with an apostrophe, or set `cell.data_type = "s"` after writing.

---

## Unconfirmed suspicions
1. `App.quit()` flushes NoteWindows but never commits open DayPanels. With focus still inside a panel editor, `app.quit()` lost a typed title (reproduced in a script). Through the real tray/menu Exit, focus moves first and FocusOut saves it (verified), so I could not find a real user path. Windows logoff/shutdown has no handler at all and may lose uncommitted panel or note edits.
2. Desktop calendar quick-add box vanishes when the calendar redraws (the once-a-minute progress redraw, or any `changed()`). Reproduced: after `calendar.redraw()` the Entry is unmapped but keeps focus, and typing continues invisibly. Already present before this branch; the new preview label disappears with it.
3. Idle CPU with glow on sits near the limit: perf_check runs gave 0.069, 0.274 (FAIL), 0.083, 0.093 %. Glow off gave 0.138 (FAIL, noise), 0.018, 0.019 %. Instrumented: with the desktop not in front, the pulse runs at exactly 1 Hz, so the one 0.27 % run is likely noise, but the margin is small.
4. `Store.save()` uses `os.replace` without `flush()`/`os.fsync()`. After a power cut, NTFS can leave data.json empty or zeroed. Not reproducible here.
5. `parse_quick` silently drops a trailing "!" from the title when there is no time ("call mom!" → "call mom", no reminder, preview says "just a task"). This follows from the Ruling, but the text changes without any feedback.

## Checked and fine
- Unit tests: 71 pass. `tests/ui_day_panel.py`: PASS (30+ tasks open in 167 ms).
- Review Focus 1: a daily task with a checklist. An item ticked on 24 Oct is not ticked on 25 Oct (day-2 progress 0/2). Ticking the task on day 2 ticks the items for day 2 only (day 1 stays 1/2, not done).
- Review Focus 2: the title is never empty. `tomorrow`, `2pm`, `friday 3pm`, `remind me`, `every day`, `!!!`, `-`, `,` all keep the original text as the title. Clearing a panel title and pressing Enter restores the old title.
- Review Focus 3: odd notes through the panel save path (`note_to_save`): `1.`, `-`, `**unclosed`, `a\r\nb` (→ `a\nb`), `- `, `1. `, `  indented`, `• stored bullet` (→ `- `), `x\n\n` (trailing blank lines dropped), `a ** b ** c`, `**bold**`, `tab\there`, `5 * 3 = 15`, `**a**b**`. All keep their text (exception: BUG-4). Opening the panel without editing never rewrites a note.
- Review Focus 4: two or three fast clicks on a panel checkbox or item box during the animation give exactly one toggle. A desktop-calendar double-click on a checkbox is one toggle (`_double` ignores "check"). Concurrent animations on the calendar, mini calendar and panel use explicit values, so they cannot double-toggle.
- Review Focus 5: TaskDialog and panel editing the same task. Dialog saves last → the dialog's title is stored and the panel shows it. Panel saves last → the panel's title is stored (also on disk). No exceptions.
- Two panels for different days open side by side and refresh each other. Re-opening the same day focuses the existing panel.
- parse_quick correct for: `call mom 7pm tomorrow`, `monday.com`, `may I call you`, `march for science`, `a may day`, `12:30pm`, `12am`, `0:30`, `7 pm`, `9.30am`, `19.00`, `24:00` (rejected), noon/midnight, `next friday/mon/sun`, `the 3rd`, `on the 31st`, `1st`, `march 3rd 1990`, `3rd of march`, `25th december`, `dec 25 2026`, `13/1`, invalid `31/4`, `feb 30`, `29/2` (left in the title), `every 2 weeks`, `every 3 days`, `every mon, wed & fri 6am`, `every monday, wednesday and friday`, `every 0 days` (→ daily), `annually`, `remind me 7pm`, `call mom at 7pm!` (reminder). "at 3" → 03:00 matches the spec (24-hour unless am/pm).
- Model: `set_task_done` / `set_item_done` rules. Old task dicts without `"items"` (progress 0/0, set_task_done ok). Rollover keeps item ticks (1/1 after moving). Export Checklist column `0/2: =1+1; b` (text, the prefix protects it). For repeating tasks, today's ticks are shown, as the Ruling says.
- No exceptions or crashes from the progress count at narrow calendar widths (900 → 300 px) or in the mini calendar.
- Timers: after 60 open/close cycles, 60 rebuilds and 20 tick animations, `after info` shows only `_tick` and `pulse`. Animations stop themselves. `_settle` stops when nothing is raised. The glow pulses at 1 Hz when the calendar can't be seen.
- Perf (tests/perf_check.py, 200 tasks, tray on): 1 process, 0 child processes, 3 threads, about 59 MB working set. CPU with glow off 0.018 / 0.019 % (one noisy 0.138 %). Glow on: see suspicion 3.
- Progressive card build: closing before all cards are built cancels the job (`_cancel_build`). `_build_rest` checks `winfo_exists`. Structural rebuilds with focus build every card.
