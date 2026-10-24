# Fix report — round 3

All changes are in the working tree (not committed). The regression tests are in the new `tests/test_leaks.py`. I ran them on the round-2 code and saw the leak tests fail before making the fix.

| Item | Root cause | Change (files:functions) | Regression test (tests/test_leaks.py) | RED seen? | Status |
|---|---|---|---|---|---|
| R3-1 | `DesktopCalendar.redraw()` called `canvas.tag_bind(...)` with new lambdas each time: 3 per header button in `_button` (5 buttons, 6 when "Today" is shown) and 2 for the grip. Each bind registers a Tcl command that keeps a Python closure. `canvas.delete("all")` removes the items but not the commands, so they stayed until the canvas was destroyed. That is +17 to +20 commands per redraw. | `desktop_cal.py: DesktopCalendar.__init__` now binds `<Button-1>`, `<Enter>` and `<Leave>` once on the stable tag `btn`, and `<Enter>`/`<Leave>` once on `grip`. `_button` only adds the tag `btn` to the item and records `item -> action` in `self._buttons`. `redraw` resets `_buttons` and no longer binds the grip. New `_button_click` looks up the clicked item (`find_withtag("current")`) and runs its action. | `RedrawLeakTests::test_calendar_redraw_registers_no_commands` (50 redraws with the Today button shown: growth ≤ 1, was +1000), `::test_mini_calendar_and_cards_register_no_commands` (mini 50 redraws, `refresh_all` ×50: was +849), `::test_day_panel_commands_are_freed_with_it` (guard). `HeaderButtonTests::test_next_prev_today_buttons` (› › ‹ Today through real canvas events), `::test_hand_cursor_on_buttons_and_size_cursor_on_grip`, `::test_task_and_search_buttons_call_the_app` (guards) | yes (+1000 and +849) | fixed |

## Notes

- **Other canvases I checked:**
  - `MiniCalendar.redraw` uses its own `hits` list for its ‹ › ✕ buttons and binds nothing per redraw. I measured it at 0 growth on the old code too.
  - `CountdownCard.refresh` binds nothing per refresh. Its `grip` and drag binds come from `make_resizable` and `make_draggable` in `__init__`.
  - `NoteWindow` binds only in `__init__`.
  - `make_draggable`/`make_resizable` (the `drag` and `grip` press binds) run once in `__init__`, so they were never part of the leak.
- **Day panel:** I verified it with a test rather than assuming. Its widget binds are registered on the widgets themselves and freed by `destroy()`. Opening and closing it 10 times (10 tasks) gives growth ≤ 0.
- **Other per-redraw registrations:** `after` callbacks free their command once they fire or are cancelled. Tk fonts and traces were covered in round 2. I found no other `tag_bind`, `register` or `command=` in a redraw path.
- **Tolerance:** the leak tests allow growth of up to 1, because a pending `after` job (glow, tick) can fire during the loop and free its command (I once saw −1). A real leak shows up as ≥ 50.
- **Behaviour:** the binds still go through `tag_bind` on the same items, so the event order is the same. The canvas-wide `<Button-1>` (`_click`) sees the `"button"` hit and does nothing, as before. Double-click, quick-add, the tick animation, the right-click menu, header drag and grip resize are unchanged. The full suite passes.

## Memory check (500 calendar redraws, 30 tasks, temp data folder)

Script: `C:\Users\shreyash\AppData\Local\Temp\claude\qa-fix3\mem.py`. For the HEAD baseline I used `git archive HEAD` extracted to `qa-fix3\old`.

```
HEAD 9af1afb: Tcl commands 211 -> 8711 (+8500); working set 51.7 -> 60.1 MB (+8.4); private 33.9 -> 41.8 MB (+7.9)
fixed:        Tcl commands 182 -> 182 (+0);     working set 51.8 -> 52.2 MB (+0.5); private 34.1 -> 34.2 MB (+0.2)
```

## Final test / perf output

```
> .venv/Scripts/python -m unittest discover -s tests -t .
Ran 107 tests in 22.257s
OK
(stderr: 0 "invalid command name" / Traceback lines)

> timeout 90 .venv/Scripts/python tests/ui_day_panel.py
...
ok   panel opens with 30+ tasks in 157 ms (< 300)
PASS

> timeout 60 .venv/Scripts/python tests/perf_check.py on   (x4) / off (x2)
glow on: CPU 0.006% of one core, threads 3, memory 59.3 MB, child processes 0 -> PASS
glow on: CPU 0.006% of one core, threads 3, memory 59.1 MB, child processes 0 -> PASS
glow on: CPU 0.022% of one core, threads 3, memory 58.9 MB, child processes 0 -> PASS
glow on: CPU 0.006% of one core, threads 3, memory 59.2 MB, child processes 0 -> PASS
glow off: CPU 0.006% of one core, threads 3, memory 59.0 MB, child processes 0 -> PASS
glow off: CPU 0.005% of one core, threads 3, memory 59.2 MB, child processes 0 -> PASS
```
