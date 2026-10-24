# Fix report — round 2

All changes are in the working tree (not committed). Every regression test is in the new `tests/test_timers.py`. I ran each one and saw it fail on the round-1 code before making its fix.

| Item | Root cause | Change (files:functions) | Regression test (tests/test_timers.py) | RED seen? | Status |
|---|---|---|---|---|---|
| R2-1 | Once a minute, `App._tick` called `calendar.redraw()` (12–31 ms for 200 tasks) just to move today's progress bar. `_tick` also woke every 15 s. | `desktop_cal.py: DesktopCalendar.__init__, redraw, _draw_cell` (the filled line is tagged `progress` and remembered as `_progress`, reset on every redraw), `update_progress` (new; only `coords` of that line). `app.py: _tick` (calls `update_progress()` instead of `redraw()`; keeps `_tick_job`), `_next_tick_ms` (new: wake 200 ms after the next whole minute, or at an earlier snooze), `TICK_MS` replaced by `TICK_MARGIN_MS` | `MinuteTickTests::test_minute_tick_moves_bar_only` (canvas item ids unchanged, the bar's x1 grows), `::test_bar_follows_redraw_and_resize` (18:00 → 75 %; after a resize, a tick at 06:00 → 25 % on the new item), `::test_next_tick_is_at_the_minute_or_snooze`, `::test_reminder_fires_at_its_minute` (guard) | yes (guard passed before, as expected) | fixed |
| R2-2 | `Dialog.present()` scheduled `after(300, lambda…)` and never cancelled it. Closing the dialog sooner deleted the command but left the job queued, so it failed later or ran a callback that reused the name. The same applied to `NoteWindow._pending` (600 ms) when a note was deleted. | `dialogs.py: Dialog.__init__, present` (keeps `_topmost_job`, cancels a previous one), `_drop_topmost` (new), `destroy` (new: cancels the job). `widgets.py: NoteWindow.destroy` (new: cancels `_pending`). The other `after(` users already cancel (`DayPanel._cancel_build`, `RichNote.destroy`, Settings/Countdown `_preview_job`, `TickAnimation`). | `StaleTimerTests::test_dialogs_closed_at_once_leave_no_stale_jobs` (Task, Countdown, CountdownManager, Search and DayPanel each opened and closed at once; no `after` job may name a missing Tcl command) | yes | fixed |
| R2-3 | `quit()` unhooked last, so an exception in commit/save skipped it. The Tcl DLL was opened by a guessed name and could load a second copy. Some return types were left to the defaults. A failed `SetWinEventHook` left its Tcl command registered. | `app.py: App.quit` (`stop_hooks()` first). `winapi.py: ForegroundHook._loaded_tcl` (new: `GetModuleHandleW` on `tcl{v}t.dll` / `tcl{v}.dll` / `tcl9tcl{v}.dll`; only an already-loaded module is used, via `CDLL(name, handle=…)`; otherwise `handle` is None and the 1 s fallback runs; restype/argtypes for `Tcl_EvalEx`, `Tcl_SaveInterpState`, `Tcl_RestoreInterpState`, `Tcl_InterpDeleted`), `ForegroundHook.__init__` (deletes its command if the hook fails); module level: restype/argtypes for `UnhookWinEvent`, `GetClassNameW`, `SystemParametersInfoW`, `GetMessageW`, `GetCurrentThreadId`, `GetModuleHandleW` | `ForegroundHookTests::test_quit_unhooks_even_if_saving_fails`, `::test_uses_only_the_loaded_tcl_library`, `::test_failed_hook_deletes_its_command` | yes | fixed |
| R2-4 | SettingsDialog's `trace_add` callbacks are held by Tcl and were never removed, so each closed Settings window stayed alive. | `dialogs.py: Dialog.watch_var` (new: adds the trace and records it), `Dialog.destroy` (removes recorded traces), `SettingsDialog.__init__, _size` (use `watch_var`). No other dialog uses `trace_add` (SmartEntry was fixed in round 1). | `SettingsLeakTests::test_closed_settings_are_freed` (2 opens with a live preview; 0 `SettingsDialog` alive after `gc.collect()`) | yes (2 alive) | fixed |
| R2-5 | `quit()` destroyed the root with `_tick`, `_pulse`, `_settle` and other jobs still queued. Tcl's notifier is per thread, so the next Tk in the same process ran them and printed "invalid command name". | `app.py: App.quit` (cancels every pending `after` job of the interp with `after cancel` just before `root.destroy()`; the commands themselves are left for their widgets to delete) | `StaleTimerTests::test_quit_leaves_no_pending_jobs` | yes (3 jobs) | fixed: 0 messages in the suite (was ~21) |

## Notes

- **R2-1 cost:** measured in a scratch script with 200 tasks, `calendar.redraw()` takes 12.0 ms and `update_progress()` takes 0.0017 ms. A full redraw still happens on day change (`go_today()` + `changed()`), on data and settings changes, and on `<Configure>` (resize). Each redraw re-creates the bar at the current minute and re-points `_progress`, so the bar is correct after any redraw.
- **Tick alignment (R2-1, optional part):** reminder times are whole minutes (`model.reminder_time` has no seconds), the day changes on a minute, and the bar moves per minute. So `_tick` now sleeps until 200 ms after the next whole minute, or until an earlier snooze is due (snoozes carry seconds). Reminders now fire within about 0.2 s of their minute instead of within 15 s, with 1 wake-up a minute instead of 4. The 2 s first tick at startup is unchanged. Tcl timers follow the system clock as before, so after sleep or a clock change the behaviour is the same as the old 15 s timer, at most one minute coarser.
- **R2-3, quit order:** if commit or save raises, the hook is already removed and the app keeps running, as before. In that rare case the glow runs on the 1 s fallback, and only resumes after the next redraw if it was idle at the time.
- **R2-3, DLL names:** the list of names is only used to find a module that is *already loaded*. Nothing new is ever loaded. A Tcl 9 build with a different name falls back to polling.
- **R2-5:** jobs are cancelled with the raw `after cancel`, not `after_cancel()`. tkinter's `after_cancel` also deletes the command from the root, and the owning widget's `destroy()` then raises "can't delete Tcl command". I saw that error in my first attempt.
- `docs/DESIGN.md` performance paragraph updated (once-a-minute tick, bar-only update).

## Final test / perf output

```
> .venv/Scripts/python -m unittest discover -s tests -t .
.....................................................................................................
Ran 101 tests in 16.652s
OK
(stderr: 0 "invalid command name" lines; round 1 had ~21)

> timeout 90 .venv/Scripts/python tests/ui_day_panel.py
...
ok   panel opens with 30+ tasks in 152 ms (< 300)
PASS

> timeout 60 .venv/Scripts/python tests/perf_check.py on      (6 runs)
glow on: CPU 0.018% of one core, threads 3, memory 59.2 MB, child processes 0 -> PASS
glow on: CPU 0.005% of one core, threads 3, memory 59.2 MB, child processes 0 -> PASS
glow on: CPU 0.005% of one core, threads 3, memory 59.1 MB, child processes 0 -> PASS
glow on: CPU 0.019% of one core, threads 3, memory 59.4 MB, child processes 0 -> PASS
glow on: CPU 0.006% of one core, threads 3, memory 59.5 MB, child processes 0 -> PASS
glow on: CPU 0.019% of one core, threads 3, memory 59.1 MB, child processes 0 -> PASS

> timeout 60 .venv/Scripts/python tests/perf_check.py off     (3 runs)
glow off: CPU 0.005% of one core, threads 3, memory 58.9 MB, child processes 0 -> PASS
glow off: CPU 0.005% of one core, threads 3, memory 59.2 MB, child processes 0 -> PASS
glow off: CPU 0.018% of one core, threads 3, memory 59.1 MB, child processes 0 -> PASS
```
