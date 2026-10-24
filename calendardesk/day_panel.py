"""Day panel: every task on one day as a card with its checklist and formatted notes.

Edits typed here save without rebuilding the panel (so typing is never interrupted). Ticks, added or
removed items and moves rebuild it, keeping focus and scroll position. Changes made elsewhere (the
task dialog, the calendar) rebuild it too, but wait while an edit here is unsaved or a tick is animating.
"""
import re
import tkinter as tk
import tkinter.font as tkfont
from datetime import timedelta
from tkinter import messagebox, ttk

from . import model, theme
from .anim import TickAnimation
from .dialogs import Dialog, REMIND_CHOICES, repeat_label
from .holidays_in import holiday_name
from .richnote import RichNote

MUTED = "#6b7280"
FIRST_CARDS = 8   # built at once when the panel opens; the rest follow in small batches
BATCH = 6
EMPTY_LIST_LINE = re.compile(r"(- |\d+\. )\s*|\s*")


def note_to_save(md):
    """Drop empty trailing lines and list bullets left by pressing Enter at the end of a list."""
    lines = md.split("\n")
    while lines and EMPTY_LIST_LINE.fullmatch(lines[-1]):
        lines.pop()
    return "\n".join(lines)


class SmartEntry(ttk.Frame):
    """Add box that understands "call mom 7pm tomorrow" and shows what it understood as you type."""
    HINT = 'e.g. "call mom 7pm tomorrow", "gym every mon and thu 7am", "rent 1st every month!"'

    def __init__(self, parent, base_day, on_submit):
        super().__init__(parent)
        self.base_day, self.on_submit = base_day, on_submit
        row = ttk.Frame(self)
        row.pack(fill="x")
        self.var = tk.StringVar()
        self.entry = ttk.Entry(row, textvariable=self.var)
        self.entry.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Add", command=self.submit).pack(side="left", padx=(6, 0))
        self.preview = ttk.Label(self, foreground=MUTED, text=self.HINT)
        self.preview.pack(anchor="w", pady=(2, 0))
        self.var.trace_add("write", lambda *a: self.update_preview())
        self.entry.bind("<Return>", lambda e: self.submit())

    def update_preview(self):
        text = self.var.get().strip()
        if not text:
            self.preview.configure(text=self.HINT)
            return
        found = model.parse_quick(text, self.base_day)["found"]
        self.preview.configure(text=("↳ " + " · ".join(found)) if found else "↳ just a task")

    def submit(self):
        text = self.var.get().strip()
        if not text:
            return
        parsed = model.parse_quick(text, self.base_day)
        self.var.set("")
        self.on_submit(parsed)


class CheckBox(tk.Canvas):
    """A square tick box drawn on a small canvas, so the tick animation can play on it."""

    def __init__(self, parent, done, on_click, bg, size=18):
        super().__init__(parent, width=size, height=size, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.size = size
        p = 2
        self.box = (p, p, size - p, size - p)
        if done:
            self.create_rectangle(*self.box, fill=theme.ACCENT, outline=theme.ACCENT)
            s = size
            self.create_line(s * .26, s * .52, s * .44, s * .72, s * .76, s * .3, fill=theme.readable_on(theme.ACCENT),
                             width=2, capstyle="round", joinstyle="round")
        else:
            self.create_rectangle(*self.box, outline="#8a8f98", width=1.5)
        self.bind("<Button-1>", lambda e: on_click())


class TaskCard(ttk.Frame):
    def __init__(self, panel, parent, t):
        super().__init__(parent, padding=(8, 6), relief="solid", borderwidth=1)
        self.panel, self.t, self.day = panel, t, panel.day
        self.item_checks, self._item_saved = {}, {}
        done = model.is_done(t, self.day)
        bg = panel.bg
        tid = t["id"]

        head = ttk.Frame(self)
        head.pack(fill="x")
        self.check = CheckBox(head, done, self.click_check, bg)
        self.check.pack(side="left", padx=(0, 6))
        self.title = tk.Entry(head, relief="flat", bg=bg, bd=0, highlightthickness=0,
                              font=panel.f_done if done else panel.f_title, fg=MUTED if done else "#111827")
        self.title.insert(0, t["title"])
        self.title.pack(side="left", fill="x", expand=True)
        self.title.bind("<Return>", lambda e: self.commit_title() or "break")
        self.title.bind("<FocusOut>", lambda e: self.commit_title())
        # "Unsaved" means changed since this box was filled or last saved, not "differs from the data":
        # a change made elsewhere (the task dialog) must not look like typing here.
        self._title_saved = t["title"]
        panel.editor(self.title, (tid, "title", None), lambda: self.title.get() != self._title_saved,
                     self.commit_title)

        ticked, total = model.progress(t, self.day)
        if total:
            ttk.Label(head, text=f"{ticked}/{total}", foreground=theme.ACCENT if ticked == total else MUTED
                      ).pack(side="left", padx=(6, 0))
        chips = ttk.Label(head, text=self._chips(), foreground=MUTED, cursor="hand2")
        chips.pack(side="left", padx=(8, 0))
        chips.bind("<Button-1>", lambda e: self.edit_details())
        more = ttk.Button(head, text="⋮", width=3, style="Toolbutton", cursor="hand2")
        menu = tk.Menu(more, tearoff=0)
        menu.add_command(label="Edit details…", command=self.edit_details)
        menu.add_command(label="Move to next day", command=self.move_next_day,
                         state="normal" if t.get("repeat", "none") == "none" else "disabled")
        menu.add_separator()
        if t.get("repeat", "none") == "none":
            menu.add_command(label="Delete", command=lambda: self.delete(whole=True))
        else:
            menu.add_command(label="Delete this day", command=lambda: self.delete(whole=False))
            menu.add_command(label="Delete all repeats", command=lambda: self.delete(whole=True))
        more.configure(command=lambda: menu.tk_popup(more.winfo_rootx(), more.winfo_rooty() + more.winfo_height()))
        more.pack(side="left", padx=(6, 0))
        expanded = panel.is_expanded(t)
        ttk.Button(head, text="▾" if expanded else "▸", width=3, style="Toolbutton", cursor="hand2",
                   command=self.collapse if expanded else self.expand).pack(side="left", padx=(4, 0))
        if expanded:
            self._body(tid, bg)

    def _chips(self):
        t, out = self.t, []
        if t.get("time"):
            out.append(t["time"])
        if t.get("remind"):
            before = int(t.get("remind_before") or 0)
            out.append("🔔" + (f" {next((l for l, m in REMIND_CHOICES if m == before), '')}" if before else ""))
        if t.get("repeat", "none") != "none":
            out.append("↻ " + repeat_label(t))
        return " · ".join(out) or "+ details"

    def _body(self, tid, bg):
        panel, t = self.panel, self.t
        body = ttk.Frame(self, padding=(24, 4, 0, 0))
        body.pack(fill="x")
        for item in t.get("items", []):
            row = ttk.Frame(body)
            row.pack(fill="x", pady=1)
            iid = item["id"]
            box = CheckBox(row, model.item_done(t, item, self.day), lambda iid=iid: self.click_item(iid), bg, size=16)
            box.pack(side="left", padx=(0, 6))
            self.item_checks[iid] = box
            done = model.item_done(t, item, self.day)
            e = tk.Entry(row, relief="flat", bg=bg, bd=0, highlightthickness=0,
                         font=panel.f_item_done if done else panel.f_item, fg=MUTED if done else "#1f2937")
            e.insert(0, item["text"])
            e.pack(side="left", fill="x", expand=True)
            self._item_saved[iid] = item["text"]
            commit = lambda e=e, item=item: self.commit_item(e, item)
            e.bind("<Return>", lambda ev, c=commit: c() or "break")
            e.bind("<FocusOut>", lambda ev, c=commit: c())
            panel.editor(e, (tid, "item", iid), lambda e=e, iid=iid: e.get() != self._item_saved[iid], commit)
            ttk.Button(row, text="✕", width=2, command=lambda item=item: self.delete_item(item)).pack(side="left")

        add = ttk.Frame(body)
        add.pack(fill="x", pady=(2, 4))
        ttk.Label(add, text="+", foreground=MUTED).pack(side="left", padx=(3, 8))
        self.add_entry = ttk.Entry(add)
        self.add_entry.pack(side="left", fill="x", expand=True)
        self.add_entry.bind("<Return>", lambda e: self.add_item() or "break")
        panel.editor(self.add_entry, (tid, "add", None), lambda: False, lambda: None)

        bar = ttk.Frame(body)
        bar.pack(fill="x")
        ttk.Label(bar, text="Notes", foreground=MUTED).pack(side="left")
        lines = (t.get("note") or "").count("\n") + 1
        self.note = RichNote(body, height=min(12, max(3, lines + 1)), font=panel.f_note, relief="solid", bd=1,
                             padx=6, pady=4)
        for text, cmd in (("B", self.note.toggle_bold), ("1. List", self.note.toggle_number),
                          ("• List", self.note.toggle_bullet)):
            ttk.Button(bar, text=text, width=len(text) + 2, command=cmd).pack(side="right", padx=(4, 0))
        self.note.load(t.get("note") or "")
        self.note.pack(fill="x", pady=(2, 2))
        self._note_saved = note_to_save(self.note.dump())  # normalised: a stored "• " comes back as "- "
        self.note.bind("<<NoteChanged>>", lambda e: self.commit_note())
        self.note.bind("<FocusOut>", lambda e: self.commit_note(), add="+")
        panel.editor(self.note, (tid, "note", None),
                     lambda: note_to_save(self.note.dump()) != self._note_saved, self.commit_note)

    # -- saving edits --------------------------------------------------------------
    def commit_title(self):
        text = self.title.get().strip()
        if not text:  # a task always keeps a title
            self.title.delete(0, "end")
            self.title.insert(0, self._title_saved)
            return
        if text != self._title_saved:
            self.t["title"] = self._title_saved = text
            self.panel.own_save()

    def commit_item(self, entry, item):
        if not entry.winfo_exists():
            return
        text = entry.get().strip()
        if not text:
            self.delete_item(item)
        elif text != self._item_saved[item["id"]]:
            item["text"] = self._item_saved[item["id"]] = text
            self.panel.own_save()

    def commit_note(self):
        if not self.note.winfo_exists():
            return
        md = note_to_save(self.note.dump())
        if md != self._note_saved:
            self.t["note"] = self._note_saved = md
            self.panel.own_save()

    # -- actions --------------------------------------------------------------------
    def add_item(self):
        text = self.add_entry.get().strip()
        if not text:
            return
        self.t.setdefault("items", []).append(model.new_item(text))
        if model.is_done(self.t, self.day):  # a new open item means the task isn't finished
            model.set_done(self.t, self.day, False)
        self.panel.structural((self.t["id"], "add", None))

    def delete_item(self, item):
        items = self.t.get("items", [])
        if item in items:
            items.remove(item)
            self.panel.structural()

    def click_check(self):
        key = (self.t["id"], self.day)
        if key in self.panel.animating:
            return
        self.panel.commit_all()
        ticking = not model.is_done(self.t, self.day)
        self.panel.animating.add(key)

        def finished():
            self.panel.animating.discard(key)
            self.panel.app.toggle_done(self.t, self.day, ticking)
        TickAnimation(self.check, self.check.box, None, theme.ACCENT, theme.DONE, finished, ticking).start()

    def click_item(self, iid):
        item = next((i for i in self.t.get("items", []) if i["id"] == iid), None)
        key = (self.t["id"], self.day, iid)
        if item is None or key in self.panel.animating:
            return
        self.panel.commit_all()
        ticking = not model.item_done(self.t, item, self.day)
        self.panel.animating.add(key)
        box = self.item_checks[iid]

        def finished():
            self.panel.animating.discard(key)
            model.set_item_done(self.t, item, self.day, ticking)
            self.panel.app.changed()
        TickAnimation(box, box.box, None, theme.ACCENT, theme.DONE, finished, ticking).start()

    def expand(self):
        self.panel.expanded[self.t["id"]] = True
        self.panel.structural()

    def collapse(self):
        self.panel.expanded[self.t["id"]] = False
        self.panel.structural()

    def edit_details(self):
        self.panel.commit_all()
        self.panel.app.edit_task(task=self.t, day=self.day)

    def move_next_day(self):
        if self.t.get("repeat", "none") != "none":
            return
        self.panel.commit_all()
        self.panel.app.move_task(self.t, self.day + timedelta(1))

    def delete(self, whole):
        what = "this day of " if not whole else ""
        rest = " and all its repeats" if whole and self.t.get("repeat", "none") != "none" else ""
        if messagebox.askyesno("Delete task", f"Delete {what}'{self.t['title']}'{rest}?", parent=self.panel):
            self.panel.app.delete_task(self.t, self.day, whole=whole)


class DayPanel(Dialog):
    def __init__(self, app, day):
        super().__init__(app, day.strftime("%A %d %B %Y"), resizable=True)
        self.day = day
        self.cards, self.expanded, self.animating = {}, {}, set()
        self._editors, self._own, self._pending, self._rebuilding = [], False, False, False
        self._todo, self._build_job = [], None
        self.bg = ttk.Style(self).lookup("TFrame", "background") or self.cget("bg")
        fam = theme.FAMILY
        self.f_title = tkfont.Font(self, family=fam, size=11, weight="bold")
        self.f_done = tkfont.Font(self, family=fam, size=11, weight="bold", overstrike=1)
        self.f_item = tkfont.Font(self, family=fam, size=10)
        self.f_item_done = tkfont.Font(self, family=fam, size=10, overstrike=1)
        self.f_note = tkfont.Font(self, family=fam, size=10)

        head = ttk.Frame(self)
        head.pack(fill="x")
        ttk.Label(head, text=day.strftime("%a %d %b %Y"), font=(fam, 14, "bold")).pack(side="left")
        self.info = ttk.Label(head, foreground="#c05f00")
        self.info.pack(side="left", padx=(10, 0))
        ttk.Button(head, text="Countdown to this day…", command=lambda: app.edit_countdown(day=day)).pack(side="right")

        colours = ttk.Frame(self)
        colours.pack(fill="x", pady=(6, 0))
        ttk.Label(colours, text="Date colour:", foreground=MUTED).pack(side="left")
        for col in theme.DATE_COLORS:
            tk.Button(colours, bg=col, activebackground=col, width=2, relief="flat", bd=0,
                      command=lambda col=col: app.set_date_color(day, col)).pack(side="left", padx=2)
        ttk.Button(colours, text="Custom…", command=lambda: app.set_date_color(day, "custom", parent=self)
                   ).pack(side="left", padx=(4, 2))
        ttk.Button(colours, text="Clear", command=lambda: app.set_date_color(day, None)).pack(side="left")

        self.add_box = SmartEntry(self, day, self._add)
        self.add_box.pack(fill="x", pady=(10, 6))

        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True)
        self.scroll = tk.Canvas(wrap, bg=self.bg, highlightthickness=0, bd=0)
        bar = ttk.Scrollbar(wrap, orient="vertical", command=self.scroll.yview)
        self.scroll.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.scroll.pack(side="left", fill="both", expand=True)
        self.inner = ttk.Frame(self.scroll)
        self._inner_id = self.scroll.create_window(0, 0, anchor="nw", window=self.inner)
        self.scroll.bind("<Configure>", lambda e: self.scroll.itemconfigure(self._inner_id, width=e.width))
        self.inner.bind("<Configure>", lambda e: self.scroll.configure(scrollregion=self.scroll.bbox("all")))
        self.bind("<MouseWheel>", self._wheel)
        self.empty = ttk.Label(self.inner, text="No tasks on this day yet.", foreground=MUTED)

        self.geometry("620x660")
        self.minsize(440, 320)
        self._update_header()
        self.rebuild()
        self.present()
        self.add_box.entry.focus_set()

    # -- the registry of in-place editors (for saving, deferring refreshes and keeping focus) -------
    def editor(self, widget, key, dirty, commit):
        self._editors.append((widget, key, dirty, commit))

    def _dirty(self):
        return any(w.winfo_exists() and dirty() for w, _, dirty, _ in self._editors)

    def commit_all(self):
        for w, _, dirty, commit in list(self._editors):
            if w.winfo_exists() and dirty():
                commit()

    def _focus(self):
        try:
            f = self.focus_get()
        except (KeyError, tk.TclError):
            return None
        for w, key, _, _ in self._editors:
            if w is f:
                return key, w.index("insert")
        return None

    def _restore_focus(self, saved):
        if not saved:
            return
        key, index = saved
        for w, k, _, _ in self._editors:
            if k == key:
                w.focus_set()
                if isinstance(w, tk.Text):
                    w.mark_set("insert", index)
                    w.see("insert")
                else:
                    w.icursor(index)
                self._scroll_into_view(w)
                return

    def _scroll_into_view(self, widget):
        self.update_idletasks()
        total = self.inner.winfo_height()
        if total <= 0:
            return
        y = widget.winfo_rooty() - self.inner.winfo_rooty()
        top, bottom = (f * total for f in self.scroll.yview())
        if y < top or y + widget.winfo_height() > bottom:
            self.scroll.yview_moveto(max(0, y - 40) / total)

    # -- saving and refreshing ----------------------------------------------------------
    def own_save(self):
        """Save an edit made in this panel without rebuilding it (the widgets already show it)."""
        self._own = True
        try:
            self.app.changed()
        finally:
            self._own = False
        if self._pending and not self._rebuilding and not self.animating and not self._dirty():
            self.rebuild()

    def structural(self, focus=None):
        """Save a change that alters the cards (items added/removed, expand/collapse) and rebuild."""
        self._own = True
        try:
            self.app.changed()
        finally:
            self._own = False
        self.rebuild(focus=(focus, "end") if focus else None)

    def refresh(self):
        if not self.winfo_exists():
            return
        self._update_header()
        if self._own:
            return
        if self.animating or self._dirty():
            self._pending = True  # rebuilt once the edit is saved / the animation ends
            return
        self.rebuild()

    def rebuild(self, focus=None):
        if self._rebuilding:
            return
        self._rebuilding = True
        try:
            self.commit_all()
            focus = focus or self._focus()
            top = self.scroll.yview()[0]
            for card in self.cards.values():
                card.destroy()
            self.cards, self._editors = {}, []
            self._cancel_build()
            tasks = model.tasks_on(self.app.store.data["tasks"], self.day)
            if tasks:
                self.empty.pack_forget()
            else:
                self.empty.pack(pady=20)
            # Opening fresh: show the first cards now and add the rest just after, so a busy day
            # still opens quickly. After an edit: build everything so focus and scroll come back.
            self._todo = list(tasks)
            self._build(len(tasks) if focus or top > 0 else FIRST_CARDS)
            if self._todo:
                self._build_job = self.after(1, self._build_rest)
            self.update_idletasks()
            self.scroll.configure(scrollregion=self.scroll.bbox("all"))
            self.scroll.yview_moveto(top)
            self._restore_focus(focus)
        finally:
            self._rebuilding = False
            self._pending = False

    def _build(self, n):
        for t in self._todo[:n]:
            card = TaskCard(self, self.inner, t)
            card.pack(fill="x", pady=4, padx=(2, 6))
            self.cards[t["id"]] = card
        del self._todo[:n]

    def _build_rest(self):
        self._build_job = None
        if not self.winfo_exists():
            return
        self._build(BATCH)
        if self._todo:
            self._build_job = self.after(1, self._build_rest)

    def _cancel_build(self):
        if self._build_job:
            self.after_cancel(self._build_job)
            self._build_job = None
        self._todo = []

    def is_expanded(self, t):
        if t["id"] in self.expanded:
            return self.expanded[t["id"]]
        return bool(t.get("items") or t.get("note"))

    def _update_header(self):
        info = []
        hol = holiday_name(self.day)
        if hol:
            info.append(hol)
        sw = model.school_week(self.app.settings["school_terms"], self.day)
        if sw:
            info.append(f"{sw[0]} · week {sw[1]}")
        self.info.configure(text="  ·  ".join(info))

    def _add(self, parsed):
        t = model.task_from_quick(parsed)
        self.app.add_task(t)
        if parsed["date"] != self.day:
            self.add_box.preview.configure(text=f"↳ added to {parsed['date'].strftime('%a %d %b')}")

    def _wheel(self, e):
        w = e.widget
        if isinstance(w, tk.Text) and w.yview() != (0.0, 1.0):
            return  # the note scrolls itself
        if self.scroll.yview() != (0.0, 1.0):
            self.scroll.yview_scroll(-1 if e.delta > 0 else 1, "units")

    def close(self):
        if self.winfo_exists():
            self._cancel_build()
            self.commit_all()
        super().close()
