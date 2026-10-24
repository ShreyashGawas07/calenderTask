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
| Bring the calendar in front of other windows | `Ctrl+Alt+C` (change the letter in Settings); press it again or click another app to send it back |
| Add a task fast | Double-click anywhere in a day, type, press Enter |
| Add a task with time, reminder, repeat or colour | **+ Task**, or right-click a day → *Add task…* |
| Edit a task | Click it once (or right-click → *Edit task…*) |
| Tick a task done | Click its ☐ box (done tasks move to the end of the day) |
| See everything on a day | Click the day number or **+N more** |
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
| Change the look | Settings → **Appearance**: theme (Dark, Light, Glass, Paper), accent colour, font, colours for text, weekends, holidays and grid, and the four "today" highlights (glow, TODAY badge, week row, day-progress bar), each on or off |

Everything stays on the wallpaper behind your apps; only the hotkey (or clicking it on the desktop) brings it
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

## Tests

```
.venv\Scripts\python -m unittest discover -s tests -t .
```
