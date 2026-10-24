# CalendarDesk

A free desktop calendar for Windows that sits on your wallpaper. It is written from scratch to replace
CalendarTask/DesktopCal, without the auto-start, background helper, bundled offers or paid tiers.
See [docs/DESIGN.md](docs/DESIGN.md) for details.

## Start it

```
.\install.ps1
```

This creates the Python environment and adds a **CalendarDesk** shortcut to the Start menu. It does not add
anything to startup. To start it with Windows, tick the box in Settings.

## Using it

| To… | Do this |
|---|---|
| Bring the calendar in front of other windows | `Ctrl+Alt+C`; press it again, press `Esc`, or click another app to send it back |
| Use the keyboard | With the calendar in front: `Ctrl+Shift+O, D` opens today's day panel, `Ctrl+Shift+C, H` the ☰ menu, `Ctrl+Shift+N` adds a task to today, `Ctrl+N` new task, `Ctrl+F` search, `Ctrl+,` settings, `←` `→` month, `Home` today, `Ctrl+M` mini calendar. `A, B` means press A, then B within 1.5 s |
| Choose your own shortcuts | Settings → **Shortcuts** (or ☰ → *Keyboard shortcuts…*): pick a command, **Change…**, press the keys. Every command can have one, on the calendar only or everywhere (global). You can't save a shortcut that another command, Windows or another running program already uses; you're warned about keys common in other apps, Windows Calculator's keys and Start-menu shortcut keys. *Global shortcuts on* frees every global key at once. Details: [docs/keyboard-shortcuts.md](docs/keyboard-shortcuts.md) |
| Add a task fast | Double-click anywhere in a day, type, press Enter (click anywhere else to close an empty box). Smart typing understands times, dates, repeats and reminders: `call mom 7pm tomorrow`, `gym every mon and thu 7am`, `rent 1st every month`, `pay bill 6pm!` (`!` or `remind me` = reminder). A line under the box shows what it understood |
| Add a task with time, reminder, repeat or colour | **+ Task**, or right-click a day → *Add task…*. Smart typing works there too: type `call mom at 7 am` and the time, date, repeat and reminder fill in (fields you set yourself are kept) |
| Picture, GIF or video background | Settings → **Appearance** → *Choose picture, GIF or video…*. Dates and tasks stay readable on top (shadowed text; date colours become a band). *Darken* sets how much the theme colour tones it down. Small pictures, GIFs and videos are upscaled and sharpened once when you choose them, and the tip under the button names a free AI upscaler (Upscayl for pictures, Video2X for videos) for real extra detail. A video plays only while you can see it (desktop or calendar in front) and pauses, using no power, otherwise; *Play video* can also limit it to the raised calendar or show a still |
| Edit a task | Click it once (or right-click → *Edit task…*) |
| Tick a task done | Click its ☐ box: it animates, then moves to the end of the day |
| See and edit everything on a day | Click the day number or **+N more** to open the day panel. There you can tick tasks, edit titles in place and add checklist items (the calendar shows `1/3`). Notes support **• List**, **1. List** and **B** (or Ctrl+B); Enter continues a list, and Enter on an empty item ends it. ⋮ moves or deletes a task, and ▸ opens a task that has no items or notes yet |
| Change month | ‹ › arrows or the mouse wheel; **Today** jumps back |
| Colour a date | Right-click the day → *Date colour* |
| Countdown or anniversary card | ☰ menu → *New countdown…*, or right-click a day → *Countdown to this date…* |
| Sticky note | ☰ menu or tray → *New note* |
| Quick-look calendar | Tray → *Mini calendar* (it lives on the wallpaper too) |
| Make the calendar any size | Settings → **Size**: Small / Medium / Large / Half screen / Full screen, or width and height sliders; text, cards and notes have their own size sliders |
| Try settings safely | Every change shows live; **Cancel** puts everything back, and ☰ / tray → *Undo last settings change* reverts the last save |
| Search, export to Excel, settings, school terms, backups | ☰ menu or the tray icon |
| Move or resize the calendar | Drag the header; drag the bottom-right corner. Text scales with the size (tick *Lock* in Settings to stop moving) |
| Resize a countdown card | Drag its bottom-right corner; double-click to change its colour and style (Minimal, Solid, Gradient, Progress ring) |
| Change the look | Settings → **Appearance**: theme (Dark, Light, Glass, Paper), accent colour, font, colours for text, weekends, holidays and grid, and the four "today" highlights (glow, TODAY badge, week row, day-progress bar with the % of the day left), each on or off |

Everything stays on the wallpaper behind your apps; only the show / hide shortcut (or clicking it on the desktop) brings it
forward, and it drops back as soon as you click another app. Reminder pop-ups are the one exception, so
you don't miss them.

Unfinished one-off tasks move to today automatically (you can turn this off in Settings). Reminders pop up
in the bottom-right corner with Done, Snooze 10 min and Dismiss.

Data is stored only on this PC, in `%APPDATA%\CalendarDesk\data.json`, with a daily backup in `backups\`
(the newest 30 are kept).

## Remove it

```
.\uninstall.ps1             # keeps your data
.\uninstall.ps1 -RemoveData # also deletes your data
```

Then delete this folder.

It is built to keep the PC fast: one process, no polling, and about 0.07 % of one CPU core while idle
(`tests\perf_check.py` measures it).

## Tests

```
.venv\Scripts\python -m unittest discover -s tests -t .
.venv\Scripts\python tests\ui_day_panel.py
.venv\Scripts\python tests\perf_check.py on
```
