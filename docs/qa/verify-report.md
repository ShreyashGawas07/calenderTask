# Verify report — round 1

Verified against the uncommitted working tree (`git status`: 10 source files, 2 docs and 4 test files modified, plus untracked `docs/qa/` and `tests/test_day_panel.py`). I compared against an unmodified copy of HEAD, extracted read-only with `git archive HEAD | tar -x` into `%TEMP%\claude\qa-verify\old`. I did not stash, check out, reset or commit anything. All scratch scripts are in `%TEMP%\claude\qa-verify`, every run used temp data folders, and every run was wrapped in `timeout`.

"Fails on old code" means I ran the fixer's new test files against the HEAD copy of `calendardesk/` (in `qa-verify\oldnewtests`): 20 regression tests ran, with 16 FAIL and 2 ERROR. The only 2 that passed on old code are `test_slash_date_with_context` and `test_added_item_leaves_box_empty`, both of which the fixer describes as guards.

| Item | Verdict | Evidence (what I ran, what I saw) | Notes |
|---|---|---|---|
| BUG-1 | PASS | Hunter repro (`bug1.py`). New code: `B done: True`, `animating: set()`, `panel pending: False` after an outside toggle, the second click unticks B, 0 errors. Old copy: `B done: False`, key stuck in `animating`, TclError. Variation (`bug1b.py`): note dirty + "Clear" colour, then click an item box of another card → item ticked, note saved, `animating` empty. Own card's title dirty + swatch + its own checkbox → ticked, title saved. Triple click → exactly one toggle. Panel refreshes afterwards. 0 errors. | Tests `test_task_check`, `test_item_check` and `test_start_on_destroyed_canvas_finishes` all fail or error on old code and pass now. |
| BUG-2 | PASS | Hunter repro (`bug2.py`, 20 and 60 cycles, alternating days, some with a dirty title on close). New code: `DayPanel alive: 0, TaskCard alive: 0, fonts: 23` (baseline 23). Old copy: 20 panels, 84 cards and 207 fonts alive. | `test_closed_panels_are_freed` fails on old code. One run logged a `RichNote…<lambda>() missing 'e'` TypeError. This is pre-existing (it also shows up on old code); see "Regressions found". |
| BUG-3 | PASS | Hunter repro (`bug3.py`): `A add box now: 'buy milk'`. The text survives 2 more refreshes (a desktop tick and a date colour). Enter then adds it as an item and the box is cleared. A draft does not reappear after the panel is closed and reopened. | Minor: when the task moves off the panel, its draft stays in `add_drafts` (harmless; it's freed with the panel). Unsent add-box text is still lost on Exit (not in scope). |
| BUG-4 | PASS | Hunter repro (`bug4.py`). `2024. was a good year`, `100. items` and `3. third\n4. fourth` are shown and saved unchanged, with only " X" added. Variations: real lists `1. a\n2. b\n3. c` are kept; `1. a\n1. b` is renumbered to `2.` (a real list, acceptable); `1. a\n3. skip`, `0. zero`, `1.5 kg sugar`, a list followed by `2024. year`, a bullet then a numbered list, and `intro / list / blank / 5. five` are all preserved. Enter inside a list renumbers correctly. Toggling "1. List" on a `2024.` line gives `1. 2024. …`, and toggling back restores it. | 3 widget and Markdown tests fail on old code. |
| BUG-5 | PASS | Hunter's 7 cases (`parse.py`, old vs new diff): all stay in the title now; `2026-11-05 dentist` → 5 Nov 2026, title "dentist". User-style inputs are still understood: `party 24/10`, `party on 24/10`, `dentist 5/11 3pm`, `report due 31/10`, `exam 12/11/2026`, `exam 12/11/26`, `dentist 5-11-2026`, `dentist on 5-11`, `flight 6/11 7:40am`, `meet at 7.30`, `meet 7.30pm`, `train 19:30`, `pay 2.50 at 7pm` (title "pay 2.50", 19:00), `due 2026-11-05`. These now stay plain text: `1/2 marathon`, `2 3/4 cups`, `2026-02-30 bad`. Fuzz: 30,000 random token mixes gave 0 exceptions; the only empty titles came from whitespace-only input. | Documented behaviour changes, now plain text: `24/10 party` (date first, then words), `dentist 5-11` (dash without "on"), `19.00 news`. The live preview shows this, so I judge them sensible. `on 5/11` alone sets the date but keeps "on 5/11" as the title; this is unchanged from old code (the never-empty-title rule). |
| BUG-6 | PASS | `buy sun cream`, `the sun also rises`, `sat with grandma`, `sun cream`, `sat exam prep`, `sun and sea trip`, `sat nav repair` and `watch sat night live` are all kept as text. Still dates: `gym sat`, `gym sat 7am`, `gym sat!`, `Gym Sat`, `lunch with sam sat`, `sat 7am gym`, `Sat 9am`, `sun 10am brunch`, `brunch on sun`, `buy sun cream on sat` (title "buy sun cream", Sat), `dentist sun 4pm`, `gym SUN 7pm!` (reminder), `meet sat at 10`, `gym every sat`, `next sun picnic`, `gym saturday`, `sunday brunch`, `call bob mon`, `mon call bob`, `standup every mon and thu 9:30`. | Behaviour change: `sat gym` (weekday first, no time) is now text, as documented. Edge: `on the sun` → Sunday, title "on the" (sun is at the end of the text). It's odd, but not a realistic task. |
| BUG-7 | PASS | Hunter repro (`bug7.py`): `done False, progress (0, 2), done_dates [], items [[], []]`. Old code had `[['2026-10-24'], ['2026-10-24']]`. Variations: a one-off task with 1 of 2 items ticked keeps `(1, 2)` after a date move (consistent with the documented scope). Saving a repeating task without changing its rule keeps the item tick `(1, 1)`. | `test_item_ticks_reset_with_task_ticks` fails on old code. |
| BUG-8 | PASS | `bug8.py`: the task title `=HYPERLINK(...)`, the note `=cmd|...`, a bare `=`, the countdown `=1+1` and the desktop note `=2+3` all have `data_type 's'`. `+1+2`, `-5 minus` and `@SUM(A1)` were already text (openpyxl only treats `=` as a formula). | When opened in Excel, `+`/`-`/`@` strings are stored as text cells and are not re-evaluated, so I judge this fine. |
| EXTRA-1 | PASS | `extra1.py`: with focus in the panel, I typed in the title and the note, opened a second panel, then called `app.quit()`. data.json has `A typed` and `n note-typed`. Old copy: the title was saved but the note was lost (`n`). | `test_quit_commits_open_panel_edits` fails on old code. |
| EXTRA-2 | PASS | `extra2.py` (`os.fsync`/`os.replace` wrapped to record calls): the call order is `['fsync', 'replace']`, the file is complete, and an average save takes 1.8 ms. | `test_save_syncs_before_replace` fails on old code. |
| EXTRA-3 | PASS | **Stress** (`stress.py`): 12 runs × 500 foreground switches cycling a second Tk Toplevel, Progman and the calendar. Half the switches were driven from Python `update()`, half from inside `mainloop` with nested `update()`. During the runs I opened and closed a day panel every 25 switches, ticked tasks every 7, and clicked panel checkboxes every 11. 6 runs had tray off and 6 had tray on. Result: all exit 0, 0 fatal errors, 0 callback errors, `expr 6*7` correct after every switch, 497–500 of 500 switches landed, 514–530 hook callbacks per run, 2 threads (tray off) / 3 threads (tray on). **Adversarial** (`adv.py`): (a) WinEvents pumped from inside a ctypes `PeekMessageW` loop inside an `after` callback (nested GIL release), 2 × 300 rounds → clean. (b) A busy Python thread competing for the GIL → no hang or crash. It is slower than the no-hook control (60 rounds in 39.5 s vs 26.7 s; faulthandler showed progress, not a deadlock). (c) After `quit()`, a new Tk + 100 switches → clean (hook unhooked). (d) App torn down *without* `quit()`, then 300 switches with a new Tk → no crash, only harmless "invalid command name …_foreground_changed" background errors. The hook keeps the widget, and so the interp, alive, so there is no use-after-free. **Fallback** (`fallback.py`, `ctypes.CDLL("tcl…")` forced to fail): `handle None`, 3 pulses in 3 s with another window in front (1 s poll), 12/s on the desktop, clean exit. **Glow behaviour**: desktop (Progman) in front → 7–12 pulses/s; another window in front → 0 pulses in 2 s (1–3 when Chrome came to the front by itself during the run: one wake-up per real foreground change). | See the risk assessment below. |

## Regressions found

None caused by this round's changes.

Pre-existing issue, made a little more visible by the BUG-2 fix (not a regression; for the next round):
- **Stale `after` callback after a quick dialog/panel close.** `Dialog.present()` (dialogs.py:83) schedules `self.after(300, lambda: …)` and never cancels it. If the dialog or panel is destroyed within 300 ms, tkinter deletes the Tcl command, but the `after` event stays queued. When Python later reuses the same `id()` for a new callback, that command name is registered again, so the stale `after` calls an unrelated callback with no arguments. Observed: `TypeError: DesktopCalendar._button.<locals>.<lambda>() missing 1 required positional argument: 'e'` and `RichNote.__init__.<locals>.<lambda>() …`.
  - Repro (`stale.py`): 40 × open a panel, close it after 30 ms, `gc.collect()`, `calendar.redraw()`, pump 400 ms. Result: new code 2 errors, old code 4 errors. `bug7.py` hit it intermittently on both versions.
  - Impact today: a line in error.log. In theory, a zero-argument callback could be invoked by mistake.
  - Fix direction: keep the job id and cancel it in `Dialog.destroy()`.
- Test hygiene: the suite prints about 21 "invalid command name …_pulse/_tick" background errors at teardown (4 on old code). These are pending `after` jobs when the root is destroyed. They are harmless, but they hide real stderr output. `App.quit()` could cancel `_tick`/`_pulse` before `destroy()`.

## EXTRA-3 risk assessment

**Recommendation: keep, with small changes.**

Why it holds up:
- The callback never touches tkinter. It only calls the Tcl C API through `ctypes.CDLL`, which releases the GIL. ctypes callbacks take the GIL through `PyGILState_Ensure`, which is correct whether the event arrives inside `Tcl_DoOneEvent` (GIL released by `_tkinter`) or inside a ctypes call (GIL released by ctypes).
- `Tcl_EvalEx("after 0 cmd")` only queues a timer. `Tcl_SaveInterpState`/`Tcl_RestoreInterpState` protect a command that is in progress.
- The hook is installed on the Tk thread, out of context, so events arrive on that same thread and the interp is never used from another thread.
- `self._proc` is kept alive for the life of the hook.
- `quit()` unhooks before `root.destroy()`.
- The hook holds `_widget`, so the interp can't be freed while the hook is set.
- A missing DLL (for example under Tcl 9) falls back to the 1 s poll, as verified.
- The fixer's first, crashing version (calling `win.after` from the callback) was correctly diagnosed. 6,000 switches plus the adversarial cases gave zero crashes.

Suggested hardening, all small:
1. In `quit()`, call `stop_hooks()` first, or put the save/commit work in a `try/finally`, so the hook is always removed before `destroy()` even if a commit or save raises.
2. Load the DLL by module handle, so it can't pick up a different `tcl86t.dll`. For example, check `ctypes.windll.kernel32.GetModuleHandleW("tcl86t.dll")` and use `ctypes.CDLL(name, handle=h)`, falling back if the handle is 0. Today `CDLL("tcl86t")` resolves to the already-loaded module, so this only guards against an odd install.
3. Set `restype`/`argtypes` for `Tcl_InterpDeleted` and `Tcl_EvalEx` (currently `int` by default; that's fine on x64 Windows, but say so).
4. If `SetWinEventHook` fails, delete the registered Tcl command.

None of these are blocking.

Reverting to the 1 s poll is not justified. The hook removes about 20 wake-ups per 20 s, and I found no crash path.

## Perf numbers

`tests/perf_check.py` (200 tasks, tray on, 20 s window, `timeout 60`):
- **Glow on (12 runs):** 0.192, 0.017, 0.233, 0.015, 0.014, 0.240, 0.202, 0.012, 0.013, 0.013, 0.014, 0.163 %. 8 PASS, 4 FAIL (≥ 0.1 %).
- **Glow off (3 runs):** 0.014, 0.219 (FAIL), 0.016 %.
- **Every run:** 3 threads, 0 child processes, 58.9–59.7 MB.

Checking the fixer's explanation (instrumented copy `perf_instr.py` / `perf_instr2.py`, which logs `calendar.redraw()` calls, `_pulse` calls and hook events inside the measurement window):
- **today_progress on, glow on (6 runs):** a minute redraw happened in the window in exactly the 2 FAIL runs (redraw took 15.6 ms → 0.153 %, and 31.0 ms → 0.206 %). The 4 runs without one measured 0.014–0.016 %.
- **today_progress off, glow on (11 runs):** 0.016, 0.011, 0.013, 0.017, 0.902, 0.022, 0.012, 0.013, 0.013, 0.011, 0.013 %. The 0.902 % run had no redraw. One further run printed nothing; its exit code wasn't captured, so it was either a hang killed by `timeout` or a crash, and I could not reproduce it. In the 6 counted runs: 0–1 pulses and 0–1 hook events per window.
- **today_progress off, glow off (7 runs):** 1.379, 0.037, 0.016, 0.038, 0.010, 0.017, 0.037 %.

Conclusion: the fixer is right. The regular 0.15–0.24 % spikes are the once-a-minute full `calendar.redraw()` for the progress bar (16–31 ms CPU for 200 tasks). With the bar off, every glow-on run with a captured exit code stayed below 0.1 % except one 0.902 % outlier. Two outliers (0.902 % and 1.379 %) had no redraw, pulse or hook activity to explain them. They appeared with the glow on and off, which points to machine noise rather than the glow. The steady state with the hook is about 0.013 %, the same as with the glow off.

Recommendation: make the minute update redraw only today's progress bar, not the whole calendar. That is a separate change.

## Suite results

```
> .venv/Scripts/python -m unittest discover -s tests -t .
Ran 91 tests in 13–75 s (one slow first run; slowest single test 2.5 s)
OK
(stderr: ~21 "invalid command name …_pulse/_tick" teardown messages; harmless, see above)

> timeout 90 .venv/Scripts/python tests/ui_day_panel.py
... all ok ...
ok   panel opens with 30+ tasks in 122 ms (< 300)
PASS

> new regression tests run against the HEAD code (qa-verify\oldnewtests)
Ran 20 tests: FAILED (failures=16, errors=2); the 2 that pass are the documented guards

> perf_check on / off: see "Perf numbers"
```
