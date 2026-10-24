# Verify report — round 3 (final)

I tested the uncommitted round-3 fix in `calendardesk/desktop_cal.py` and the new `tests/test_leaks.py` myself. For the "before" numbers I used a scratch copy made with `git archive HEAD` (9af1afb). The "after" numbers come from a HEAD copy with the working-tree `desktop_cal.py` and `test_leaks.py` dropped in; it matches the working tree except for line endings. All runs used temp Store folders and hotkey "K", each wrapped in `timeout`. The working tree was not changed. Scripts are in `%TEMP%\claude\qa-verify3`: `mem.py`, `mem_panel.py` and `behave.py`.

**Overall: PASS**

| Item / check | Verdict | Evidence |
|---|---|---|
| R3-1 leak: 500 calendar redraws, this month | PASS | Tcl commands: old +8499, new −1. Working set: old +8.1 MB, new +0.3 MB |
| R3-1 leak: 500 redraws with the "Today" button shown | PASS | old +10000 commands / +10.2 MB; new +0 / +0.0 MB |
| R3-1 leak: 200 `app.refresh_all()` | PASS | old +3399 / +3.3 MB; new −1 / +0.0 MB |
| R3-1 leak: 100 × `go(+1)` then `go(−1)` | PASS | old +3699 / +3.0 MB; new −1 / +0.0 MB |
| Header buttons ‹ › Today + Task Search ☰ (real canvas Motion/Press/Release events) | PASS | Month changes correctly. "Today" is drawn only when another month is shown. `edit_task(day=today)`, `search()` and `main_menu()` are each called exactly once. No delayed single-click action follows a button click |
| Hand cursor on hover, reset on leave | PASS | `hand2` → `""` |
| Grip: size cursor, drag-resize, no header drag | PASS | `size_nw_se` → `""`. Grip drag +40/+30 changes the size by exactly +40/+30, and the position is unchanged |
| Header drag moves the window | PASS | Dragging the title and the empty header both move the window by the exact delta. Press-and-move on a button does not move the window, and the button still fires once |
| Locked setting | PASS | Grip drag and header drag both leave the geometry unchanged |
| Single click on a task | PASS | Nothing at 100 ms; `edit_task(task)` after the click delay |
| Double-click | PASS | Quick-add box opens on a task, with no edit. On a check or a button: no quick-add and no edit |
| Tick animation on a check | PASS | Key is in `animating` right away; task is done after the animation; no other action |
| Right-click | PASS | Task context menu opens ("Edit task…" …). Right-click on a header button: no menu |
| Mouse wheel | PASS | −120 → next month, +120 → back |
| Buttons after theme change, resize and Settings preview | PASS | `preview_settings` with light, glass, paper, dark and calendar_size, plus a grip resize: the `btn`-tagged items equal the keys of `_buttons` (5/5 or 6/6) every time, and › ‹ Search work |
| Stale record | PASS | After a redraw, none of the old button ids is in `_buttons` or on the canvas (Tk item ids are never reused). Clicking where old buttons were, after a shrink, triggers an action only when a new button is under the pointer (checked with Tk's 1 px pick halo) |
| Empty space / no item | PASS | Clicking the empty header does nothing. `_button_click` with no button under the pointer raises nothing. 0 Tk callback errors in the whole run |
| Behaviour parity with HEAD | PASS | The same `behave.py` on the HEAD copy gives the same results. Its only failure is the new-only `_button_click` attribute |
| Other surfaces, 100 cycles each (new code) | PASS | Mini calendar redraw +0 commands / +0.0 MB; countdown card refresh +0 / +0.0; note restyle +0 / +0.0; day panel open/close +0 commands. Day panel memory: +1.6 MB in the first 100 cycles, then +0.1, −0.0, +0.1 over the next 300 (a one-time warm-up; HEAD shows the same +1.7 then flat) |
| `tests/test_leaks.py` RED on HEAD / GREEN now | PASS | HEAD copy: 2 failures ("1000 not less than or equal to 1", "849 not less than or equal to 1"). New: 6 tests OK |

## Regressions found

None.

One note on the tests: my first drag check reported a 3× move. That came from my synthetic `rootx` being recomputed from the window as it moved. It was not an app bug, and with fixed screen coordinates the move is exact.

## Numbers

| Scenario | Tcl commands old (HEAD) | Tcl commands new | Working set old | Working set new |
|---|---|---|---|---|
| 500 redraws, this month | 240 → 8739 (+8499) | 211 → 210 (−1) | +8.1 MB | +0.3 MB |
| 500 redraws, Today shown | 8779 → 18779 (+10000) | 210 → 210 (+0) | +10.2 MB | +0.0 MB |
| 200 refresh_all | +3399 | −1 | +3.3 MB | +0.0 MB |
| 100 go(+1)/go(−1) | +3699 | −1 | +3.0 MB | +0.0 MB |
| End-of-run working set | 79.3 MB | 55.8 MB | | |

Perf (`tests/perf_check.py`):
- glow on: CPU 0.022 / 0.010 / 0.006 / 0.024 % of one core, 59.1–59.2 MB, 3 threads, 0 child processes → PASS ×4
- glow off: CPU 0.005 / 0.012 %, 59.0–59.3 MB → PASS ×2

## Suite results

- `.venv/Scripts/python -m unittest discover -s tests -t .` → Ran 107 tests in 22.6 s, OK. 0 "invalid command name" or Traceback lines in the output.
- `timeout 90 .venv/Scripts/python tests/ui_day_panel.py` → PASS (panel opens with 30+ tasks in 156 ms).
- `tests.test_leaks`: HEAD copy FAILED (failures=2); fixed code OK (6 tests).
