# Keyboard shortcuts

Status: built and tested (commit `0105aff`, 2026-10-25). The two bug-hunt → fix → verify QA rounds
have **not** been run yet; they are on hold until asked for.
Design notes: [`superpowers/specs/2026-10-25-keyboard-shortcuts-design.md`](superpowers/specs/2026-10-25-keyboard-shortcuts-design.md).

## What it does

Every CalendarDesk command can be run from the keyboard, with a shortcut you choose in
**Settings → Shortcuts** (also ☰ menu → *Keyboard shortcuts…*). Instead of moving the mouse to the ☰
menu you press, for example, `Ctrl+Shift+C, H`.

- **One step**: modifiers plus one key, e.g. `Ctrl+F`, `Ctrl+Alt+C`, `Home`.
- **Two steps (chord)**: `Ctrl+Shift+O, D` means *press Ctrl+Shift+O, then D within 1.5 s*. The second
  key works with the modifiers still held or released. This is how "Ctrl+Shift+O+D" is written:
  Windows cannot register two letter keys held together, so a chord stands in for it.
- **Where it works**: *on the calendar* (while the calendar or mini calendar has the keyboard; never
  while you are typing in a box) or *everywhere* (a global shortcut that works in any program).

## Commands and default shortcuts

| Command | Default | Works |
|---|---|---|
| Show / hide calendar | `Ctrl+Alt+C` (the old hotkey letter, if you had changed it) | everywhere |
| Open today's day panel | `Ctrl+Shift+O, D` | on calendar |
| Open the ☰ menu | `Ctrl+Shift+C, H` | on calendar |
| Add a task to today (smart typing) | `Ctrl+Shift+N` | on calendar |
| New task… | `Ctrl+N` | on calendar |
| Search | `Ctrl+F` | on calendar |
| Settings | `Ctrl+,` | on calendar |
| Next / previous month | `Right` / `Left` | on calendar (the mini calendar moves itself) |
| Go to today | `Home` | on calendar |
| Send calendar back to the wallpaper | `Esc` | on calendar |
| Mini calendar | `Ctrl+M` | on calendar |
| New note, New countdown…, Countdowns…, Show all notes and cards, Export…, Undo last settings change, Keyboard shortcuts…, Exit | none (set your own) | — |

## Settings → Shortcuts

- A list of every command with its shortcut and where it works.
- **Change…** (or double-click) opens the recorder: press the keys and see right away whether they
  are free. Global shortcuts are paused while you record, so pressing an existing one records it
  instead of running it.
- **Clear** removes a shortcut, **Reset** restores one default, **Reset all** restores them all.
- **Works everywhere (global)** switches the selected command between global and calendar-only.
- **Global shortcuts on**: untick it to free every global key at once (e.g. while gaming) without
  losing your choices.
- Nothing changes until **Save**. **Cancel** keeps the old shortcuts, and *Undo last settings change*
  puts back the previous ones, including what is registered with Windows.
- The ☰ menu shows each command's shortcut next to it.

## Conflict checks

**Errors** (you can't save until you change or clear the shortcut; Save jumps to the clashing one):

- Another CalendarDesk command already uses it, or one is the first step of the other's chord
  (`Ctrl+Shift+O` and `Ctrl+Shift+O, D` can't both exist). Two chords may share a first step.
- Windows keeps it: `Win+<key>`, `Ctrl+Alt+Delete`, `Ctrl+Shift+Esc`, `Alt+Tab`, `Alt+F4`,
  `Ctrl+Esc`, `Alt+Esc`, `Win+Shift+S`, `Win+Ctrl+D` and similar.
- Another running program has already registered it. CalendarDesk finds this by briefly trying to
  register the keys itself; Windows doesn't say which program holds them.
- A global shortcut without Ctrl, Alt or Win (that key would stop typing everywhere). A calendar-only
  shortcut that uses Win.

**Warnings** (you can still save):

- It is the *Shortcut key* of a Start-menu or desktop shortcut (read from the `.lnk` files), for
  example a Calculator shortcut you gave a key.
- For global shortcuts:
  - keys most programs use (`Ctrl+C/V/X/Z/S/F/N/T/W…`)
  - browser and editor keys (`Ctrl+Shift+T/N/I/J…`, `Ctrl+Tab`, `Alt+Left`…)
  - `Alt+letter` menu keys and function keys
  - Windows Calculator's own keys (`Alt+1…5` modes, `Ctrl+M/P/Q/R/L` memory, `Ctrl+H` history)

## How it is built

| Part | File | What it does |
|---|---|---|
| Model | `calendardesk/shortcuts.py` | Command list and defaults, `parse` / `fmt` of shortcut text, virtual-key table, `effective(settings)`, `conflicts(...)`, `.lnk` shortcut-key scan. Pure Python, no Tk. |
| Global keys | `calendardesk/winapi.py` → `HotkeyThread`, `probe_hotkey` | The existing hotkey thread now registers every global shortcut's first step. When one is pressed, its chord's second keys are registered for 1.5 s (a Windows thread timer), then released. `set_bindings()` swaps the set (used on Save, Undo and while recording). |
| Calendar keys | `calendardesk/app.py` → `apply_shortcuts`, `_key` | One Tk `<KeyPress>` binding on the calendar and mini calendar. It skips Entry, Text and Combobox widgets and keeps chord state with a single `after(1500)`. |
| Settings UI | `calendardesk/shortcut_ui.py`, `dialogs.py` | Shortcuts tab, key recorder, Save validation. |
| Storage | `settings["shortcuts"]`, `settings["global_shortcuts"]` | Only differences from the defaults are stored, e.g. `{"open_today": {"keys": "Ctrl+Alt+D", "global": true}}`. Broken entries fall back to the default. `settings["hotkey"]` still sets the default show / hide letter, so old data keeps working. |

**Performance:**

- Still one process with three threads (Tk, hotkey, tray).
- Nothing polls: the hotkey thread sleeps in `GetMessage`, and calendar keys cost nothing until a
  key is pressed.
- Measured with `tests/perf_check.py`: idle CPU is 0.10–0.13 % of one core. The code from before
  this feature measures the same 0.12–0.13 % on this machine at the same time (the machine is busier
  than when the earlier 0.01–0.02 % was recorded).
- Memory is about 60 MB, with no child processes.

## Tests

| File | Covers |
|---|---|
| `tests/test_shortcuts.py` (29) | parsing and formatting, Tk key events, defaults and old hotkey letter, every conflict rule, `.lnk` reading |
| `tests/test_hotkeys.py` (6) | real `RegisterHotKey` thread: singles, chords, chord time-out releasing keys, re-binding, failures |
| `tests/test_shortcut_app.py` (20) | in the running app: arrows / Home / Esc, chords (held or released modifiers, time-out, wrong key), no shortcuts while typing, quick add from another month, a real Tk key event, mini calendar, global key end-to-end, global switch, Settings save / cancel / undo, save refused on a clash, the menu item opening the tab, the recorder |

Results at commit `0105aff`:

- Full suite: **162 tests OK** (`.venv\Scripts\python -m unittest discover -s tests`).
- `tests/ui_day_panel.py`: **PASS**, panel opens in 174 ms.

Fixes to existing tests made along the way:

- `test_day_panel.py` no longer breaks once its fixed date is in the past. Rollover used to move its
  tasks to today, so 5 of those tests had started failing on 2026-10-25.
- `perf_check.py` no longer clashes with a running CalendarDesk. It uses a free hotkey, because a
  "key already used" warning box costs about 0.9 % CPU while it is open. It now also prints CPU by
  thread.

## Limits worth knowing

- Keys that Windows takes before any program sees them (`Win+L`, `Ctrl+Alt+Delete`…) can't be
  recorded, and they would be refused anyway.
- On keyboard layouts with AltGr, AltGr arrives as `Ctrl+Alt`, so `Ctrl+Alt+<key>` shortcuts can
  clash with typing special characters there.
- Calendar-only shortcuts work while the calendar or mini calendar has the keyboard, not inside the
  day panel or dialogs.
- A running CalendarDesk picks this up only after it is restarted.

## Still to do (when asked)

- QA round 1 and round 2: bug hunter → fixer → verifier, with reports in `docs/qa/`.
- Push `main` to GitHub.
