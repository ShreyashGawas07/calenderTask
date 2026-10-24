# Fix report — round 1

All changes are in the working tree (not committed). Each regression test was run and seen failing before its fix.

| Item | Root cause (one line) | Change (files:functions) | Regression test (file::name) | RED seen? | Status |
|---|---|---|---|---|---|
| BUG-1 | `commit_all()` in a click let `own_save` run a pending rebuild, which destroyed the clicked canvas. `TickAnimation.start()` then raised before `on_done`, so the key stayed in `animating` forever | `day_panel.py: TaskCard.click_check, click_item, _live_card` (mark the key as animating *before* `commit_all`, so `own_save` doesn't rebuild; re-find the live card/box afterwards; skip if the item was removed). `anim.py: TickAnimation.start, _create_items` (a dead canvas finishes at once and still calls `on_done`) | `tests/test_day_panel.py::ClickAfterDeferredRefreshTests::test_task_check`, `::test_item_check`; `tests/test_anim.py::TickAnimationTests::test_start_on_destroyed_canvas_finishes` | yes | fixed |
| BUG-2 | The `StringVar` trace on SmartEntry is held by Tcl and never removed, so every closed panel (cards, fonts) stays alive | `day_panel.py: SmartEntry.__init__, SmartEntry.destroy` (keep the trace id, `trace_remove` on destroy) | `tests/test_day_panel.py::PanelLeakTests::test_closed_panels_are_freed` (0 panels alive, font count back to baseline) | yes | fixed |
| BUG-3 | A rebuild destroys the add-item box and its unsent text (it never counts as dirty) | `day_panel.py: DayPanel.__init__ (add_drafts), DayPanel.rebuild` (save non-empty add-box text per task), `TaskCard._body` (put it back), `TaskCard.add_item` (clear the box once the item is added) | `tests/test_day_panel.py::AddBoxTests::test_add_box_text_survives_refresh`, `::test_added_item_leaves_box_empty` | yes (2nd test is a guard for the new code) | fixed |
| BUG-4 | Any line matching `\d+\. ` was treated as a numbered item and renumbered from 1 | `richnote.py: list_number` (new: a list starts at `1.` and goes on with the same or the next number), `parse_lines`, `RichNote._kinds/_kind` (line kind now depends on the line above), `dump`, `toggle_bullet`, `toggle_number`, `newline`, `_set_prefix`, `_renumber`, `_style_line` | `tests/test_richnote.py::MarkdownTests::test_number_that_is_not_a_list_is_kept`, `RichNoteWidgetTests::test_number_that_is_not_a_list_survives_editing`, `::test_enter_and_toggle_leave_other_numbers_alone` | yes | fixed |
| BUG-5 | `d/m`, `d-m` and `h.mm` were accepted anywhere; ISO dates were not handled, so `11-05` was read as a d-m date | `model.py: _clearly_a_date, _numeric_date` (new), `parse_quick` (`take()` now tries each match against an `ok` check; ISO `YYYY-MM-DD` branch before d/m; the d/m branch uses `_numeric_date`; dot times need `at`) | `tests/test_parse.py::FalsePositiveTests::test_numbers_are_not_dates_or_times`, `::test_iso_date`, `::test_slash_date_with_context`, `::test_dot_time_needs_am_pm_or_at` | yes | fixed |
| BUG-6 | Bare `sat`/`sun` were matched anywhere as weekdays | `model.py: _WORD_WD, _clearly_a_date, parse_quick` (weekday branch) | `tests/test_parse.py::FalsePositiveTests::test_sun_and_sat_as_words`, `::test_short_weekday_where_it_is_a_date` | yes | fixed |
| BUG-7 | `rule_changed` reset the task's `done_dates` but not its items' | `dialogs.py: TaskDialog.save` (also clear each item's `done_dates`) | `tests/test_day_panel.py::DialogDateChangeTests::test_item_ticks_reset_with_task_ticks` | yes | fixed |
| BUG-8 | openpyxl stores any string starting with `=` as a formula | `export.py: _sheet` (cells whose text starts with `=` get `data_type = "s"`, text kept exactly) | `tests/test_model.py::ExportTests::test_text_starting_with_equals_stays_text` | yes | fixed |
| EXTRA-1 | `App.quit()` flushed note windows but not open day panels | `app.py: App.quit` (`commit_all()` on every open view that has it, before `save()`) | `tests/test_day_panel.py::QuitSavesPanelTests::test_quit_commits_open_panel_edits` (title + note typed with focus in the panel, then `quit()`, checked in data.json) | yes | fixed |
| EXTRA-2 | `Store.save()` replaced data.json without flushing the temp file to disk | `store.py: Store.save` (`f.flush(); os.fsync(f.fileno())` before `os.replace`) | `tests/test_model.py::StoreTests::test_save_syncs_before_replace` (fsync is called before replace) | yes | fixed |
| EXTRA-3 | With the glow hidden, `_pulse` polled `desktop_is_foreground()` every second | `winapi.py: ForegroundHook` (new, `SetWinEventHook(EVENT_SYSTEM_FOREGROUND, WINEVENT_OUTOFCONTEXT)`), `desktop_cal.py: DesktopCalendar.__init__, _pulse` (no timer while hidden if the hook is active; otherwise falls back to the 1 s check), `_foreground_changed, stop_hooks`; `app.py: App.quit` (unhooks) | `tests/test_anim.py::CalendarClickTests::test_hidden_glow_waits_for_foreground_change` | yes | fixed (see notes: a first version crashed; the shipped one passed the stress tests) |

## Notes

**Smart typing rules (BUG-5/6).** Make ambiguous forms stricter instead of guessing:
- `sat`/`sun` (3-letter only; `saturday`/`sunday` always count) and a yearless slash date (`24/10`) count as a date only (a) after `on`, (b) at the very end of the text, or (c) with nothing but a time between them and the start or end of the text. So `gym sat`, `gym sat 7am`, `sun 10am brunch`, `party 24/10`, `dentist 5/11 3pm`, `brunch on sun` and `buy sun cream on sat` are dates. `buy sun cream`, `the sun also rises`, `sat with grandma`, `sat exam prep`, `buy 3/4 cup flour` and `chapter 2/3 done` stay text. "every sat" and "next sun" already had their own branches and still work. Repeat, reminder and `!` words are removed before this check, so `gym sat every week` still works.
- A yearless dash form (`5-11`) needs `on`: `read pages 1-12` and `score 3-1` stay text. With a year (`24-10-2026`, `5-11-26`) it is a date anywhere. The year must have 2 or 4 digits, and both separators must match.
- A slash or dash date that is part of a longer run of numbers is never a date: `2 3/4`, `1/2/3/4`, and the `11-05` inside `2026-11-05`.
- `YYYY-MM-DD` is read as an ISO date (`2026-11-05 dentist` gives 5 Nov 2026, title "dentist"). An invalid ISO date stays in the title.
- `h.mm` is a time only with am/pm (`7.30 pm`, `9.30am`) or after `at` (`at 19.00`). A colon time (`19:30`, `9:30`) still works anywhere. So `pay 2.50` and `version 2.10` stay text. Behaviour change: a bare `19.00` is no longer a time (the hunter listed it as correct before; the brief asked for this).
- Behaviour change: `24/10 party` (a date at the start, followed by words) is now text. The rule allows the start only when a time follows (`24/10 7pm party`). This keeps `3/4 cup flour` and `1/2 marathon` as text.
- All of the hunter's examples now behave as the brief asks; I kept none of the old behaviours. All 31 original `test_parse.py` tests pass unchanged (checked by running the original file against the fixed code).

**Notes numbering rule (BUG-4).** A line is a numbered-list item only if it starts with `1.`, or if it directly follows a list item and has the same number or the next one (the same number covers the line that Enter just inserted). `2024. was a good year`, `100. items` and an old list `3. third\n4. fourth` are now plain text and keep their numbers. Toggling "1. List" on such a line adds a real prefix (`1. 2024. year`) instead of eating the number.

**BUG-3 approach.** I kept the panel refreshing right away (so a tick elsewhere shows at once) and carried the add-box text across the rebuild, instead of making the box "dirty". A dirty box would have held back every refresh while text sat in it.

**BUG-7 scope.** Only items' `done_dates` are reset, the same as the task's own `done_dates`. A one-off task's `done` flag is not reset on a date change, so its items' `done` flags are left alone too, to stay consistent with it.

**EXTRA-1.** `quit()` calls `commit_all()` (not `close()`) on views that have it, so other dialogs keep their current Exit behaviour. Windows logoff/shutdown is still not handled (hunter suspicion 1). That is out of scope here.

**EXTRA-3, what happened.** The first version had the WinEvent callback call `win.after(0, …)`. It crashed Python in 2 of 5 perf runs with `Fatal Python error: PyEval_RestoreThread … thread state is NULL`. The callback is delivered nested inside Tk's event processing, and any tkinter call there resets `_tkinter`'s saved thread state. The shipped version never calls tkinter from the callback. It asks Tcl through its C API (`Tcl_EvalEx`, wrapped in `Tcl_SaveInterpState`/`Tcl_RestoreInterpState` in case it arrives mid-command) to run `after 0 <registered command>`. tkinter then makes the Python call the normal way. If the Tcl DLL or the hook can't be set up, `handle` is None and the old 1 s check runs.
- Stress test (scratch script, not in the repo): 600 foreground switches during a live mainloop with tray on, from Python callbacks (`bring_to_front`, `focus_force`) and nested `update()`, checking a Tcl result (`expr 6*7`) after each. Across 7 runs: 0 crashes, 0 wrong Tcl results, 0 callback errors, 3 threads. In one early run the window-width check differed (197 of 600), never the Tcl result. I count that as window geometry, but I could not reproduce it in the 4 runs that logged it separately.
- The ctypes callback object is kept on the hook. The hook is unhooked in `App.quit()`, and its Tcl command is deleted.
- Remaining risk: this depends on the Tcl C API (`tcl86t.dll`, Tcl 8.6.15 here). A future Python with Tcl 9 would fail to load the DLL and fall back to polling, not crash.

**Perf numbers (glow on, `tests/perf_check.py on`).** Before: 0.180 (FAIL), 0.092, 0.088 %. After: 0.162, 0.009, 0.013, 0.014, 0.018, 0.243, 0.227, 0.015, 0.013 % (plus the final runs below). Typical idle CPU with the glow on fell from about 0.09 % to about 0.013 %, the same as glow off. Instrumented runs show 3–4 `_pulse` calls per run (about 25 s) instead of about 23.

The occasional 0.16–0.24 % run is not the glow. It shows up in about 1 in 3 runs, which matches the chance that the 20 s window contains the existing once-a-minute `calendar.redraw()` from `App._tick`. That full redraw takes about 16 ms CPU for 200 tasks, plus the repaint. The hunter saw the same spike with the glow off (0.138 %). I did not change this; a cheaper "today progress" redraw would fix it, and that is a separate change.

**Not changed, noticed:** `dialogs.py` lines ~494 and ~575 (Settings dialog) also use `trace_add` without removal. That is the same leak pattern as BUG-2, but only per Settings open, so it is minor and outside this round.

**Docs updated:** `docs/DESIGN.md` (glow idle / perf numbers) and `docs/superpowers/specs/2026-10-24-day-panel-design.md` (glow hook; smart-typing table and the ambiguity rules).

## Final test / perf output

```
> .venv/Scripts/python -m unittest discover -s tests -t .
Ran 91 tests in 13.166s
OK

> timeout 90 .venv/Scripts/python tests/ui_day_panel.py
...
ok   panel opens with 30+ tasks in 174 ms (< 300)
PASS

> timeout 60 .venv/Scripts/python tests/perf_check.py on     (3 runs)
glow on: CPU 0.227% of one core, threads 3, memory 59.5 MB, child processes 0 -> FAIL   (minute-redraw spike, see notes)
glow on: CPU 0.015% of one core, threads 3, memory 58.9 MB, child processes 0 -> PASS
glow on: CPU 0.013% of one core, threads 3, memory 58.9 MB, child processes 0 -> PASS

> timeout 60 .venv/Scripts/python tests/perf_check.py off    (2 runs)
glow off: CPU 0.018% of one core, threads 3, memory 59.2 MB, child processes 0 -> PASS
glow off: CPU 0.022% of one core, threads 3, memory 59.2 MB, child processes 0 -> PASS
```
