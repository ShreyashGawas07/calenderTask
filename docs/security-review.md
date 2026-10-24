# Security and privacy review (open-source readiness)

Reviewed: the working tree on top of `be1757f` (25 Oct 2026), including the new background-picture/video code, plus the
whole git history (14 commits, every file ever committed).

Scope: a focused source review for publishing the repository. It is not a multi-agent penetration test. Nothing was
probed over a network, because the app has no network code.

## Summary

| Area | Result |
|------|--------|
| Secrets (API keys, tokens, passwords, private keys) in code or history | **None found** |
| Personal data in the code | **None.** The app has no built-in names, e-mails, phone numbers or paths |
| Personal data in the docs | **Fixed.** Your Windows user name was in 5 QA reports (`C:\Users\<name>\…` scratch paths) |
| Personal data in git history | **Open: your decision.** The same 5 paths are in old commits, and every commit's author e-mail is your personal Gmail address |
| Network access | **None.** No sockets, HTTP, updates or telemetry. Nothing leaves the PC |
| Running other programs / code | **None** apart from opening the data folder and an exported Excel file in their default apps (`os.startfile`, on your click) |
| Where your data lives | `%APPDATA%\CalendarDesk` (per-user, never inside the repository). `.gitignore` now also blocks `data*.json`, `error.log`, `backups/`, `backgrounds/`, videos and GIFs, as a safety net |

## What an attacker could do with the published source

Very little, by design.

- **There is no server, account or API to attack.** CalendarDesk runs only on the PC it is installed on and talks to
  nothing. Publishing the code reveals how it works, not anything about the people using it.
- **Your tasks, notes and settings are never in the repository.** They stay in `%APPDATA%\CalendarDesk\data.json`
  on your PC. The only way someone else gets them is through access to your Windows account, which is outside the app.
- **Files the app reads:**
  - its own `data.json`;
  - pictures and videos you choose for the background;
  - the first 66 bytes of Start-menu/desktop shortcut files, only to warn you when a keyboard shortcut is already taken.

  None of these come from the internet.
- **The background feature copies the file you pick** into `%APPDATA%\CalendarDesk\backgrounds\` under a random name
  (`bg-<random>.png/.mp4`). The settings remember only the original file name (for example `holiday.mp4`), never its
  folder path, so the data file never records where your files live.
- **"Start with Windows"** writes one quoted command to your own `HKCU\…\Run` key, only when you tick it, and removes it
  when you untick it.
- **Excel export already blocks formula injection.** A task titled `=HYPERLINK(...)` is written as text, not as a formula.
- **The low-level Windows hooks** (foreground-window events, global hotkeys) only receive "which window is in front" and
  "this hotkey was pressed". They never see keystrokes or window contents.

## Checks performed

1. **Searched every tracked and new file** for: your names, e-mail addresses, `C:\Users\…` paths, `AppData`, phone
   numbers, and key or token patterns. The only hits were the QA-report scratch paths, now replaced with
   `%TEMP%\claude\…` and `C:/path/to/CalenderTask`.
2. **Searched the full history** (`git log --all -p`) for secrets and personal strings.
   - The digit runs flagged were a Windows file-format GUID (`0114020000000000c000000000000046`) and a commit hash. Neither
     is sensitive.
   - No file was ever committed and later deleted, so nothing is hidden in history beyond what is listed here.
3. **Searched the code for dangerous calls:**
   - networking (`socket`, `urllib`, `requests`, `http`)
   - process launching (`subprocess`, `os.system`, `ShellExecute`)
   - running code from text (`eval`/`exec`, `pickle`, `yaml`)
   - Tcl script building, and registry writes

   Only the expected, user-triggered uses above were found.
4. **File handling.**
   - Data saves are atomic and fsync'd.
   - A corrupt `data.json` is kept aside, not overwritten.
   - Background imports are written to `*.part` and renamed only when complete.
   - Unused background files are deleted at startup, only if their names start with `bg-` inside the app's own folder.
   - Fixed in this review: very large pictures are now stored at most 4K wide or tall. Before, a 100-megapixel photo
     would have been kept full size and re-scaled on every resize. This only slowed your own PC; it was not a security
     problem.
5. **Media decoding.** Pictures are read by Pillow and videos by FFmpeg (PyAV) and by Windows' own Media Foundation,
   only for a file you choose yourself. Keep those libraries updated, as for any program that opens media files.
6. **Dependencies.** `requirements.txt` pins exact versions (`pillow`, `pystray`, `holidays`, `openpyxl`, `av`), so an
   install never silently picks up a new release.

## Your decisions before making the repository public

1. **Commit e-mail.** All 14 commits carry your personal Gmail address, which anyone can read from a public
   repository (`git log`).
   - **For future commits:** set GitHub's private address. Find it under *GitHub → Settings → Emails → "Keep my email
     addresses private"*, then run:
     `git config user.email "<id>+ShreyashGawas07@users.noreply.github.com"`
   - **For existing commits:** the only way to remove the address is to rewrite history, for example with
     `git filter-repo --mailmap`, and then force-push. That changes every commit id. Do it before anyone else clones
     the repository, or not at all.
2. **Old QA paths.** Your Windows user name is still in the history of the 5 QA reports. It is low risk (a user name,
   not a password), and the same history rewrite would remove it. If you rewrite for the e-mail, include these files.
3. **Optional hardening:** add a `SECURITY.md` explaining how to report problems. Before attaching `error.log` to a public
   bug report, check it first: tracebacks contain your Windows user name in file paths.
