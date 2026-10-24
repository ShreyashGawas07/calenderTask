"""CalendarDesk — free desktop calendar. Run with pythonw (no console window)."""
import os
import site
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# Started with the main pythonw.exe (not the venv's launcher stub, which would add a second
# process), so load the project's packages from .venv directly.
_packages = os.path.join(HERE, ".venv", "Lib", "site-packages")
if os.path.isdir(_packages) and _packages not in sys.path:
    site.addsitedir(_packages)

from calendardesk import winapi  # noqa: E402


def main():
    if not winapi.single_instance():
        winapi.user32.MessageBoxW(None, "CalendarDesk is already running.\n\n"
                                  "Use the tray icon or Ctrl+Alt+C (default hotkey) to show it.",
                                  "CalendarDesk", 0x40)
        return
    try:
        from calendardesk.app import App
        App().run()
    except Exception:
        from calendardesk.store import default_dir
        os.makedirs(default_dir(), exist_ok=True)
        with open(os.path.join(default_dir(), "error.log"), "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
        winapi.user32.MessageBoxW(None, "CalendarDesk hit an error and closed.\n"
                                  f"Details are in {default_dir()}\\error.log", "CalendarDesk", 0x10)


if __name__ == "__main__":
    main()
