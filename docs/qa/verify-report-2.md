# Verify report — round 2

I verified the uncommitted working tree on top of 19ab728. For the HEAD baseline, I extracted a read-only copy with `git archive HEAD | tar -x` into `%TEMP%\claude\qa-verify2\old`. I did not stash, check out, reset or commit anything. All scripts are in `C:\Users\shreyash\AppData\Local\Temp\claude\qa-verify2`. Every run used a temp data folder and hotkey "K", and was wrapped in `timeout`.

**New tests against HEAD code:** `tests/test_timers.py` run on the HEAD copy gives 10 tests, 8 FAIL and 1 ERROR. The one that passes is `test_reminder_fires_at_its_minute`, a guard the fixer described as such. All 10 pass on the working tree, 3 of 3 repeat runs.

| Item | Verdict | Evidence | Notes |
|---|---|---|---|
| R2-1 minute tick / reminder clock | PASS | **Real clock** (`realtime.py`, real mainloop): `_tick` woke at 21:54:03.8 (the 2 s start tick), then at 21:55:00.202, 21:55:21.214 (the snooze) and 21:56:00.205, with no other wake-ups. Six reminders each fired exactly once, and none was missed (table below). **Simulated clock** (`sim.py`, `datetime` patched): exact boundaries, remind_before, a 10-min snooze, tomorrow 00:00, midnight rollover, and backward/forward jumps all behave correctly with 0 errors (details below). **Progress bar** (`progress.py`): resize, shrink, theme change, font-size change, settings preview and cancel, month +1 / +6 (today not shown), a tick while today is hidden, `today_progress` off and on. In every case: 0 or 1 `progress` item, `_progress` pointing at it, the fraction equal to the current minute, no exception, no stray item. The bar is correctly absent when today isn't shown or the setting is off. | Behaviour change: a reminder whose time is already due when you add or edit it fires at the next whole minute, up to about 60 s later (it was up to 15 s). It is never missed. Reminders set for a future minute now fire about 0.2 s after their minute (they could be up to 15 s late). |
| R2-2 stale `present()` job / NoteWindow pending save | PASS | `notes.py`: 20 notes typed into and then deleted within 30 ms. A save was pending in 19 of 20. Result: 0 notes brought back, 0 dangling `after` jobs, nothing in memory or on disk, 0 errors. Hide right after typing: "keep me" is saved (flushed). Typing then quitting within 30 ms: `'keep me +quit'` is on disk. Round 1's `stale.py` repro (40 panels closed quickly) now gives **0** errors (round 1: 2). | |
| R2-3 foreground-hook hardening | PASS | `stress.py`, 8 runs × 500 switches, 4 with tray off and 4 with tray on. Panels opened and closed every 25 switches, toggles every 7, panel checkbox clicks every 11, `_tick()` every 17 (45 ticks per run). All runs: exit 0, hook installed through the already-loaded module, 500/500 switches landed, `bad_tcl 0`, 514 hook callbacks, 0 errors, 2/3 threads, `CLEAN EXIT`, hook handle `None` after quit. Fallback (`fallback.py`, `GetModuleHandleW` → None): `handle None`, 3 pulses in 3 s with another window in front (1 s poll), 12/s on the desktop, clean exit. **Quit side effect** (`savefail.py`, `store.save` raising): `quit()` raises, the hook is gone, the window stays alive, the hotkey thread keeps running, the tick stays scheduled and the edits stay in memory. A second `quit()` saves `edited` and exits cleanly. | I accept the side effect. The data is kept in memory, the app keeps running and you can retry Exit. The only loss is the glow's instant wake-up (the 1 s fallback, or nothing until the next redraw), which is cosmetic. Pulses/1 s on the desktop measured 4–12 (round 1: 7–12). This is a 1 s sample taken right after a switch and is not a crash signal. |
| R2-4 `watch_var` trace removal | PASS | `settings_leak.py`, 20 tasks: 50 Cancel cycles and then 50 Save cycles, each with a live font-size preview. Tk fonts 28 → 28, SettingsDialog alive 0, PY_VAR traces 0, pending afters 3 → 3, errors 0, and the font size is restored correctly on Cancel and toggled on Save. Working set: 53.3 → 55.8 (after 50 Cancel) → 58.8 MB (after 50 Save). | The remaining growth is **not** Settings: Tcl commands grow by about 51 per cycle (501 → 5601). I traced these to `desktop_cal.py:313-315` (`_button` `tag_bind` lambdas) and `:167-168`, which are re-registered on every `calendar.redraw()` and never deleted. `canvas.delete("all")` doesn't free tag-bind commands. This is pre-existing (see Regressions). |
| R2-5 `quit()` cancels all `after` jobs | PASS | Full suite stderr: **0** "invalid command name" lines (round 1: about 21). The round-1 `extra1.py` still saves the panel title and note typed before quit (`A typed`, `n note-typed`, 0 errors). The note flush on quit works (R2-2 row). `test_quit_leaves_no_pending_jobs` passes, and the stress runs show 0 pending jobs after quit. | Jobs that are cancelled and would have changed data: a `TickAnimation` in progress (`toggle_done` runs in `on_done` after the animation) and a desktop single-click delay job (260 ms). A tick started less than about 0.3 s before Exit is lost. Before this change it was lost too (the root was destroyed under it), so this is not a regression and it is very unlikely in practice. |

## Regressions found

None caused by this round.

Pre-existing issue, found while measuring R2-4 (for a future round):
- **Tcl command leak per calendar redraw.** Each `DesktopCalendar.redraw()` adds about 17 Tcl commands (30 tasks), each with a Python closure. They come from `_button()`'s three `tag_bind` lambdas (desktop_cal.py:313-315) and the binds at :167-168. They are only freed when the canvas is destroyed. `redrawleak.py`: new code gives +17 per redraw and **+0 per minute tick**; HEAD gives +17 per redraw and **+18 per minute tick**.
  - R2-1 therefore removes the largest source, about 26k commands a day from the once-a-minute redraw.
  - Redraws on data changes, resizes and settings previews still leak, slowly.
  - Fix direction: bind once on the canvas, using tags plus `self.hits` lookups, or `tag_unbind` before `delete("all")`.

## Reminder timing

**Real clock** (`realtime.py`). Tasks were created at 21:54:01 for the current minute, the next minute, the minute after that with remind_before=1, and the minute after that exactly. One task was added at +5 s through `changed()`, and a snooze state was set for +75 s.

| Reminder | Due | Fired | Lag |
|---|---|---|---|
| cur_minute (already due) | 21:54 | 21:54:03.847 (start tick) | — |
| next_minute | 21:55:00 | 21:55:00.202 | +0.203 s |
| nn_before1 (21:56 − 1 min) | 21:55:00 | 21:55:00.202 | +0.203 s |
| snoozed (stored due 21:55:21) | 21:55:21 | 21:55:21.214 | +0.214 s |
| nn_exact | 21:56:00 | 21:56:00.206 | +0.206 s |
| added_mid_for_nn (added during the run) | 21:56:00 | 21:56:00.206 | +0.206 s |

Each fired exactly once, none was missed, and there were 0 errors.

**Simulated clock** (`sim.py`):
- **Minute boundary:** a tick at 10:00:59.900 schedules the next one in 300 ms. At 10:01:00.200 the 10:01 reminder fires once, and the next tick is in 60000 ms. An extra tick at 10:01:00.300 does not fire it again.
- **remind_before:** a 10:10 task with remind_before=5 does not fire at 10:04:59.999 (next tick in 201 ms). It fires at 10:05:00.000.
- **Snooze:** a 10-minute snooze set at 10:05:17. At the 10:15:00.2 tick, `next_ms` = 17000. The reminder fires at 10:15:17.2, once.
- **Backward jump of 29 min:** `next_ms` = 60000 and nothing fires again. **Forward jump to 23:59:** the 23:59 reminder fires once.
- **Midnight:** at 23:59:59.950, `next_ms` = 250. At 00:00:00.2: `_day` = 25 Oct, 1 backup, the calendar is redrawn and on the current month, the unfinished task rolls over to 25 Oct, and the tomorrow-00:00 reminder fires. The next tick is in 60000 ms.
- **Backward jump across midnight:** no exception; `_day` goes back to the 24th. A later forward pass would roll over and back up again. Old code did the same.
- **Snooze already past:** it never shortens the wait; `next_ms` stays ≥ 200 ms, so there is no busy loop.

**Reasoning on sleep and clock changes.** The interpreter is Tcl 8.6.15. Its timers are absolute wall-clock times (`Tcl_GetTime`), and the wait is re-checked on any window message.
- **Clock jumps forward, or the PC resumes after the due time:** the pending tick is overdue and runs on the next notifier wake-up. That is at most the remaining Windows wait time (≤ 60 s, since wait timeouts don't count time spent asleep), or sooner on any window message. Reminders missed while asleep fire on that tick if they are less than 12 h late.
- **Clock jumps backward by N:** the pending tick is delayed by N. Old code had the same behaviour (N + 15 s).
- **Every case:** `_tick` recomputes from `datetime.now()`, the delay is always between 200 ms and 60.2 s (or the snooze time), and it cancels any duplicate job. So the tick never stalls for good and never busy-loops.
- **Tcl's clock slightly ahead of the system clock:** the tick may wake just before the minute. It then reschedules about 300 ms later, as seen at 10:00:59.900 above.
- **Net effect:** after sleep or a clock change, the worst-case delay before the first tick is 60 s instead of 15 s.

## Perf numbers

`tests/perf_check.py` (`timeout 60`). Every run exited 0 and printed a result.

- **Glow on (8 runs):** 0.005, 0.022, 0.006, 0.022, 0.004, 0.004, 0.015, 0.006 % of one core. All PASS. Round 1 had 4 of 12 FAIL at 0.16–0.24 %.
- **Glow off (3 runs):** 0.011, 0.005, 0.005 %. All PASS.
- **Every run:** 3 threads, 0 child processes, 58.8–59.2 MB.

## Suite results

```
> .venv/Scripts/python -m unittest discover -s tests -t .
Ran 101 tests in 16.849s
OK      (stderr: 0 "invalid command name" lines)

> tests/test_timers.py on the HEAD copy:  Ran 10, FAILED (failures=8, errors=1)
> tests/test_timers.py on the working tree, 3 runs: OK, OK, OK

> timeout 90 .venv/Scripts/python tests/ui_day_panel.py
ok   panel opens with 30+ tasks in 150 ms (< 300)
PASS   (exit 0)
```

`docs/DESIGN.md` change: one sentence on the once-a-minute tick and the bar-only update. It matches the code.
