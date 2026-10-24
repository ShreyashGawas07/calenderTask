# Day panel, checklists, smart typing, tick animation, performance — design

Date: 2026-10-24 · Status: approved in conversation, awaiting spec review

## Goal

Let the user see and edit everything about a day's tasks in one place: each task can hold a
checklist and formatted notes (bullets, numbered lists, bold). Make writing tasks faster with smart
typing, and make ticking a task feel satisfying with a short animation. All of this must keep the PC
fast: **one process, near-zero idle CPU**.

What the user said: tasks keep their time/reminder/repeat and gain checklists and formatted notes;
the calendar shows a progress count (e.g. `1/3`), not the sub-items; smart typing and formatting in
notes are wanted; Tab-indent shortcuts and a multi-line quick-add box are not. Assumptions are
marked *(assumed)*.

## 1. Performance rules (apply to everything below)

| Rule | Budget |
|---|---|
| Processes | Exactly one (`pythonw.exe`), no child processes |
| Threads | No new threads beyond today's three (Tk, hotkey, tray) |
| Idle CPU | < 0.1 % of one core, measured over 20 s with the calendar on the wallpaper (today: 0.55 % with glow off, 2.5 % with glow on) |
| Memory | < 70 MB working set with 200 tasks |
| Redraw | Only on data/setting changes, day change, or the one-minute progress-bar tick |
| Libraries | No new dependencies, no web engine, no network |

Changes to meet them:

- **No polling loop.** Remove the 100 ms `_poll`. The hotkey and tray threads hand actions to Tk with
  `root.after(0, …)`, which Tk queues safely across threads (Python's Tcl is threaded); a
  `queue.Queue` remains only as the payload carrier if needed.
- **"Drop back to wallpaper" check** (`_settle`) runs on a 400 ms timer **only while** a pinned
  window is raised; it stops once everything is back.
- **Glow pulses only when visible**: while the calendar is raised, or while the desktop itself
  (`Progman`/`WorkerW`) is the foreground window. Otherwise the glow is drawn static at full
  strength and no timer runs; a foreground-change hook (`winapi.ForegroundHook`) wakes it. If the
  hook can't be set up, a 1 s check runs instead.
- **Animations are self-terminating**: each runs a fixed number of frames (~16 ms apart) then stops.

## 2. Data model

Task gains two optional fields (old data stays valid; missing fields mean empty):

```json
"items": [{"id": "a1b2c3", "text": "collect numbers", "done": false, "done_dates": []}],
"note":  "1. use Q3 template\n2. cc **Riya**\n- bring charger"
```

- `items` order is display order. For one-off tasks an item uses `done`; for repeating tasks it uses
  `done_dates` (per occurrence), exactly mirroring the task's own `done` / `done_dates` rules.
- New pure helpers in `model.py`: `item_done(task, item, day)`, `set_item_done(task, item, day, v)`,
  `progress(task, day) -> (done, total)`.
- **Checklist rules**: ticking the last open item ticks the task; unticking any item unticks the
  task; ticking the task ticks all its items; unticking the task leaves items as they are *(assumed:
  so you don't lose progress by accident)*.
- `note` stays a string. Formatting is a tiny markdown subset: lines starting `- ` or `• ` (bullet),
  `1. ` (numbered), and `**bold**` spans. Plain old notes are already valid. Excel export writes the
  note text as-is.

## 3. Day panel (replaces the current day dialog)

Opened by clicking a day number / "+N more" on the calendar or a day in the mini calendar.

```
Sat 24 Oct 2026 · Term 2 week 3 · Holiday name             [Date colour ▾]
[ Add a task… e.g. "call mom 7pm"                                  ] [Add]
   ↳ Tomorrow · 19:00 · repeats weekly          (live smart-typing preview)
┌───────────────────────────────────────────────────────────────────┐
│ ☐  Submit report            10:00 · 🔔15m · ↻ weekly        ⋮     │
│    ☑ collect numbers                                     ✕        │
│    ☐ write summary                                       ✕        │
│    [+ add item]                                                    │
│    Notes  [• List] [1. List] [B]                                   │
│    1. use Q3 template                                              │
│    2. cc Riya                                                      │
└───────────────────────────────────────────────────────────────────┘
┌ ☐  Call mom                 19:30                          ⋮  ▸ ┐   (collapsed card)
┌ ☑  Gym                      07:00                          ⋮  ▸ ┐   (done → bottom)
```

- A scrollable list of **task cards** (ttk/Tk widgets inside a Canvas scroller). Cards with items
  or notes start expanded; others start collapsed with a ▸ toggle *(assumed)*.
- **Title** edits in place (Entry); saves on Enter/focus-out. Chips show time, reminder, repeat;
  clicking a chip or ⋮ → *Edit details…* opens the existing task dialog. ⋮ also offers *Move to next
  day*, *Delete* (one-off) or *Delete this day / all repeats* (repeating).
- **Checklist rows**: animated checkbox, Entry for text (edit in place), ✕ to delete. "+ add item"
  Entry adds on Enter and keeps focus for the next item.
- **Notes**: a `Text` widget with tags for bullet, numbered and bold. Buttons toggle bullet/numbered
  on the current line(s) and bold on the selection. Pressing Enter on a list line continues the list
  (renumbering numbered lines); Enter on an empty list line ends the list. Stored back as the markdown
  subset above. Saves 600 ms after typing stops.
- Every change saves immediately (debounced for typing) and refreshes the calendar; the panel itself
  re-sorts only after the tick animation finishes, so cards don't jump while you're typing.
- Date colour picker and "Countdown to this day" move into the header (from the old dialog).
- One panel per day (re-opening focuses the existing one). The panel is a normal window, not pinned
  and not always-on-top.

## 4. Calendar and mini calendar

- Task lines show a compact progress count when the task has items: `☐ 10:00 Submit rep… 1/3`
  (count in muted colour; accent when complete).
- Ticking a task box on the calendar or mini calendar plays the tick animation, then redraws.

## 5. Smart typing

`model.parse_quick(text, today) -> {title, date, time, repeat, interval, weekdays, remind}`: pure,
unit-tested, English only, no network. Used by the calendar quick-add box and the panel's add box,
with a live preview line under the box showing what was understood.

Understood (case-insensitive, anywhere in the text; recognised words are removed from the title):

| Kind | Examples |
|---|---|
| Time | `7pm`, `7:30pm`, `7.30 pm`, `19:30`, `at 19.00`, `at 7` (→ 07:00 *(assumed: 24-hour unless am/pm)*), `noon`, `midnight`. A bare `2.50` is not a time (a price, a version) |
| Date | `today`, `tomorrow`/`tmrw`, `day after tomorrow`, weekday names (`mon`, `friday` → next one, today if it's today), `next monday` (→ the one after this week's), `24 oct`, `oct 24`, `24/10`, `24-10-2026`, `2026-11-05`, `1st`, `on the 5th` (→ next 5th) |
| Repeat | `daily`/`every day`, `weekly`/`every week`, `every monday` / `every mon and thu` (weekly on those days), `monthly`/`every month`, `yearly`/`every year`, `every 2 days` / `every 3 weeks` |
| Reminder | `remind me` or a trailing `!` → reminder on (needs a time; at the time) |

Rules: if a time is given but no date, the date is the clicked day (quick-add) or today (panel
add box on today) — i.e. the day the box belongs to. If nothing is recognised, the whole text is the
title. If parsing would leave an empty title, keep the original text as the title.

Ambiguous forms count only where they are clearly a date, so ordinary words and numbers stay in the
title: `sat`/`sun` (not `saturday`/`sunday`) and a yearless `24/10` only after `on`, at the very end
of the text, or with nothing but a time between them and the start or end (`gym sat 7am`,
`sun 10am brunch`; but `buy sun cream`, `sat with grandma`, `buy 3/4 cup flour` are just text). A
yearless dash form (`5-11`) needs `on` (`pages 1-12`, `score 3-1` are text). A date that is part of a
longer run of numbers (`2 3/4`, `1/2/3/4`) is never a date.

## 6. Tick animation (~350 ms, 20 frames)

On a canvas (calendar, mini calendar, panel checkboxes share one `TickAnimation` helper):
1. 0–120 ms: box fills with the accent colour from the centre (scale 0.6 → 1.0).
2. 80–240 ms: a check mark draws itself in two strokes (white/readable-on-accent).
3. 120–350 ms: a strike line sweeps left → right across the text, which fades to the "done" colour.
4. End: data is saved and the view redraws (the task moves down).

Unticking plays a quick 120 ms reverse fade. Clicks during an animation are ignored for that task.
Only the animated items are touched per frame (no full redraws), and the animation stops itself.

## 7. Files

| File | Change |
|---|---|
| `model.py` | item helpers, `progress`, `parse_quick` |
| `richnote.py` (new) | markdown-subset ⇄ Tk `Text` tags, list continuation |
| `anim.py` (new) | `TickAnimation` for canvases |
| `day_panel.py` (new) | the day panel; replaces `DayDialog` in `dialogs.py` |
| `desktop_cal.py`, `widgets.py` | progress count, tick animation, glow visibility rule, smart quick-add |
| `app.py`, `winapi.py`, `tray.py` | thread hand-off via `after`, timers only when needed, desktop-foreground check |
| `export.py` | items column ("2/3: a ✓, b, c") |
| `tests/` | parser, item rules, rich-note round-trip, performance check |

## 8. Testing

- Unit tests: `parse_quick` (each row of the table, plus nothing-recognised and empty-title cases),
  checklist rules for one-off and repeating tasks, `progress`, rich-note round-trip
  (markdown → Text → markdown is identical).
- Automated UI script: open panel, add tasks via smart typing, add/tick/delete items, format notes,
  tick with animation, verify saved JSON and calendar count.
- Performance script: idle CPU over 20 s (glow on and off) < 0.1 % of one core; one process; thread
  count unchanged; memory < 70 MB with 200 generated tasks; panel opens in < 300 ms with 30 tasks.

## 9. Quality pipeline (after the build)

1. **Bug hunter** agent: reviews code and runs the app's scripts and tests to find bugs, data-loss
   risks, security issues and performance problems. Writes `docs/qa/bug-report.md` with numbered
   findings (steps, expected, actual, severity).
2. **Fixer** agent: fixes each finding with a regression test where practical; writes
   `docs/qa/fix-report.md` mapping finding → change → test.
3. **Verifier** agent: independently re-tests each finding; marks PASS or FAIL with evidence in
   `docs/qa/verify-report.md`. FAILs go back to the fixer; repeat until all pass (max 3 rounds, then
   remaining items are reported to the user).

Agents edit only files in this project; none launches long-lived processes, and each test run on a
temporary data folder, never the user's real data.

## Out of scope

Tab-indent sub-items, multi-line quick-add, sub-sub-items, drag-reordering cards, images in notes,
sync, AI/online parsing.
