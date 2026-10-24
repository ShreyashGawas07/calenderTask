# CalendarDesk — design

A free desktop calendar for Windows, written from scratch. It keeps the useful
parts of CalendarTask/DesktopCal (xdiarys) and drops the behaviour that got it
uninstalled.

## Ground rules (why the original was removed)

| Original problem | CalendarDesk |
|---|---|
| Starts with Windows by itself | Off by default; a checkbox in Settings writes/removes one `HKCU\...\Run` value |
| Extra background process (`dkdockhost`) | One process (`pythonw`), no helpers, no services |
| Bundled installs / offers, PUP flags | No installer; `install.ps1` only adds a Start-menu shortcut |
| Sticky uninstaller | `uninstall.ps1` removes shortcut + Run value (+ data with `-RemoveData`) |
| Cloud account, telemetry, paid tiers | Fully offline, no network code, every feature free |

## Features

- **Desktop calendar**: borderless, semi-transparent month view owned by the
  desktop window (`Progman`) and kept at the bottom of the z-order, so it sits on
  the wallpaper and survives *Show desktop*. `Ctrl+Alt+<key>` (default `C`)
  brings it to the front for editing; press again or click away to send it back.
- **Tasks**: double-click a day to add, with smart typing ("call mom 7pm
  tomorrow", "gym every mon and thu 7am", "rent 1st every month!"); time,
  reminder, colour, checklist, formatted notes; repeat daily / weekly (chosen
  weekdays) / monthly / yearly every N; completed tasks sort to the end;
  unfinished one-off tasks roll over to today.
- **Day panel**: every task on a day as a card with its checklist (tick, edit,
  delete, add items) and notes with bullets, numbered lists and bold, stored as a
  tiny markdown subset (`- `, `1. `, `**bold**`). Checklist rules: ticking the
  last open item ticks the task; unticking an item unticks it; ticking the task
  ticks all items; unticking the task keeps item progress. Repeating tasks track
  items per day. The calendar shows a `1/3` count instead of the items.
- **Tick animation**: the box fills, a check mark draws itself and a line sweeps
  through the text (~350 ms, about 20 frames, then it stops itself).
- **Reminders**: in-app pop-up in the corner with Done / Snooze 10 min / Dismiss.
- **Countdown / anniversary cards**: small cards on the desktop; yearly cards
  count to the next occurrence and show the year count.
- **Notes**: coloured sticky notes on the desktop.
- **Mini-calendar**: small month view with a day list; it lives on the wallpaper like the rest.
- **Indian public holidays** (from the `holidays` package), **date background
  colours**, **school-week numbers** for user-defined terms.
- **Search** across tasks, notes and countdowns; **export to Excel**.
- **Appearance**: four theme presets plus accent, font and fine-colour overrides
  (`theme.apply()` swaps module-level colours; windows pick them up on redraw).
  Today can glow (inset rings whose colour is animated every 80 ms, no redraw),
  be tinted with a TODAY badge, light up its week row and weekday, and show a
  day-progress bar; each is a setting. Calendar and card text scale with window size.
- **Countdown card styles**: minimal, solid, gradient, progress ring.

## Structure

```
CalendarDesk.pyw          entry point (pythonw, no console)
calendardesk/
  model.py                pure logic: recurrence, ordering, rollover, countdowns, school weeks
  store.py                JSON storage in %APPDATA%\CalendarDesk, atomic writes, daily backups
  holidays_in.py          cached India holidays
  winapi.py               DPI, desktop pinning, global hotkey thread, single instance, startup key
  app.py                  root controller: actions from other threads, ticks, reminders, windows
  desktop_cal.py          the wallpaper calendar (single Canvas)
  day_panel.py            day panel: task cards, checklists, notes, smart add box
  richnote.py             notes with bullets / numbers / bold <-> markdown subset
  anim.py                 the tick animation (canvas items only, stops itself)
  dialogs.py              task editor, search, settings, countdown manager
  widgets.py              notes, countdown cards, mini-calendar, reminder pop-up
  export.py               xlsx export (openpyxl)
  tray.py                 tray icon (pystray), menu actions handed to the Tk thread
tests/                    unit tests (model, parser, rich notes, animation);
                          ui_day_panel.py and perf_check.py are scripts
```

## Performance

One process, three threads (Tk, hotkey, tray), no polling. The hotkey and tray
threads hand actions to Tk with `root.after(0, …)`. The "drop back to the
wallpaper" check runs every 400 ms, and only while something is raised. Today's glow
breathes only while you can see it (the calendar raised, or the desktop itself in
front); otherwise it is drawn steady and no timer runs: a Windows foreground-change
hook (`SetWinEventHook`, delivered through Tk's own message loop, no thread) wakes it
when another window comes to the front. The reminder clock wakes once a minute, just
after the minute turns (or sooner for a snoozed reminder); it moves only the
day-progress bar's line, and redraws the whole calendar only when the day changes. Measured with `tests/perf_check.py` (CPU
cycles over 20 s, 200 tasks): about 0.01-0.02 % of one core with the glow on or
off, about 59 MB. The day panel opens in
under 0.2 s with 30 detailed tasks: the first cards are built at once, the rest
just after.

## Data (`%APPDATA%\CalendarDesk\data.json`)

`tasks`, `countdowns`, `notes`, `date_colors`, `reminders` (fired/snoozed
state, pruned after two days) and `settings`. Recurring tasks keep one record;
per-day completion lives in `done_dates`, deleted occurrences in `skip_dates`.
Backups: one copy per day in `backups\`, newest 30 kept.
