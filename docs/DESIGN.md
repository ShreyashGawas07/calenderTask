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
- **Tasks**: one click (double-click a day) to add; time, reminder, colour,
  notes; repeat daily / weekly (chosen weekdays) / monthly / yearly every N;
  completed tasks sort to the end; unfinished one-off tasks roll over to today.
- **Reminders**: in-app pop-up in the corner with Done / Snooze 10 min / Dismiss.
- **Countdown / anniversary cards**: small cards on the desktop; yearly cards
  count to the next occurrence and show the year count.
- **Notes**: coloured sticky notes on the desktop.
- **Floating mini-calendar**: small always-on-top month view with a day list.
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
  app.py                  root controller: event queue, ticks, reminders, window management
  desktop_cal.py          the wallpaper calendar (single Canvas)
  dialogs.py              day editor, task editor, search, settings, countdown manager
  widgets.py              notes, countdown cards, mini-calendar, reminder pop-up
  export.py               xlsx export (openpyxl)
  tray.py                 tray icon (pystray), menu actions posted to the app queue
tests/test_model.py       unit tests for model.py and store.py
```

Threads: Tk runs on the main thread; the hotkey message loop and the tray icon
run on their own threads and only put actions on a `queue.Queue` that the Tk
loop drains every 100 ms.

## Data (`%APPDATA%\CalendarDesk\data.json`)

`tasks`, `countdowns`, `notes`, `date_colors`, `reminders` (fired/snoozed
state, pruned after two days) and `settings`. Recurring tasks keep one record;
per-day completion lives in `done_dates`, deleted occurrences in `skip_dates`.
Backups: one copy per day in `backups\`, newest 30 kept.
