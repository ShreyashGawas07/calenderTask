"""JSON storage with atomic writes and daily backups."""
import copy
import json
import os
import shutil
from datetime import date, datetime, timedelta

APP_NAME = "CalendarDesk"
KEEP_BACKUPS = 30

DEFAULT_SETTINGS = {
    "opacity": 0.88,
    "start_with_windows": False,
    "hotkey": "C",  # letter of the default show / hide shortcut, Ctrl+Alt+<letter>
    "shortcuts": {},  # {command: {"keys": "Ctrl+Shift+O, D", "global": False}}; missing = default
    "global_shortcuts": True,
    "rollover": True,
    "show_holidays": True,
    "show_week_numbers": True,
    "week_starts_monday": True,
    "font_size": 9,
    "locked": False,
    "school_terms": [],
    "theme": "dark",
    "accent": None,
    "font_family": "Segoe UI",
    "colors": {},
    "auto_scale": True,
    "card_scale": 1.0,
    "today_glow": True,
    "today_tint": True,
    "today_week": True,
    "today_progress": True,
    "calendar_geometry": None,
    "mini_geometry": None,
}


def default_dir():
    if os.environ.get("CALENDARDESK_DATA"):  # lets tests and trial runs use a separate folder
        return os.environ["CALENDARDESK_DATA"]
    return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), APP_NAME)


def empty_data():
    return {"version": 1, "tasks": [], "countdowns": [], "notes": [],
            "date_colors": {}, "reminders": {}, "settings": copy.deepcopy(DEFAULT_SETTINGS)}


class Store:
    def __init__(self, folder=None):
        self.folder = folder or default_dir()
        self.path = os.path.join(self.folder, "data.json")
        self.backup_dir = os.path.join(self.folder, "backups")
        os.makedirs(self.backup_dir, exist_ok=True)
        self.data = self._load()

    def _load(self):
        data = empty_data()
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    loaded = json.load(f)
                data.update(loaded)
            except (OSError, ValueError):
                # Keep the broken file for manual recovery instead of overwriting it.
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                shutil.copy2(self.path, os.path.join(self.folder, f"data.corrupt-{stamp}.json"))
        settings = copy.deepcopy(DEFAULT_SETTINGS)
        settings.update(data.get("settings") or {})
        data["settings"] = settings
        return data

    @property
    def settings(self):
        return self.data["settings"]

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())  # on disk before it replaces data.json, so a power cut can't leave it empty
        os.replace(tmp, self.path)

    def backup(self, today=None):
        """Copy today's data once per day and keep the newest KEEP_BACKUPS copies."""
        if not os.path.exists(self.path):
            return
        today = today or date.today()
        target = os.path.join(self.backup_dir, f"data-{today.isoformat()}.json")
        shutil.copy2(self.path, target)
        backups = sorted(n for n in os.listdir(self.backup_dir) if n.startswith("data-"))
        for old in backups[:-KEEP_BACKUPS]:
            os.remove(os.path.join(self.backup_dir, old))

    def list_backups(self):
        return sorted((n for n in os.listdir(self.backup_dir) if n.startswith("data-")), reverse=True)

    def restore(self, name):
        self.backup()
        shutil.copy2(os.path.join(self.backup_dir, name), self.path)
        self.data = self._load()

    def prune_reminders(self, today=None):
        cutoff = ((today or date.today()) - timedelta(days=2)).isoformat()
        self.data["reminders"] = {k: v for k, v in self.data["reminders"].items()
                                  if k.split("|")[1] >= cutoff}
