# Keyboard shortcuts for every command — design

Date: 2026-10-25 · Status: user asked to design and build it directly ("think about it yourself")

## Goal

Let the user run every CalendarDesk command from the keyboard, with shortcuts they choose in
Settings, e.g. `Ctrl+Shift+O, D` to open today's day panel or `Ctrl+Shift+C, H` to open the ☰ menu.
Warn when a shortcut is already used by Windows, another program, a Start-menu shortcut
(e.g. Calculator) or another CalendarDesk command. Keep the app fast: no new threads, no polling.

## Shortcut format

- One step: modifiers + one key, e.g. `Ctrl+Alt+C`, `Ctrl+F`, `Home`.
- Chord (two steps): `Ctrl+Shift+O, D` = press Ctrl+Shift+O, then D within 1.5 s. Windows cannot
  register two letter keys held together, so "Ctrl+Shift+O+D" is entered as this chord; the second key
  works with the same modifiers still held or with them released.
- Modifiers: Ctrl, Alt, Shift, Win (Win only for global shortcuts). Keys: A–Z, 0–9, F1–F24, arrows,
  Home, End, PageUp, PageDown, Insert, Delete, Space, Enter, Tab, Esc, Backspace and , . / ; ' [ ] \ - = `.
- Stored in `settings["shortcuts"]` as `{action: {"keys": "Ctrl+Shift+O, D", "global": false}}`;
  missing actions use their default. Empty `keys` = no shortcut. Old data: the `hotkey` letter
  (Ctrl+Alt+letter) stays the default for *Show / hide calendar*.

## Scope

- **Global**: works in any program (Win32 `RegisterHotKey` on the existing hotkey thread).
- **Calendar**: works while the calendar or mini calendar has the keyboard (Tk key bindings), never
  while typing in a text box.
- Default: only *Show / hide calendar* is global. Global shortcuts take the key away from every other
  program, so others are global only when the user ticks it (with a warning for common app keys).
- A switch "Global shortcuts on" turns all global ones off (e.g. while gaming) without losing them.

## Commands and defaults

| Command | Default | Scope |
|---|---|---|
| Show / hide calendar | Ctrl+Alt+C (old hotkey letter) | global |
| Open today's day panel | Ctrl+Shift+O, D | calendar |
| Open the ☰ menu | Ctrl+Shift+C, H | calendar |
| Add a task to today (smart typing) | Ctrl+Shift+N | calendar |
| New task… (full form) | Ctrl+N | calendar |
| Search | Ctrl+F | calendar |
| Settings | Ctrl+, | calendar |
| Next / previous month | Right / Left | calendar |
| Go to today | Home | calendar |
| Send calendar back to the wallpaper | Esc | calendar |
| Mini calendar | Ctrl+M | calendar |
| New note, new countdown, countdowns, show all notes and cards, export, undo settings, keyboard shortcuts, exit | none | — |

## Conflict checks (when recording and when saving)

Errors (cannot save):
- the same shortcut, or a chord whose first step equals another single shortcut (or vice versa),
  is used by another CalendarDesk command in an overlapping scope (a global shortcut overlaps all);
- reserved by Windows (Win+L, Win+D, Win+E, Win+R, Win+Tab, Win+number…, Ctrl+Alt+Delete,
  Ctrl+Shift+Esc, Alt+Tab, Alt+F4, Ctrl+Esc, Alt+Esc, Win alone…);
- a global shortcut without Ctrl, Alt or Win (it would stop that key from typing), or a calendar
  shortcut with Win;
- another running program has already registered it (checked by trying to register it; Windows
  doesn't say which program).

Warnings (can save):
- a Start-menu or desktop shortcut's "Shortcut key" (read from the .lnk files), e.g. Calculator;
- for global shortcuts: keys most apps use (Ctrl+C/V/X/Z/Y/A/S/F/N/O/P/T/W…), common browser and
  editor keys (Ctrl+Shift+T/N/O/I/J/C/P…), function keys, Alt+letter menus, and the Windows
  Calculator's own keys (Alt+1…5 modes, Ctrl+M/P/Q/R/L memory, Ctrl+H history…).

## UI

Settings → **Shortcuts** tab: a list of commands (shortcut, scope). Select one → **Change…** opens a
recorder ("Press the keys…", optional second key within 1.5 s) that shows conflicts live; global
shortcuts are paused while recording. Also **Clear**, **Works everywhere (global)** tick, **Reset**,
**Reset all**, and the "Global shortcuts on" switch. Shortcuts apply on Save (Cancel and *Undo last
settings change* restore them); if registering fails at save, the user is told which ones.
The ☰ menu shows each item's shortcut and has **Keyboard shortcuts…** (opens this tab).

## Performance

The existing hotkey thread registers all global shortcuts and blocks in `GetMessage`. A chord's
second keys are registered only for 1.5 s after its first step (a thread timer), then released.
Calendar shortcuts are a single Tk `<KeyPress>` binding per window. Nothing polls.
