"""Application controller: owns the data, the windows, the hotkey, the tray and the reminder clock."""
import copy
import os
import traceback
import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import colorchooser, filedialog, messagebox

from . import model, shortcuts, theme, winapi
from .desktop_cal import DesktopCalendar
from .day_panel import DayPanel
from .dialogs import CountdownDialog, CountdownManager, SearchDialog, SettingsDialog, TaskDialog
from .store import Store
from .widgets import CountdownCard, MiniCalendar, NoteWindow, ReminderPopup

TICK_MARGIN_MS = 200  # wake just after the minute turns, never just before it


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
        self._prune_backgrounds()

        theme.apply(self.settings)
        self.calendar = DesktopCalendar(self)
        self._open_desktop_items()
        self.key_map, self._key_wait, self._key_job = {}, None, None
        self.hotkey = winapi.HotkeyThread([], self.post, chord_ms=shortcuts.CHORD_MS)
        self.hotkey.start()
        self.hotkey.registered.wait(2)
        self.apply_shortcuts()
        self.bind_shortcut_keys(self.calendar)
        self.tray = None
        if tray:
            from .tray import Tray
            self.tray = Tray(self.post)
            self.tray.start()
        self._settling = False
        self._tick_job = self.root.after(2000, self._tick)

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

    def _prune_backgrounds(self):
        """Delete background files left over from earlier choices (and from Settings closed with Cancel)."""
        folder = os.path.join(self.store.folder, "backgrounds")
        if os.path.isdir(folder):
            from .media import prune
            bg = self.settings.get("background") or {}
            prune(folder, {bg.get("file"), bg.get("poster")})

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
    # -- keyboard shortcuts ----------------------------------------------------
    def apply_shortcuts(self, warn=True):
        """Register the global shortcuts and rebuild the calendar's key map from the settings."""
        eff = shortcuts.effective(self.settings)
        bindings, self.key_map = [], {}
        for action, b in eff.items():
            steps = shortcuts.parse(b["keys"])
            if not steps:
                continue
            if b["global"]:
                if self.settings.get("global_shortcuts", True):
                    bindings.append((action, tuple(shortcuts.win32(st) for st in steps)))
            else:
                self.key_map.setdefault(steps[0], []).append((steps[1] if len(steps) > 1 else None, action))
        failed = self.hotkey.set_bindings(bindings)
        if failed and warn:
            names = "\n".join(f"  {shortcuts.LABELS[a]}: {eff[a]['keys']}" for a in failed)
            self.root.after(500, lambda: messagebox.showwarning(
                "CalendarDesk", f"These shortcuts are already used by another program:\n{names}\n\n"
                                "Change them in Settings → Shortcuts."))
        return failed

    def pause_global_shortcuts(self):
        """While a shortcut is being recorded, so pressing it doesn't run it."""
        self.hotkey.set_bindings([])

    def shortcut_taken(self, step):
        """True if another program has registered this step (our own registrations don't count)."""
        mods, vk = shortcuts.win32(step)
        return (mods, vk) not in self.hotkey.active and winapi.probe_hotkey(mods, vk)

    def bind_shortcut_keys(self, view):
        view.win.bind("<KeyPress>", lambda e: self._key(e, view), add="+")

    def _key(self, e, view):
        """Calendar shortcuts: one Tk binding per window; nothing runs while typing in a box."""
        try:
            if e.widget.winfo_class() in ("Entry", "Text", "Spinbox", "TEntry", "TCombobox", "TSpinbox"):
                return None
        except (AttributeError, tk.TclError):
            return None
        step = shortcuts.step_from_tk(e.state, e.keycode)
        if step is None:
            return None  # a modifier on its own: a waiting chord keeps waiting
        wait = self._key_wait
        self._end_key_wait()
        if wait:
            first_mods, seconds = wait
            for second, action in seconds:
                if step == second or (not second[0] and step == (first_mods, second[1])):
                    self._shortcut(action, view)
                    return "break"
        entries = self.key_map.get(step)
        if not entries:
            return None
        single = [a for second, a in entries if second is None]
        if single:
            self._shortcut(single[0], view)
        else:
            self._key_wait = (step[0], entries)
            self._key_job = self.root.after(shortcuts.CHORD_MS, self._end_key_wait)
        return "break"

    def _end_key_wait(self):
        if self._key_job:
            self.root.after_cancel(self._key_job)
        self._key_wait = self._key_job = None

    def _shortcut(self, action, view):
        nav = {"next_month": lambda: view.go(1), "prev_month": lambda: view.go(-1), "go_today": view.go_today}
        (nav.get(action) or (lambda: self._run_action(action)))()

    def shortcuts_dialog(self):
        self._single(SettingsDialog).show_tab("shortcuts")

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
            "undo_settings": self.undo_settings, "open_today": lambda: self.open_day(self.today()),
            "menu": self.calendar.open_menu, "quick_add": self.calendar.quick_add_today,
            "next_month": lambda: self.calendar.go(1), "prev_month": lambda: self.calendar.go(-1),
            "go_today": self.calendar.go_today, "send_back": self.all_to_back,
            "shortcuts": self.shortcuts_dialog,
        }.get(action)
        if handler:
            handler()

    def main_menu(self, parent, at=None):
        eff = shortcuts.effective(self.settings)
        m = tk.Menu(parent, tearoff=0)

        def item(label, command, action, **kw):
            m.add_command(label=label, command=command, accelerator=eff[action]["keys"], **kw)

        item("New task…", lambda: self.edit_task(day=self.today()), "new_task")
        item("New note", self.new_note, "new_note")
        item("New countdown…", self.edit_countdown, "new_countdown")
        item("Countdowns…", self.manage_countdowns, "countdowns")
        item("Show all notes and cards", self.show_all, "show_all")
        item("Mini calendar", self.toggle_mini, "toggle_mini")
        item("Search…", self.search, "search")
        m.add_separator()
        item("Export to Excel…", self.export, "export")
        item("Settings…", self.settings_dialog, "settings")
        item("Keyboard shortcuts…", self.shortcuts_dialog, "shortcuts")
        item("Undo last settings change", self.undo_settings, "undo_settings",
             state="normal" if self.settings_undo else "disabled")
        m.add_separator()
        item("Exit CalendarDesk", self.quit, "quit")
        x, y = at or (parent.winfo_pointerx(), parent.winfo_pointery())
        m.tk_popup(x, y)

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
            self.bind_shortcut_keys(self.mini)
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
            self.calendar.update_progress()  # moves only the bar; real changes redraw everything
        self._last_minute = now.minute
        self._check_reminders(now)
        if self._tick_job:
            self.root.after_cancel(self._tick_job)
        self._tick_job = self.root.after(self._next_tick_ms(now), self._tick)

    def _next_tick_ms(self, now):
        """Sleep until the next whole minute (reminder times, the day and the progress bar all change on
        whole minutes), or until a snoozed reminder falls due if that is sooner."""
        wake = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        for s in self.store.data["reminders"].values():
            if s.startswith("snooze:"):
                due = datetime.fromisoformat(s[7:])
                if now < due < wake:
                    wake = due
        return int((wake - now).total_seconds() * 1000) + TICK_MARGIN_MS

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
        """Show settings on screen without saving. Startup and shortcuts only change on Save."""
        s = self.settings
        old_scale = s["card_scale"]
        for k, v in values.items():
            if k not in ("start_with_windows", "hotkey", "shortcuts", "global_shortcuts", "calendar_size"):
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
        new_keys = {k: copy.deepcopy(values[k]) for k in ("hotkey", "shortcuts", "global_shortcuts") if k in values}
        keys_changed = any(self.settings.get(k) != v for k, v in new_keys.items())
        self.preview_settings(values)
        self.settings["start_with_windows"] = winapi.get_startup()
        self.settings.update(new_keys)
        if keys_changed:
            self.apply_shortcuts()
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
        self.calendar.stop_hooks()  # first, so nothing below can leave the system hook behind
        self.calendar.close_background()  # stops Windows' video player before its window goes
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
        for job in self.root.tk.splitlist(self.root.tk.call("after", "info")):
            # Timers (tick, glow, settle…) would only fail once the windows are gone. Their commands
            # belong to their widgets, which delete them on destroy, so only the jobs are cancelled here.
            self.root.tk.call("after", "cancel", job)
        self.root.destroy()
