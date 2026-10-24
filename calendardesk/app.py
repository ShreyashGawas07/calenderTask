"""Application controller: owns the data, the windows, the hotkey, the tray and the reminder clock."""
import copy
import os
import traceback
import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import colorchooser, filedialog, messagebox

from . import model, theme, winapi
from .desktop_cal import DesktopCalendar
from .day_panel import DayPanel
from .dialogs import CountdownDialog, CountdownManager, SearchDialog, SettingsDialog, TaskDialog
from .store import Store
from .widgets import CountdownCard, MiniCalendar, NoteWindow, ReminderPopup

TICK_MS = 15_000


class App:
    def __init__(self, store=None, tray=True):
        winapi.set_dpi_aware()
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("CalendarDesk")
        self.root.report_callback_exception = self._report_error
        self.store = store or Store()
        self.views = []
        self.notes, self.cards = {}, {}
        self.mini = None
        self.settings_undo = None  # snapshot from before the last saved settings change
        self._day = self.today()

        self.store.backup()
        self.store.prune_reminders()
        if self.settings["rollover"]:
            model.rollover(self.store.data["tasks"], self._day)
        self.save()

        theme.apply(self.settings)
        self.calendar = DesktopCalendar(self)
        self._open_desktop_items()
        self.hotkey = None
        self._start_hotkey()
        self.tray = None
        if tray:
            from .tray import Tray
            self.tray = Tray(self.post)
            self.tray.start()
        self._settling = False
        self.root.after(2000, self._tick)

    # -- basics ------------------------------------------------------------
    @property
    def settings(self):
        return self.store.settings

    def today(self):
        return date.today()

    def run(self):
        self.root.mainloop()

    def save(self):
        self.store.save()

    def changed(self):
        self.save()
        self.refresh_all()

    def refresh_all(self):
        self.calendar.redraw()
        if self.mini:
            self.mini.redraw()
        for card in self.cards.values():
            card.refresh()
        for note in self.notes.values():
            note.restyle()
        for v in list(self.views):
            v.refresh()

    def _report_error(self, exc, val, tb):
        text = "".join(traceback.format_exception(exc, val, tb))
        with open(os.path.join(self.store.folder, "error.log"), "a", encoding="utf-8") as f:
            f.write(f"--- {datetime.now().isoformat(timespec='seconds')}\n{text}\n")

    def _single(self, cls, *args):
        """Re-use an open dialog of this kind instead of stacking duplicates."""
        for v in self.views:
            if type(v) is cls and (not args or getattr(v, "day", None) == args[0]):
                v.deiconify()
                v.present()
                return v
        return cls(self, *args)

    # -- hotkey / tray queue -------------------------------------------------
    def _start_hotkey(self):
        if self.hotkey:
            self.hotkey.stop()
        self.hotkey = winapi.HotkeyThread(self.settings["hotkey"], lambda: self.post("toggle_front"))
        self.hotkey.start()
        self.hotkey.registered.wait(2)
        if not self.hotkey.ok:
            self.root.after(500, lambda: messagebox.showwarning(
                "CalendarDesk", f"Ctrl+Alt+{self.settings['hotkey']} is already used by another program.\n"
                                "Pick a different letter in Settings."))

    def post(self, action):
        """Run a named action on the Tk thread. Safe to call from the hotkey and tray threads."""
        try:
            self.root.after(0, self._run_action, action)
        except RuntimeError:
            pass  # the app is shutting down

    def _run_action(self, action):
        handler = {
            "toggle_front": self.toggle_front, "toggle_mini": self.toggle_mini,
            "new_task": lambda: self.edit_task(day=self.today()), "new_note": self.new_note,
            "new_countdown": self.edit_countdown, "show_all": self.show_all,
            "countdowns": self.manage_countdowns, "search": self.search,
            "export": self.export, "settings": self.settings_dialog, "quit": self.quit,
            "undo_settings": self.undo_settings,
        }.get(action)
        if handler:
            handler()

    def main_menu(self, parent):
        m = tk.Menu(parent, tearoff=0)
        m.add_command(label="New note", command=self.new_note)
        m.add_command(label="New countdown…", command=self.edit_countdown)
        m.add_command(label="Countdowns…", command=self.manage_countdowns)
        m.add_command(label="Show all notes and cards", command=self.show_all)
        m.add_command(label="Mini calendar", command=self.toggle_mini)
        m.add_separator()
        m.add_command(label="Export to Excel…", command=self.export)
        m.add_command(label="Settings…", command=self.settings_dialog)
        m.add_command(label="Undo last settings change", command=self.undo_settings,
                      state="normal" if self.settings_undo else "disabled")
        m.add_separator()
        m.add_command(label="Exit CalendarDesk", command=self.quit)
        m.tk_popup(parent.winfo_pointerx(), parent.winfo_pointery())

    # -- desktop windows -----------------------------------------------------
    def _pinned(self):
        """All windows that live on the wallpaper (raised together by the hotkey)."""
        mini = [self.mini] if self.mini else []
        return [*self.cards.values(), *self.notes.values(), *mini, self.calendar]

    def toggle_front(self):
        if self.calendar.front and winapi.foreground_is_ours():
            self.all_to_back()
        else:
            for w in self._pinned():
                w.to_front(focus=w is self.calendar)

    def all_to_back(self):
        for w in self._pinned():
            w.to_back()

    def watch_raised(self):
        """Start checking (every 400 ms) whether raised desktop windows should drop back."""
        if not self._settling:
            self._settling = True
            self.root.after(400, self._settle)

    def _settle(self):
        """Once another app is in front, put raised desktop windows back onto the wallpaper.
        Runs only while something is raised, so an idle calendar costs nothing."""
        if not any(w.front for w in self._pinned()):
            self._settling = False
            return
        if not winapi.foreground_is_ours():
            self.all_to_back()
            self._settling = False
            return
        self.root.after(400, self._settle)

    def preview_opacity(self, value):
        self.calendar.set_opacity(value)
        for card in self.cards.values():
            card.win.attributes("-alpha", value)

    def _open_desktop_items(self):
        for n in self.store.data["notes"]:
            if n.get("visible", True):
                self.notes[n["id"]] = NoteWindow(self, n)
        self.sync_cards()

    def _close_desktop_items(self):
        for w in [*self.notes.values(), *self.cards.values()]:
            w.destroy()
        self.notes, self.cards = {}, {}

    def toggle_mini(self):
        if self.mini:
            self.mini.destroy()
            self.mini = None
        else:
            self.mini = MiniCalendar(self)
            self.mini.to_front()  # just asked for it, so show it; it drops back when you click elsewhere

    def show_all(self):
        for n in self.store.data["notes"]:
            self.show_note(n)
        for cd in self.store.data["countdowns"]:
            cd["visible"] = True
        self.sync_cards()
        self.save()

    # -- tasks -----------------------------------------------------------------
    def add_task(self, t):
        self.store.data["tasks"].append(t)
        self.changed()

    def edit_task(self, task=None, day=None):
        TaskDialog(self, task, day)

    def open_day(self, day):
        return self._single(DayPanel, day)

    def toggle_done(self, t, day, value=None):
        model.set_task_done(t, day, (not model.is_done(t, day)) if value is None else value)
        self.changed()

    def move_task(self, t, day):
        t["date"] = model.d2s(day)
        self.changed()

    def delete_task(self, t, day, whole=True):
        if whole:
            self.store.data["tasks"].remove(t)
        else:
            t.setdefault("skip_dates", []).append(model.d2s(day))
            model.set_done(t, day, False)
        self.changed()

    def set_date_color(self, day, color, parent=None):
        colors = self.store.data["date_colors"]
        if color == "custom":
            color = colorchooser.askcolor(color=colors.get(day.isoformat()), parent=parent or self.root,
                                          title="Date colour")[1]
            if not color:
                return
        if color:
            colors[day.isoformat()] = color
        else:
            colors.pop(day.isoformat(), None)
        self.changed()

    # -- reminders ------------------------------------------------------------
    def _tick(self):
        now = datetime.now()
        if now.date() != self._day:
            self._day = now.date()
            if self.settings["rollover"]:
                model.rollover(self.store.data["tasks"], self._day)
            self.store.backup()
            self.store.prune_reminders()
            self.calendar.go_today()
            self.changed()
        elif self.settings["today_progress"] and now.minute != getattr(self, "_last_minute", None):
            self.calendar.redraw()  # advance today's progress bar
        self._last_minute = now.minute
        self._check_reminders(now)
        self.root.after(TICK_MS, self._tick)

    def _check_reminders(self, now):
        state = self.store.data["reminders"]
        fired = False
        for day in (now.date(), now.date() + timedelta(1)):
            for t in model.tasks_on(self.store.data["tasks"], day):
                due = model.reminder_time(t, day)
                if due is None or model.is_done(t, day):
                    continue
                key = f"{t['id']}|{day.isoformat()}"
                s = state.get(key)
                if s == "fired":
                    continue
                if s and s.startswith("snooze:"):
                    due = datetime.fromisoformat(s[7:])
                # Fire when due; reminders missed while the PC was off still show if under 12 h late.
                if due <= now < due + timedelta(hours=12):
                    state[key] = "fired"
                    fired = True
                    ReminderPopup(self, t, day)
        if fired:
            self.save()

    def snooze(self, t, day, minutes):
        due = datetime.now() + timedelta(minutes=minutes)
        self.store.data["reminders"][f"{t['id']}|{day.isoformat()}"] = "snooze:" + due.isoformat(timespec="seconds")
        self.save()

    # -- notes -----------------------------------------------------------------
    def new_note(self):
        l, t, r, b = winapi.work_area()
        k = len(self.notes) * 28
        n = {"id": model.new_id(), "text": "", "color": theme.NOTE_COLORS[len(self.store.data["notes"]) % 6],
             "geometry": f"230x210+{(r - l) // 2 - 115 + k}+{(b - t) // 3 + k}", "visible": True}
        self.store.data["notes"].append(n)
        self.save()
        w = NoteWindow(self, n)
        self.notes[n["id"]] = w
        w.to_front()
        w.text.focus_set()

    def show_note(self, n):
        n["visible"] = True
        if n["id"] not in self.notes:
            self.notes[n["id"]] = NoteWindow(self, n)
        self.notes[n["id"]].to_front()
        self.save()

    def hide_note(self, n):
        w = self.notes.pop(n["id"], None)
        if w:
            w.flush()
            w.destroy()
        n["visible"] = False
        self.save()

    def delete_note(self, n):
        w = self.notes.get(n["id"])
        if not messagebox.askyesno("Delete note", "Delete this note for good?", parent=w.win if w else self.root):
            return
        if w:
            w.destroy()
            self.notes.pop(n["id"])
        self.store.data["notes"].remove(n)
        self.changed()

    # -- countdowns -----------------------------------------------------------
    def edit_countdown(self, cd=None, day=None):
        CountdownDialog(self, cd, day)

    def manage_countdowns(self):
        self._single(CountdownManager)

    def save_countdown(self, cd, values):
        if cd is None:
            k = len(self.store.data["countdowns"])
            cd = {"id": model.new_id(), "created": model.d2s(self.today()),
                  "geometry": f"210x130+{60 + (k % 5) * 230}+{60 + (k // 5) * 150}"}
            self.store.data["countdowns"].append(cd)
        cd.update(values)
        self.sync_cards()
        self.changed()

    def hide_countdown(self, cd):
        self.save_countdown(cd, {"visible": False})

    def delete_countdown(self, cd, parent=None):
        if not messagebox.askyesno("Delete countdown", f"Delete '{cd['title']}'?", parent=parent or self.root):
            return False
        self.store.data["countdowns"].remove(cd)
        for v in list(self.views):
            if isinstance(v, CountdownDialog) and v.cd is cd:
                v.close()
        self.sync_cards()
        self.changed()
        return True

    def sync_cards(self):
        wanted = {cd["id"]: cd for cd in self.store.data["countdowns"] if cd.get("visible", True)}
        for cid in list(self.cards):
            if cid not in wanted:
                self.cards.pop(cid).destroy()
        for cid, cd in wanted.items():
            if cid not in self.cards:
                self.cards[cid] = CountdownCard(self, cd)

    # -- search / export / settings --------------------------------------------
    def search(self):
        self._single(SearchDialog)

    def export(self):
        from .export import export_xlsx
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Export to Excel", defaultextension=".xlsx",
            initialdir=os.path.join(os.path.expanduser("~"), "Documents"),
            initialfile=f"CalendarDesk-{self.today():%Y-%m-%d}.xlsx", filetypes=[("Excel workbook", "*.xlsx")])
        if not path:
            return
        try:
            export_xlsx(self.store.data, path, self.today())
        except OSError as err:
            messagebox.showerror("Export", f"Could not save the file:\n{err}\n\nIs it open in Excel?")
            return
        if messagebox.askyesno("Export", "Exported. Open the file now?"):
            os.startfile(path)

    def settings_dialog(self):
        self._single(SettingsDialog)

    def startup_enabled(self):
        return winapi.get_startup()

    # -- settings: live preview, save, cancel, undo ------------------------------
    CARD_BASE, NOTE_BASE = (210, 130), (230, 210)

    def settings_snapshot(self):
        """Everything Settings can change, so it can be put back exactly."""
        self.root.update_idletasks()
        return {"settings": copy.deepcopy(self.settings), "calendar": self.calendar.geometry(),
                "cards": {cid: w.geometry() for cid, w in self.cards.items()},
                "notes": {nid: w.geometry() for nid, w in self.notes.items()}}

    def preview_settings(self, values):
        """Show settings on screen without saving. Startup and hotkey only change on Save."""
        s = self.settings
        old_scale = s["card_scale"]
        for k, v in values.items():
            if k not in ("start_with_windows", "hotkey", "calendar_size"):
                s[k] = copy.deepcopy(v)
        theme.apply(s)
        if values.get("calendar_size"):
            self.calendar.set_size(*values["calendar_size"])
        if s["card_scale"] != old_scale:
            dpi = self.calendar.scale
            for w in self.cards.values():
                w.set_size(self.CARD_BASE[0] * dpi * s["card_scale"], self.CARD_BASE[1] * dpi * s["card_scale"])
            for w in self.notes.values():
                w.set_size(self.NOTE_BASE[0] * dpi * s["card_scale"], self.NOTE_BASE[1] * dpi * s["card_scale"])
        self.preview_opacity(s["opacity"])
        self.root.update_idletasks()
        self.refresh_all()

    def restore_snapshot(self, snap):
        self.preview_settings(snap["settings"])
        self.calendar.win.geometry(snap["calendar"])
        for cid, g in snap["cards"].items():
            if cid in self.cards:
                self.cards[cid].win.geometry(g)
        for nid, g in snap["notes"].items():
            if nid in self.notes:
                self.notes[nid].win.geometry(g)
        self.root.update_idletasks()
        self.refresh_all()

    def _store_geometries(self):
        self.root.update_idletasks()
        self.settings["calendar_geometry"] = self.calendar.geometry()
        for cd in self.store.data["countdowns"]:
            if cd["id"] in self.cards:
                cd["geometry"] = self.cards[cd["id"]].geometry()
        for n in self.store.data["notes"]:
            if n["id"] in self.notes:
                n["geometry"] = self.notes[n["id"]].geometry()

    def apply_settings(self, values, undo=None):
        values = dict(values)
        startup = values.pop("start_with_windows")
        if startup != winapi.get_startup():
            try:
                winapi.set_startup(startup)
            except OSError as err:
                messagebox.showerror("Settings", f"Could not change the startup setting:\n{err}")
        hotkey_changed = values["hotkey"] != self.settings["hotkey"]
        self.preview_settings(values)
        self.settings["start_with_windows"] = winapi.get_startup()
        self.settings["hotkey"] = values["hotkey"]
        if hotkey_changed:
            self._start_hotkey()
        self._store_geometries()
        if undo:
            self.settings_undo = undo
        self.changed()

    def undo_settings(self):
        snap, self.settings_undo = self.settings_undo, None
        if not snap:
            return
        self.restore_snapshot(snap)
        self.apply_settings(snap["settings"])

    def restore_backup(self, name):
        for w in self.notes.values():
            w.flush()
        self.store.restore(name)
        theme.apply(self.settings)
        self._close_desktop_items()
        self._open_desktop_items()
        self.preview_opacity(self.settings["opacity"])
        self.changed()

    def quit(self):
        for w in self.notes.values():
            w.flush()
        for v in list(self.views):  # day panels hold typing that is saved on Enter or focus-out
            if hasattr(v, "commit_all"):
                v.commit_all()
        self.save()
        if self.hotkey:
            self.hotkey.stop()
        if self.tray:
            self.tray.stop()
        self.calendar.stop_hooks()
        self.root.destroy()
