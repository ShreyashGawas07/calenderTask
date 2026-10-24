"""Normal windowed dialogs: day view, task editor, countdowns, search and settings."""
import os
import re
import tkinter as tk
from datetime import date, datetime, timedelta
import tkinter.font as tkfont
from tkinter import colorchooser, messagebox, ttk

from . import model, theme, winapi
from .holidays_in import holiday_name

REMIND_CHOICES = [("At the time", 0), ("5 min before", 5), ("10 min before", 10), ("15 min before", 15),
                  ("30 min before", 30), ("1 hour before", 60), ("2 hours before", 120), ("1 day before", 1440)]
WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
REPEAT_UNITS = {"daily": "day(s)", "weekly": "week(s)", "monthly": "month(s)", "yearly": "year(s)"}


def fmt_date(d):
    return d.strftime("%d-%m-%Y") if d else ""


def parse_date(text):
    """Accepts DD-MM-YYYY, DD/MM/YYYY, DD.MM.YYYY or YYYY-MM-DD. Returns date or None."""
    text = text.strip()
    if not text:
        return None
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", text)
        if not m:
            raise ValueError(f"'{text}' is not a date. Use DD-MM-YYYY.")
        d, mo, y = map(int, m.groups())
    return date(y, mo, d)


def parse_time(text):
    """Accepts 9:30, 09:30, 930, 9 or 9.30 → 'HH:MM'; empty → None."""
    text = text.strip().replace(".", ":")
    if not text:
        return None
    m = re.fullmatch(r"(\d{1,2})(?::?(\d{2}))?", text)
    if not m:
        raise ValueError(f"'{text}' is not a time. Use HH:MM (24-hour).")
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if h > 23 or mi > 59:
        raise ValueError(f"'{text}' is not a valid time.")
    return f"{h:02d}:{mi:02d}"


def repeat_label(t):
    rep = t.get("repeat", "none")
    if rep == "none":
        return ""
    n = int(t.get("interval") or 1)
    label = {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly", "yearly": "Yearly"}[rep] if n == 1 \
        else f"Every {n} {REPEAT_UNITS[rep]}"
    if rep == "weekly" and t.get("weekdays"):
        label += " (" + ",".join(WEEKDAY_NAMES[i] for i in sorted(t["weekdays"])) + ")"
    return label


class Dialog(tk.Toplevel):
    def __init__(self, app, title, resizable=False):
        super().__init__(app.root)
        self.app = app
        self.title(title)
        self.resizable(resizable, resizable)
        self.configure(padx=14, pady=12)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda e: self.close())
        app.views.append(self)

    def present(self):
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 3
        self.geometry(f"+{x}+{y}")
        self.lift()
        self.attributes("-topmost", True)
        self.after(300, lambda: self.winfo_exists() and self.attributes("-topmost", False))
        self.focus_force()

    def refresh(self):
        pass

    def close(self):
        if self in self.app.views:
            self.app.views.remove(self)
        self.destroy()


def swatches(parent, colors, var, include_none=True):
    row = tk.Frame(parent)
    buttons = {}

    def pick(c):
        var.set(c)
        for k, b in buttons.items():
            b.configure(relief="sunken" if k == c else "flat", bd=3 if k == c else 1)

    if include_none:
        b = tk.Button(row, text="✕", width=2, relief="flat", command=lambda: pick(""))
        b.pack(side="left", padx=2)
        buttons[""] = b
    for c in colors:
        b = tk.Button(row, bg=c, activebackground=c, width=2, relief="flat", command=lambda c=c: pick(c))
        b.pack(side="left", padx=2)
        buttons[c] = b
    pick(var.get() if var.get() in buttons else (colors[0] if not include_none else ""))
    return row


class TaskDialog(Dialog):
    def __init__(self, app, task=None, day=None):
        super().__init__(app, "Edit task" if task else "New task")
        self.task = task
        t = task or model.new_task("", day or app.today())
        self.v_title = tk.StringVar(value=t["title"])
        self.v_date = tk.StringVar(value=fmt_date(model.s2d(t["date"])))
        self.v_time = tk.StringVar(value=t.get("time") or "")
        self.v_remind = tk.BooleanVar(value=t.get("remind", False))
        before = int(t.get("remind_before") or 0)
        self.v_before = tk.StringVar(value=next((l for l, m in REMIND_CHOICES if m == before), REMIND_CHOICES[0][0]))
        self.v_repeat = tk.StringVar(value=t.get("repeat", "none"))
        self.v_interval = tk.IntVar(value=int(t.get("interval") or 1))
        self.v_until = tk.StringVar(value=fmt_date(model.s2d(t.get("until"))))
        self.v_color = tk.StringVar(value=t.get("color") or "")
        self.v_days = [tk.BooleanVar(value=i in (t.get("weekdays") or [])) for i in range(7)]

        g = ttk.Frame(self)
        g.pack(fill="both", expand=True)
        r = 0
        ttk.Label(g, text="Task").grid(row=r, column=0, sticky="w", pady=3)
        e = ttk.Entry(g, textvariable=self.v_title, width=42)
        e.grid(row=r, column=1, columnspan=3, sticky="we", pady=3)
        e.focus_set()
        r += 1
        ttk.Label(g, text="Date").grid(row=r, column=0, sticky="w", pady=3)
        ttk.Entry(g, textvariable=self.v_date, width=12).grid(row=r, column=1, sticky="w")
        ttk.Label(g, text="Time").grid(row=r, column=2, sticky="e", padx=(10, 4))
        ttk.Entry(g, textvariable=self.v_time, width=7).grid(row=r, column=3, sticky="w")
        r += 1
        ttk.Checkbutton(g, text="Remind me", variable=self.v_remind).grid(row=r, column=0, sticky="w", pady=3)
        ttk.Combobox(g, textvariable=self.v_before, values=[l for l, _ in REMIND_CHOICES], state="readonly",
                     width=16).grid(row=r, column=1, columnspan=2, sticky="w")
        r += 1
        ttk.Label(g, text="Repeat").grid(row=r, column=0, sticky="w", pady=3)
        rep = ttk.Frame(g)
        rep.grid(row=r, column=1, columnspan=3, sticky="w")
        cb = ttk.Combobox(rep, textvariable=self.v_repeat, values=model.REPEATS, state="readonly", width=9)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self._sync_repeat())
        self.every = ttk.Frame(rep)
        ttk.Label(self.every, text="  every").pack(side="left")
        ttk.Spinbox(self.every, from_=1, to=99, textvariable=self.v_interval, width=4).pack(side="left", padx=4)
        self.unit = ttk.Label(self.every, text="")
        self.unit.pack(side="left")
        r += 1
        self.days_row = ttk.Frame(g)
        self.days_row.grid(row=r, column=1, columnspan=3, sticky="w")
        for i, n in enumerate(WEEKDAY_NAMES):
            ttk.Checkbutton(self.days_row, text=n, variable=self.v_days[i]).pack(side="left")
        r += 1
        self.until_lbl = ttk.Label(g, text="Until")
        self.until_lbl.grid(row=r, column=0, sticky="w", pady=3)
        self.until_entry = ttk.Entry(g, textvariable=self.v_until, width=12)
        self.until_entry.grid(row=r, column=1, sticky="w")
        self.until_hint = ttk.Label(g, text="(optional)", foreground="#777")
        self.until_hint.grid(row=r, column=2, columnspan=2, sticky="w", padx=6)
        r += 1
        ttk.Label(g, text="Colour").grid(row=r, column=0, sticky="w", pady=3)
        swatches(g, model.COLORS[1:], self.v_color).grid(row=r, column=1, columnspan=3, sticky="w")
        r += 1
        ttk.Label(g, text="Notes").grid(row=r, column=0, sticky="nw", pady=3)
        self.note = tk.Text(g, width=42, height=4, wrap="word", font=(theme.FAMILY, 9))
        self.note.grid(row=r, column=1, columnspan=3, sticky="we", pady=3)
        self.note.insert("1.0", t.get("note", ""))
        r += 1
        ttk.Label(g, text="Dates: DD-MM-YYYY · Time: 24-hour HH:MM", foreground="#777").grid(
            row=r, column=1, columnspan=3, sticky="w")

        b = ttk.Frame(self)
        b.pack(fill="x", pady=(10, 0))
        ttk.Button(b, text="Save", command=self.save).pack(side="right")
        ttk.Button(b, text="Cancel", command=self.close).pack(side="right", padx=6)
        if task:
            ttk.Button(b, text="Delete", command=self.delete).pack(side="left")
        self.bind("<Return>", lambda e: None if isinstance(e.widget, tk.Text) else self.save())
        self._sync_repeat()
        self.present()

    def _sync_repeat(self):
        rep = self.v_repeat.get()
        if rep == "none":
            self.every.pack_forget()
            for w in (self.until_lbl, self.until_entry, self.until_hint):
                w.grid_remove()
        else:
            self.every.pack(side="left")
            self.unit.configure(text=REPEAT_UNITS[rep])
            for w in (self.until_lbl, self.until_entry, self.until_hint):
                w.grid()
        if rep == "weekly":
            self.days_row.grid()
        else:
            self.days_row.grid_remove()

    def save(self):
        try:
            title = self.v_title.get().strip()
            if not title:
                raise ValueError("Please type a task.")
            day = parse_date(self.v_date.get())
            if not day:
                raise ValueError("Please enter a date.")
            time = parse_time(self.v_time.get())
            remind = self.v_remind.get()
            if remind and not time:
                raise ValueError("Set a time so the reminder knows when to pop up.")
            until = parse_date(self.v_until.get()) if self.v_repeat.get() != "none" else None
            if until and until < day:
                raise ValueError("'Until' must be on or after the date.")
            interval = max(1, int(self.v_interval.get()))
        except (ValueError, tk.TclError) as err:
            messagebox.showerror("Check the task", str(err), parent=self)
            return
        t = self.task or model.new_task(title, day)
        rule_changed = self.task is not None and (
            t["date"] != model.d2s(day) or t.get("repeat") != self.v_repeat.get())
        t.update({
            "title": title, "date": model.d2s(day), "time": time, "remind": remind,
            "remind_before": dict(REMIND_CHOICES)[self.v_before.get()],
            "repeat": self.v_repeat.get(), "interval": interval,
            "weekdays": [i for i, v in enumerate(self.v_days) if v.get()] if self.v_repeat.get() == "weekly" else [],
            "until": model.d2s(until) if until else None,
            "color": self.v_color.get() or None,
            "note": self.note.get("1.0", "end-1c").strip(),
        })
        if rule_changed:
            t["done_dates"], t["skip_dates"] = [], []
        if self.task is None:
            self.app.add_task(t)
        else:
            self.app.changed()
        self.close()

    def delete(self):
        if messagebox.askyesno("Delete task", f"Delete '{self.task['title']}'"
                               + (" and all its repeats?" if self.task.get("repeat") != "none" else "?"),
                               parent=self):
            self.app.delete_task(self.task, None, whole=True)
            self.close()


class DayDialog(Dialog):
    def __init__(self, app, day):
        super().__init__(app, day.strftime("%A, %d %B %Y"), resizable=True)
        self.day = day
        head = ttk.Frame(self)
        head.pack(fill="x")
        ttk.Label(head, text=day.strftime("%A, %d %B %Y"), font=(theme.FAMILY, 13, "bold")).pack(anchor="w")
        self.info = ttk.Label(head, foreground="#c05f00")
        self.info.pack(anchor="w")

        cols = ("done", "time", "title", "repeat")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=10, selectmode="browse")
        for c, text, w in (("done", "✓", 30), ("time", "Time", 60), ("title", "Task", 280), ("repeat", "Repeats", 150)):
            self.tree.heading(c, text=text)
            self.tree.column(c, width=w, anchor="center" if c in ("done", "time") else "w", stretch=c == "title")
        self.tree.pack(fill="both", expand=True, pady=8)
        self.tree.bind("<Double-1>", lambda e: self.edit())
        self.tree.bind("<space>", lambda e: self.toggle())
        self.tree.bind("<Delete>", lambda e: self.delete())

        b = ttk.Frame(self)
        b.pack(fill="x")
        for text, cmd in (("Add", self.add), ("Edit", self.edit), ("Done / undo", self.toggle),
                          ("Move to next day", self.move), ("Delete", self.delete)):
            ttk.Button(b, text=text, command=cmd).pack(side="left", padx=(0, 6))

        c = ttk.Frame(self)
        c.pack(fill="x", pady=(10, 0))
        ttk.Label(c, text="Date colour:").pack(side="left")
        for col in theme.DATE_COLORS:
            tk.Button(c, bg=col, activebackground=col, width=2, relief="flat",
                      command=lambda col=col: app.set_date_color(day, col)).pack(side="left", padx=2)
        ttk.Button(c, text="Custom…", command=lambda: app.set_date_color(day, "custom", parent=self)).pack(side="left", padx=4)
        ttk.Button(c, text="Clear", command=lambda: app.set_date_color(day, None)).pack(side="left")
        ttk.Button(c, text="Countdown to this day…", command=lambda: app.edit_countdown(day=day)).pack(side="right")
        self.refresh()
        self.present()

    def refresh(self):
        if not self.winfo_exists():
            return
        info = []
        hol = holiday_name(self.day)
        if hol:
            info.append(hol)
        sw = model.school_week(self.app.settings["school_terms"], self.day)
        if sw:
            info.append(f"{sw[0]} · week {sw[1]}")
        self.info.configure(text="   ·   ".join(info))
        sel = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        self.rows = {}
        for t in model.tasks_on(self.app.store.data["tasks"], self.day):
            iid = self.tree.insert("", "end", values=("✓" if model.is_done(t, self.day) else "",
                                                      t.get("time") or "", t["title"], repeat_label(t)))
            self.rows[iid] = t
        if sel and sel[0] in self.rows:
            self.tree.selection_set(sel)

    def _selected(self):
        sel = self.tree.selection()
        return self.rows.get(sel[0]) if sel else None

    def add(self):
        self.app.edit_task(day=self.day)

    def edit(self):
        t = self._selected()
        if t:
            self.app.edit_task(task=t, day=self.day)

    def toggle(self):
        t = self._selected()
        if t:
            self.app.toggle_done(t, self.day)

    def move(self):
        t = self._selected()
        if not t:
            return
        if t.get("repeat", "none") != "none":
            messagebox.showinfo("Repeating task", "Edit the task to change when a repeating task happens.", parent=self)
            return
        self.app.move_task(t, self.day + timedelta(1))

    def delete(self):
        t = self._selected()
        if not t:
            return
        if t.get("repeat", "none") == "none":
            if messagebox.askyesno("Delete task", f"Delete '{t['title']}'?", parent=self):
                self.app.delete_task(t, self.day, whole=True)
            return
        ans = messagebox.askyesnocancel("Delete repeating task",
                                        f"'{t['title']}' repeats.\n\nYes = delete only this day\nNo = delete all repeats",
                                        parent=self)
        if ans is not None:
            self.app.delete_task(t, self.day, whole=not ans)


class CountdownDialog(Dialog):
    def __init__(self, app, cd=None, day=None):
        super().__init__(app, "Edit countdown" if cd else "New countdown")
        self.cd = cd
        c = cd or {"title": "", "date": model.d2s(day or app.today() + timedelta(30)), "yearly": False,
                   "color": theme.CARD_COLORS[0], "visible": True}
        self.v_title = tk.StringVar(value=c["title"])
        self.v_date = tk.StringVar(value=fmt_date(model.s2d(c["date"])))
        self.v_yearly = tk.BooleanVar(value=c.get("yearly", False))
        self.v_visible = tk.BooleanVar(value=c.get("visible", True))
        self.v_color = tk.StringVar(value=c.get("color") or theme.CARD_COLORS[0])
        self.v_style = tk.StringVar(value=theme.CARD_STYLES[c.get("style", "minimal")])
        g = ttk.Frame(self)
        g.pack(fill="both")
        ttk.Label(g, text="Title").grid(row=0, column=0, sticky="w", pady=3)
        e = ttk.Entry(g, textvariable=self.v_title, width=34)
        e.grid(row=0, column=1, sticky="we")
        e.focus_set()
        ttk.Label(g, text="Date").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(g, textvariable=self.v_date, width=12).grid(row=1, column=1, sticky="w")
        ttk.Checkbutton(g, text="Every year (birthday / anniversary)", variable=self.v_yearly).grid(
            row=2, column=1, sticky="w", pady=3)
        ttk.Checkbutton(g, text="Show card on desktop", variable=self.v_visible).grid(row=3, column=1, sticky="w")
        ttk.Label(g, text="Colour").grid(row=4, column=0, sticky="w", pady=3)
        colour_row = ttk.Frame(g)
        colour_row.grid(row=4, column=1, sticky="w")
        swatches(colour_row, theme.CARD_COLORS, self.v_color, include_none=False).pack(side="left")
        ttk.Button(colour_row, text="Custom…", command=self._custom_colour).pack(side="left", padx=6)
        ttk.Label(g, text="Style").grid(row=5, column=0, sticky="w", pady=3)
        ttk.Combobox(g, textvariable=self.v_style, values=list(theme.CARD_STYLES.values()), state="readonly",
                     width=16).grid(row=5, column=1, sticky="w")
        b = ttk.Frame(self)
        b.pack(fill="x", pady=(10, 0))
        ttk.Button(b, text="Save", command=self.save).pack(side="right")
        ttk.Button(b, text="Cancel", command=self.close).pack(side="right", padx=6)
        if cd:
            ttk.Button(b, text="Delete", command=lambda: (self.app.delete_countdown(cd, parent=self))).pack(side="left")
        self.bind("<Return>", lambda e: self.save())
        self.present()

    def save(self):
        try:
            title = self.v_title.get().strip()
            if not title:
                raise ValueError("Please give the countdown a title.")
            d = parse_date(self.v_date.get())
            if not d:
                raise ValueError("Please enter a date.")
        except ValueError as err:
            messagebox.showerror("Check the countdown", str(err), parent=self)
            return
        style = next(k for k, v in theme.CARD_STYLES.items() if v == self.v_style.get())
        values = {"title": title, "date": model.d2s(d), "yearly": self.v_yearly.get(),
                  "color": self.v_color.get(), "visible": self.v_visible.get(), "style": style}
        self.app.save_countdown(self.cd, values)
        self.close()

    def _custom_colour(self):
        picked = colorchooser.askcolor(color=self.v_color.get(), parent=self, title="Card colour")[1]
        if picked:
            self.v_color.set(picked)


class CountdownManager(Dialog):
    def __init__(self, app):
        super().__init__(app, "Countdowns & anniversaries", resizable=True)
        self.tree = ttk.Treeview(self, columns=("title", "date", "left", "shown"), show="headings", height=10)
        for c, text, w in (("title", "Title", 200), ("date", "Date", 100), ("left", "Days left", 80), ("shown", "On desktop", 80)):
            self.tree.heading(c, text=text)
            self.tree.column(c, width=w, stretch=c == "title")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.edit())
        b = ttk.Frame(self)
        b.pack(fill="x", pady=(8, 0))
        ttk.Button(b, text="New…", command=lambda: app.edit_countdown()).pack(side="left")
        ttk.Button(b, text="Edit…", command=self.edit).pack(side="left", padx=6)
        ttk.Button(b, text="Show / hide", command=self.toggle).pack(side="left")
        ttk.Button(b, text="Delete", command=self.delete).pack(side="left", padx=6)
        ttk.Button(b, text="Close", command=self.close).pack(side="right")
        self.refresh()
        self.present()

    def refresh(self):
        if not self.winfo_exists():
            return
        self.tree.delete(*self.tree.get_children())
        self.rows = {}
        for cd in self.app.store.data["countdowns"]:
            days, target, _ = model.countdown_info(cd, self.app.today())
            iid = self.tree.insert("", "end", values=(cd["title"], fmt_date(target), days,
                                                      "Yes" if cd.get("visible", True) else "No"))
            self.rows[iid] = cd

    def _sel(self):
        s = self.tree.selection()
        return self.rows.get(s[0]) if s else None

    def edit(self):
        if cd := self._sel():
            self.app.edit_countdown(cd=cd)

    def toggle(self):
        if cd := self._sel():
            self.app.save_countdown(cd, {"visible": not cd.get("visible", True)})

    def delete(self):
        if cd := self._sel():
            self.app.delete_countdown(cd, parent=self)


class SearchDialog(Dialog):
    def __init__(self, app):
        super().__init__(app, "Search", resizable=True)
        self.v_q = tk.StringVar()
        e = ttk.Entry(self, textvariable=self.v_q, width=50)
        e.pack(fill="x")
        e.focus_set()
        e.bind("<KeyRelease>", lambda ev: self.refresh())
        self.tree = ttk.Treeview(self, columns=("kind", "date", "title", "status"), show="headings", height=14)
        for c, text, w in (("kind", "Type", 80), ("date", "Date", 95), ("title", "Title", 300), ("status", "Status", 120)):
            self.tree.heading(c, text=text)
            self.tree.column(c, width=w, stretch=c == "title")
        self.tree.pack(fill="both", expand=True, pady=8)
        self.tree.bind("<Double-1>", lambda ev: self.open())
        self.tree.bind("<Return>", lambda ev: self.open())
        ttk.Label(self, text="Searches task titles and notes, sticky notes and countdowns. Double-click to open.",
                  foreground="#777").pack(anchor="w")
        self.refresh()
        self.present()

    def refresh(self):
        if not self.winfo_exists():
            return
        q = self.v_q.get().strip()
        self.tree.delete(*self.tree.get_children())
        self.rows = {}
        if not q:
            return
        today = self.app.today()
        data = self.app.store.data
        found = []
        for t in data["tasks"]:
            if model.matches(t, q):
                if t.get("repeat", "none") == "none":
                    status = "Done" if t.get("done") else ("Open" if model.s2d(t["date"]) >= today else "Overdue")
                else:
                    status = repeat_label(t)
                found.append((t["date"], ("Task", fmt_date(model.s2d(t["date"])), t["title"], status), ("task", t)))
        for n in data["notes"]:
            if q.lower() in n.get("text", "").lower():
                first = n["text"].strip().splitlines()[0] if n["text"].strip() else "(note)"
                found.append(("", ("Note", "", first, "Shown" if n.get("visible", True) else "Hidden"), ("note", n)))
        for cd in data["countdowns"]:
            if q.lower() in cd["title"].lower():
                days, target, _ = model.countdown_info(cd, today)
                found.append((cd["date"], ("Countdown", fmt_date(target), cd["title"], f"{days} days"), ("cd", cd)))
        for _, values, ref in sorted(found, key=lambda x: x[0], reverse=True):
            self.rows[self.tree.insert("", "end", values=values)] = ref

    def open(self):
        s = self.tree.selection()
        if not s:
            return
        kind, obj = self.rows[s[0]]
        if kind == "task":
            d = model.s2d(obj["date"])
            if obj.get("repeat", "none") != "none":
                d = max(d, self.app.today())
                while not model.occurs_on(obj, d) and d < model.s2d(obj["date"]) + timedelta(800):
                    d += timedelta(1)
            self.app.calendar.show_month_of(d)
            self.app.open_day(d)
        elif kind == "note":
            self.app.show_note(obj)
        else:
            self.app.edit_countdown(cd=obj)


SIZE_PRESETS = [("Small", 38, 45), ("Medium", 50, 62), ("Large", 66, 80),
                ("Half screen", 50, 100), ("Full screen", 100, 100)]


class SettingsDialog(Dialog):
    """Every change previews live on the calendar and cards. Save keeps it; Cancel restores
    exactly what was there when the dialog opened."""

    def __init__(self, app):
        super().__init__(app, "Settings")
        s = app.settings
        self.snapshot = app.settings_snapshot()
        self._preview_job = None
        l, t, r, b = winapi.work_area()
        self.work = (r - l, b - t)
        cal = app.calendar.win
        self.vars = {
            "opacity": tk.DoubleVar(value=s["opacity"]),
            "font_size": tk.IntVar(value=s["font_size"]),
            "card_scale": tk.DoubleVar(value=s["card_scale"]),
            "cal_w": tk.IntVar(value=round(cal.winfo_width() * 100 / self.work[0])),
            "cal_h": tk.IntVar(value=round(cal.winfo_height() * 100 / self.work[1])),
            "week_starts_monday": tk.BooleanVar(value=s["week_starts_monday"]),
            "show_week_numbers": tk.BooleanVar(value=s["show_week_numbers"]),
            "show_holidays": tk.BooleanVar(value=s["show_holidays"]),
            "rollover": tk.BooleanVar(value=s["rollover"]),
            "locked": tk.BooleanVar(value=s["locked"]),
            "start_with_windows": tk.BooleanVar(value=app.startup_enabled()),
            "hotkey": tk.StringVar(value=s["hotkey"]),
            "theme": tk.StringVar(value=theme.THEME_NAMES.get(s["theme"], "Dark")),
            "font_family": tk.StringVar(value=s["font_family"]),
            "auto_scale": tk.BooleanVar(value=s["auto_scale"]),
            "today_glow": tk.BooleanVar(value=s["today_glow"]),
            "today_tint": tk.BooleanVar(value=s["today_tint"]),
            "today_week": tk.BooleanVar(value=s["today_week"]),
            "today_progress": tk.BooleanVar(value=s["today_progress"]),
        }
        self.accent = s["accent"]
        self.colors = dict(s["colors"])
        self.terms = [dict(t) for t in s["school_terms"]]
        self.size_touched = False
        tk.Label(self, text="Changes show on your calendar and cards right away.  "
                            "Save keeps them · Cancel puts everything back.",
                 bg="#e7f5ff", fg="#1864ab", anchor="w", padx=8, pady=5).pack(fill="x", pady=(0, 8))
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)
        nb.add(self._size(nb), text="Size")
        nb.add(self._appearance(nb), text="Appearance")
        nb.add(self._general(nb), text="General")
        nb.add(self._school(nb), text="School weeks")
        nb.add(self._data(nb), text="Data & backup")
        b = ttk.Frame(self)
        b.pack(fill="x", pady=(10, 0))
        ttk.Button(b, text="Save", command=self.save).pack(side="right")
        ttk.Button(b, text="Cancel", command=self.close).pack(side="right", padx=6)
        ttk.Button(b, text="Reset size to default", command=self._default_size).pack(side="left")
        for key, var in self.vars.items():
            if key not in ("start_with_windows", "hotkey"):
                var.trace_add("write", lambda *a, k=key: self._changed(k))
        # Lift the calendar and cards above other windows so the preview is visible.
        for w in app._pinned():
            w.to_front(focus=False)
        self.present()

    # -- live preview ------------------------------------------------------
    def _changed(self, key=None):
        if key in ("cal_w", "cal_h"):
            self.size_touched = True
        if self._preview_job:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(120, self._preview)

    def _preview(self):
        self._preview_job = None
        values = self.values()
        if values is not None:
            self.app.preview_settings(values)
            for w in self.app._pinned():
                w.to_front(focus=False)
            self.lift()

    def values(self):
        """Current dialog state as settings values, or None while a field is half-typed."""
        try:
            values = {k: var.get() for k, var in self.vars.items()}
        except (tk.TclError, ValueError):
            return None
        cal_w, cal_h = values.pop("cal_w"), values.pop("cal_h")
        if self.size_touched:
            values["calendar_size"] = (cal_w * self.work[0] / 100, cal_h * self.work[1] / 100)
        values["font_size"] = min(24, max(7, int(values["font_size"])))
        values["opacity"] = round(float(values["opacity"]), 2)
        values["card_scale"] = round(float(values["card_scale"]), 2)
        values["theme"] = self._theme_key()
        values["font_family"] = values["font_family"].strip() or "Segoe UI"
        values["accent"], values["colors"] = self.accent, dict(self.colors)
        values["school_terms"] = [dict(t) for t in self.terms]
        return values

    # -- tabs --------------------------------------------------------------
    def _size(self, nb):
        f = ttk.Frame(nb, padding=10)
        v = self.vars
        ttk.Label(f, text="Calendar size", font=(theme.FAMILY, 10, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        presets = ttk.Frame(f)
        presets.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 8))
        for name, w, h in SIZE_PRESETS:
            ttk.Button(presets, text=name, command=lambda w=w, h=h: self._set_size(w, h)).pack(side="left", padx=(0, 4))
        self.size_labels = {}
        for row, (key, label) in enumerate((("cal_w", "Width"), ("cal_h", "Height")), start=2):
            ttk.Label(f, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Scale(f, from_=25, to=100, variable=v[key], length=260,
                      command=lambda x, k=key: v[k].set(round(float(x)))).grid(row=row, column=1, sticky="w")
            self.size_labels[key] = ttk.Label(f, width=18)
            self.size_labels[key].grid(row=row, column=2, sticky="w", padx=6)
        ttk.Label(f, text="Tip: you can also drag the calendar's bottom-right corner.",
                  foreground="#777").grid(row=4, column=1, columnspan=2, sticky="w")

        ttk.Label(f, text="Text size").grid(row=5, column=0, sticky="w", pady=(14, 3))
        ttk.Scale(f, from_=7, to=24, variable=v["font_size"], length=260,
                  command=lambda x: v["font_size"].set(round(float(x)))).grid(row=5, column=1, sticky="w", pady=(14, 3))
        self.size_labels["font_size"] = ttk.Label(f, width=18)
        self.size_labels["font_size"].grid(row=5, column=2, sticky="w", padx=6, pady=(14, 3))
        ttk.Checkbutton(f, text="Text also grows and shrinks with the calendar size",
                        variable=v["auto_scale"]).grid(row=6, column=1, columnspan=2, sticky="w")

        ttk.Label(f, text="Cards & notes").grid(row=7, column=0, sticky="w", pady=(14, 3))
        ttk.Scale(f, from_=0.6, to=2.5, variable=v["card_scale"], length=260,
                  command=lambda x: v["card_scale"].set(round(float(x), 2))).grid(row=7, column=1, sticky="w", pady=(14, 3))
        self.size_labels["card_scale"] = ttk.Label(f, width=18)
        self.size_labels["card_scale"].grid(row=7, column=2, sticky="w", padx=6, pady=(14, 3))
        ttk.Label(f, text="Sets every countdown card and sticky note to this size (with its text).",
                  foreground="#777").grid(row=8, column=1, columnspan=2, sticky="w")

        ttk.Label(f, text="Opacity").grid(row=9, column=0, sticky="w", pady=(14, 3))
        ttk.Scale(f, from_=0.3, to=1.0, variable=v["opacity"], length=260).grid(row=9, column=1, sticky="w", pady=(14, 3))
        self.size_labels["opacity"] = ttk.Label(f, width=18)
        self.size_labels["opacity"].grid(row=9, column=2, sticky="w", padx=6, pady=(14, 3))
        for key in ("cal_w", "cal_h", "font_size", "card_scale", "opacity"):
            v[key].trace_add("write", lambda *a: self._size_text())
        self._size_text()
        return f

    def _size_text(self):
        v = self.vars
        try:
            w, h = v["cal_w"].get(), v["cal_h"].get()
            self.size_labels["cal_w"].configure(text=f"{w}%  ({round(w * self.work[0] / 100)} px)")
            self.size_labels["cal_h"].configure(text=f"{h}%  ({round(h * self.work[1] / 100)} px)")
            self.size_labels["font_size"].configure(text=f"{v['font_size'].get()} pt")
            self.size_labels["card_scale"].configure(text=f"{round(v['card_scale'].get() * 100)}%")
            self.size_labels["opacity"].configure(text=f"{round(v['opacity'].get() * 100)}%")
        except tk.TclError:
            pass

    def _set_size(self, w, h):
        self.vars["cal_w"].set(w)
        self.vars["cal_h"].set(h)

    def _default_size(self):
        self._set_size(round(780 * self.app.calendar.scale * 100 / self.work[0]),
                       round(560 * self.app.calendar.scale * 100 / self.work[1]))
        self.vars["font_size"].set(9)
        self.vars["card_scale"].set(1.0)

    def _general(self, nb):
        f = ttk.Frame(nb, padding=10)
        v = self.vars
        ttk.Label(f, text="Show / edit hotkey").grid(row=2, column=0, sticky="w", pady=4)
        hk = ttk.Frame(f)
        hk.grid(row=2, column=1, sticky="w")
        ttk.Label(hk, text="Ctrl + Alt +").pack(side="left")
        ttk.Combobox(hk, textvariable=v["hotkey"], values=[chr(c) for c in range(65, 91)], width=3,
                     state="readonly").pack(side="left", padx=4)
        checks = [("week_starts_monday", "Week starts on Monday"),
                  ("show_week_numbers", "Show week numbers (school week when in a term)"),
                  ("show_holidays", "Show Indian public holidays"),
                  ("rollover", "Move unfinished tasks to today"),
                  ("locked", "Lock calendar and cards in place"),
                  ("start_with_windows", "Start with Windows (off unless you tick it)")]
        for i, (key, text) in enumerate(checks, start=3):
            ttk.Checkbutton(f, text=text, variable=v[key]).grid(row=i, column=0, columnspan=2, sticky="w", pady=2)
        return f

    def _appearance(self, nb):
        f = ttk.Frame(nb, padding=10)
        v = self.vars
        ttk.Label(f, text="Theme").grid(row=0, column=0, sticky="w", pady=4)
        cb = ttk.Combobox(f, textvariable=v["theme"], values=list(theme.THEME_NAMES.values()),
                          state="readonly", width=12)
        cb.grid(row=0, column=1, sticky="w")
        cb.bind("<<ComboboxSelected>>", lambda e: self._theme_picked())

        ttk.Label(f, text="Font").grid(row=1, column=0, sticky="w", pady=4)
        common = ["Segoe UI", "Calibri", "Arial", "Verdana", "Georgia", "Bahnschrift", "Nirmala UI",
                  "Consolas", "Cascadia Code", "Comic Sans MS"]
        installed = sorted({n for n in tkfont.families(self) if not n.startswith("@")})
        fonts = [n for n in common if n in installed] + [n for n in installed if n not in common]
        ttk.Combobox(f, textvariable=v["font_family"], values=fonts, width=24).grid(row=1, column=1, sticky="w")

        ttk.Label(f, text="Colours").grid(row=2, column=0, sticky="nw", pady=4)
        grid = ttk.Frame(f)
        grid.grid(row=2, column=1, sticky="w", pady=4)
        self.colour_buttons = {}
        for i, (key, label) in enumerate([("accent", "Accent")] + list(theme.FINE_COLOURS.items())):
            ttk.Label(grid, text=label).grid(row=i // 3, column=(i % 3) * 2, sticky="e", padx=(0 if i % 3 == 0 else 12, 4))
            b = tk.Button(grid, width=3, relief="groove", command=lambda k=key: self._pick_colour(k))
            b.grid(row=i // 3, column=(i % 3) * 2 + 1, sticky="w", pady=2)
            self.colour_buttons[key] = b
        ttk.Button(f, text="Reset colours to theme", command=self._reset_colours).grid(row=3, column=1, sticky="w")
        self._show_colours()

        ttk.Label(f, text="Today").grid(row=4, column=0, sticky="nw", pady=(12, 0))
        today = ttk.Frame(f)
        today.grid(row=4, column=1, sticky="w", pady=(12, 0))
        for key, text in (("today_glow", "Glowing, pulsing border"),
                          ("today_tint", "Tinted box with a TODAY badge"),
                          ("today_week", "Light up this week's row and today's weekday"),
                          ("today_progress", "Bar showing how much of the day has passed")):
            ttk.Checkbutton(today, text=text, variable=v[key]).pack(anchor="w")
        return f

    def _theme_key(self):
        return next(k for k, n in theme.THEME_NAMES.items() if n == self.vars["theme"].get())

    def _theme_picked(self):
        # Each theme comes with a suggested opacity (Glass is the see-through one).
        self.vars["opacity"].set(theme.PRESETS[self._theme_key()]["opacity"])
        self._show_colours()
        self._changed()

    def _current_palette(self):
        return theme.palette({"theme": self._theme_key(), "accent": self.accent, "colors": self.colors})

    def _show_colours(self):
        p = self._current_palette()
        for key, b in self.colour_buttons.items():
            b.configure(bg=p[key], activebackground=p[key])

    def _pick_colour(self, key):
        picked = colorchooser.askcolor(color=self._current_palette()[key], parent=self)[1]
        if picked:
            if key == "accent":
                self.accent = picked
            else:
                self.colors[key] = picked
            self._show_colours()
            self._changed()

    def _reset_colours(self):
        self.accent, self.colors = None, {}
        self._show_colours()
        self._changed()

    def _school(self, nb):
        f = ttk.Frame(nb, padding=10)
        ttk.Label(f, text="Weeks are numbered W1, W2… from the start of each term.", foreground="#555").pack(anchor="w")
        self.term_tree = ttk.Treeview(f, columns=("name", "start", "end"), show="headings", height=6)
        for c, text, w in (("name", "Term", 160), ("start", "Starts", 100), ("end", "Ends", 100)):
            self.term_tree.heading(c, text=text)
            self.term_tree.column(c, width=w)
        self.term_tree.pack(fill="both", expand=True, pady=6)
        row = ttk.Frame(f)
        row.pack(fill="x")
        self.v_tname, self.v_tstart, self.v_tend = tk.StringVar(value="Term 1"), tk.StringVar(), tk.StringVar()
        for label, var, w in (("Name", self.v_tname, 12), ("Start", self.v_tstart, 11), ("End", self.v_tend, 11)):
            ttk.Label(row, text=label).pack(side="left")
            ttk.Entry(row, textvariable=var, width=w).pack(side="left", padx=(2, 8))
        ttk.Button(row, text="Add", command=self._add_term).pack(side="left")
        ttk.Button(f, text="Remove selected", command=self._remove_term).pack(anchor="w", pady=(6, 0))
        self._fill_terms()
        return f

    def _fill_terms(self):
        self.term_tree.delete(*self.term_tree.get_children())
        for i, t in enumerate(self.terms):
            self.term_tree.insert("", "end", iid=str(i), values=(
                t["name"], fmt_date(model.s2d(t["start"])), fmt_date(model.s2d(t["end"]))))

    def _add_term(self):
        try:
            start, end = parse_date(self.v_tstart.get()), parse_date(self.v_tend.get())
            if not (start and end) or end < start:
                raise ValueError("Enter a start date and an end date after it (DD-MM-YYYY).")
        except ValueError as err:
            messagebox.showerror("School term", str(err), parent=self)
            return
        self.terms.append({"name": self.v_tname.get().strip() or "Term",
                           "start": model.d2s(start), "end": model.d2s(end)})
        self.terms.sort(key=lambda t: t["start"])
        self._fill_terms()
        self._changed()

    def _remove_term(self):
        for iid in sorted(self.term_tree.selection(), key=int, reverse=True):
            del self.terms[int(iid)]
        self._fill_terms()
        self._changed()

    def _data(self, nb):
        f = ttk.Frame(nb, padding=10)
        store = self.app.store
        ttk.Label(f, text="Your data is stored only on this PC:").pack(anchor="w")
        ttk.Label(f, text=store.path, foreground="#555").pack(anchor="w", pady=(0, 8))
        row = ttk.Frame(f)
        row.pack(fill="x")
        ttk.Button(row, text="Open data folder", command=lambda: os.startfile(store.folder)).pack(side="left")
        ttk.Button(row, text="Back up now", command=self._backup_now).pack(side="left", padx=6)
        ttk.Button(row, text="Export to Excel…", command=self.app.export).pack(side="left")
        ttk.Label(f, text="A backup is made automatically each day (newest 30 kept).").pack(anchor="w", pady=(12, 2))
        row2 = ttk.Frame(f)
        row2.pack(fill="x")
        self.v_backup = tk.StringVar()
        self.backup_box = ttk.Combobox(row2, textvariable=self.v_backup, values=store.list_backups(),
                                       state="readonly", width=26)
        self.backup_box.pack(side="left")
        ttk.Button(row2, text="Restore this backup", command=self._restore).pack(side="left", padx=6)
        return f

    def _backup_now(self):
        self.app.store.backup()
        self.backup_box.configure(values=self.app.store.list_backups())
        messagebox.showinfo("Backup", "Backup saved.", parent=self)

    def _restore(self):
        name = self.v_backup.get()
        if name and messagebox.askyesno("Restore backup", f"Replace current data with {name}?\n"
                                        "Today's data is backed up first.", parent=self):
            self.app.restore_backup(name)
            self.snapshot = None  # the restored data replaces everything; nothing to revert
            self.close()

    def save(self):
        values = self.values()
        if values is None:
            messagebox.showerror("Settings", "Text size must be a number.", parent=self)
            return
        if self._preview_job:
            self.after_cancel(self._preview_job)
        self.app.apply_settings(values, undo=self.snapshot)
        self.snapshot = None
        self.close()

    def close(self):
        if self._preview_job:
            self.after_cancel(self._preview_job)
        if self.snapshot:  # closed without saving: put everything back as it was
            self.app.restore_snapshot(self.snapshot)
        super().close()
