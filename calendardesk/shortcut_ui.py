"""Settings → Shortcuts: the list of commands and the key recorder."""
import tkinter as tk
from tkinter import ttk

from . import shortcuts, theme

ERROR_FG, WARN_FG, OK_FG = "#c92a2a", "#b35c00", "#2b8a3e"
_MOD_KEYSYMS = {"Win_L", "Win_R", "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R"}


def show_problems(label, problems, ok_text=""):
    """Put the first error (or all warnings) into a label, coloured by how bad it is."""
    errors = [m for lvl, m in problems if lvl == "error"]
    warnings = [m for lvl, m in problems if lvl == "warning"]
    if errors:
        label.configure(text="✖ " + errors[0], foreground=ERROR_FG)
    elif warnings:
        label.configure(text="⚠ " + "\n⚠ ".join(warnings), foreground=WARN_FG)
    else:
        label.configure(text=ok_text, foreground=OK_FG)


class ShortcutsTab(ttk.Frame):
    """Every command with its shortcut. Edits stay here until Settings is saved."""

    def __init__(self, parent, dialog):
        super().__init__(parent, padding=10)
        self.dialog = dialog
        self.app = dialog.app
        s = self.app.settings
        self.current = shortcuts.effective(s)
        self.defaults = shortcuts.defaults(s.get("hotkey"))
        self.global_on = tk.BooleanVar(value=s.get("global_shortcuts", True))
        self._lnk = None

        ttk.Label(self, text="Select a command, then Change… and press the keys. A second key pressed "
                             "within 1.5 s makes a two-key shortcut, e.g. Ctrl+Shift+O, D.",
                  wraplength=520, justify="left").pack(anchor="w")
        box = ttk.Frame(self)
        box.pack(fill="both", expand=True, pady=6)
        self.tree = ttk.Treeview(box, columns=("keys", "where"), height=11, selectmode="browse")
        self.tree.heading("#0", text="Command")
        self.tree.heading("keys", text="Shortcut")
        self.tree.heading("where", text="Works")
        self.tree.column("#0", width=250)
        self.tree.column("keys", width=150)
        self.tree.column("where", width=110)
        sb = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        for action, label, _, _ in shortcuts.ACTIONS:
            self.tree.insert("", "end", iid=action, text=label)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._selected())
        self.tree.bind("<Double-1>", lambda e: self.change())

        row = ttk.Frame(self)
        row.pack(fill="x")
        ttk.Button(row, text="Change…", command=self.change).pack(side="left")
        ttk.Button(row, text="Clear", command=self.clear).pack(side="left", padx=4)
        ttk.Button(row, text="Reset", command=self.reset).pack(side="left")
        self.v_global = tk.BooleanVar()
        self.global_box = ttk.Checkbutton(row, text="Works everywhere (global)", variable=self.v_global,
                                          command=self._toggle_global)
        self.global_box.pack(side="left", padx=10)
        ttk.Button(row, text="Reset all", command=self.reset_all).pack(side="right")
        self.status = ttk.Label(self, wraplength=520, justify="left")
        self.status.pack(anchor="w", fill="x", pady=(6, 0))
        ttk.Checkbutton(self, text="Global shortcuts on (untick to free every global key, e.g. while gaming)",
                        variable=self.global_on).pack(anchor="w", pady=(6, 0))
        self._fill()
        self.tree.selection_set("toggle_front")

    # -- data ------------------------------------------------------------
    def lnk(self):
        if self._lnk is None:
            self._lnk = shortcuts.lnk_hotkeys(shortcuts.lnk_folders())
        return self._lnk

    def problems(self, action, keys=None, glob=None):
        b = self.current[action]
        keys = b["keys"] if keys is None else keys
        glob = b["global"] if glob is None else glob
        taken = self.app.shortcut_taken if glob and self.global_on.get() else None
        return shortcuts.conflicts(action, keys, glob, self.current, taken=taken, lnk=self.lnk())

    def changed_values(self):
        """Only what differs from the defaults is stored."""
        return {a: dict(b) for a, b in self.current.items() if b != self.defaults[a]}

    def first_error(self):
        """(action, message) for the first shortcut that can't be saved, or None. The ones the
        user changed come first, so a clash is reported on the command they just edited."""
        changed = self.changed_values()
        for action in sorted(self.current, key=lambda a: a not in changed):
            for lvl, msg in self.problems(action):
                if lvl == "error":
                    return action, msg
        return None

    # -- view ------------------------------------------------------------
    def _fill(self):
        for action, b in self.current.items():
            where = ("everywhere" if b["global"] else "on calendar") if b["keys"] else ""
            self.tree.item(action, values=(b["keys"] or "—", where))

    def _action(self):
        sel = self.tree.selection()
        return sel[0] if sel else None

    def _selected(self):
        action = self._action()
        if not action:
            return
        self.v_global.set(self.current[action]["global"])
        show_problems(self.status, self.problems(action), "No conflicts." if self.current[action]["keys"] else "")

    def select(self, action):
        self.tree.selection_set(action)
        self.tree.see(action)

    def _set(self, action, keys, glob):
        self.current[action] = {"keys": keys, "global": glob}
        self._fill()
        self._selected()

    # -- buttons -----------------------------------------------------------
    def change(self):
        action = self._action()
        if action:
            KeyRecorder(self, action)

    def clear(self):
        action = self._action()
        if action:
            self._set(action, "", self.current[action]["global"])

    def reset(self):
        action = self._action()
        if action:
            self._set(action, self.defaults[action]["keys"], self.defaults[action]["global"])

    def reset_all(self):
        self.current = {a: dict(b) for a, b in self.defaults.items()}
        self._fill()
        self._selected()

    def _toggle_global(self):
        action = self._action()
        if action:
            self._set(action, self.current[action]["keys"], self.v_global.get())


class KeyRecorder(tk.Toplevel):
    """Press the keys for one command. Global shortcuts are paused meanwhile, so pressing an
    existing one records it instead of running it."""

    def __init__(self, tab, action):
        super().__init__(tab)
        self.tab, self.action, self.app = tab, action, tab.app
        self.title("Record shortcut")
        self.resizable(False, False)
        self.configure(padx=14, pady=12)
        self.transient(tab.winfo_toplevel())
        self.steps, self._win, self._job = [], False, None
        self.glob = tk.BooleanVar(value=tab.current[action]["global"])
        ttk.Label(self, text=shortcuts.LABELS[action], font=(theme.FAMILY, 10, "bold")).pack(anchor="w")
        ttk.Label(self, text="Press the keys now. For a two-key shortcut press the second key within 1.5 s.",
                  wraplength=380, justify="left").pack(anchor="w", pady=(2, 8))
        self.shown = tk.Label(self, text="…", font=(theme.FAMILY, 16, "bold"), width=22, relief="groove", pady=8)
        self.shown.pack(fill="x")
        ttk.Checkbutton(self, text="Works everywhere (global), not just on the calendar", variable=self.glob,
                        command=self._check, takefocus=False).pack(anchor="w", pady=(8, 0))
        self.status = ttk.Label(self, wraplength=380, justify="left")
        self.status.pack(anchor="w", fill="x", pady=(6, 0))
        row = ttk.Frame(self)
        row.pack(fill="x", pady=(10, 0))
        self.use_btn = ttk.Button(row, text="Use", command=self.use, state="disabled", takefocus=False)
        self.use_btn.pack(side="right")
        ttk.Button(row, text="Cancel", command=self.close, takefocus=False).pack(side="right", padx=6)
        ttk.Button(row, text="Try again", command=self.again, takefocus=False).pack(side="left")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<KeyPress>", self._press)
        self.bind("<KeyRelease>", self._release)
        self.app.pause_global_shortcuts()
        self.update_idletasks()
        self.geometry(f"+{tab.winfo_rootx() + 40}+{tab.winfo_rooty() + 40}")
        self.grab_set()
        self.focus_force()

    def _press(self, e):
        if e.keysym in ("Win_L", "Win_R"):
            self._win = True
        if e.keysym in _MOD_KEYSYMS:
            return "break"
        step = shortcuts.step_from_tk(e.state, e.keycode, win=self._win)
        if step is None:
            return "break"
        if self._job and len(self.steps) == 1:  # second key in time
            if step == self.steps[0]:
                return "break"  # a held-down first key repeats; that isn't a second step
            self.after_cancel(self._job)
            self._job = None
            self.steps.append(step)
        elif not self._job:
            self.steps = [step]
            self._job = self.after(shortcuts.CHORD_MS, self._timeout)
        self._check()
        return "break"

    def _release(self, e):
        if e.keysym in ("Win_L", "Win_R"):
            self._win = False
        return "break"

    def _timeout(self):
        self._job = None
        self._check()

    def keys(self):
        return shortcuts.fmt(tuple(self.steps))

    def _check(self):
        keys = self.keys()
        self.shown.configure(text=keys or "…")
        if not keys:
            self.use_btn.configure(state="disabled")
            return
        problems = self.tab.problems(self.action, keys, self.glob.get())
        waiting = " Waiting for a second key…" if self._job else ""
        show_problems(self.status, problems, "Free to use." + waiting)
        bad = any(lvl == "error" for lvl, _ in problems)
        self.use_btn.configure(state="disabled" if bad or self._job else "normal")

    def again(self):
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        self.steps = []
        self.status.configure(text="")
        self._check()
        self.focus_force()

    def use(self):
        if self.steps and not self._job:
            self.tab._set(self.action, self.keys(), self.glob.get())
            self.close()

    def close(self):
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        self.grab_release()
        self.destroy()
        self.app.apply_shortcuts(warn=False)  # back to the saved shortcuts; edits apply on Save
