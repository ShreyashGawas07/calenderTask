"""Sticky notes, countdown cards, the floating mini-calendar and reminder pop-ups."""
import tkinter as tk
import winsound
from datetime import date

from . import model, theme, winapi
from .anim import TickAnimation
from .desktop_cal import WEEKDAYS, shift_month
from .holidays_in import holiday_name
from .pinned import PinnedWindow


class NoteWindow(PinnedWindow):
    def __init__(self, app, note):
        self.note = note
        super().__init__(app, note.get("geometry") or "220x200+120+120", bg=note["color"], min_size=(140, 90))
        f = theme.fonts(app.settings["font_size"])
        bar = tk.Frame(self.win, bg=note["color"], height=22, cursor="fleur")
        bar.pack(fill="x")
        self.bar = bar
        menu_btn = tk.Label(bar, text="☰", bg=note["color"], fg="#333", font=f["bold"], cursor="hand2")
        menu_btn.pack(side="left", padx=6)
        menu_btn.bind("<Button-1>", self._menu)
        close = tk.Label(bar, text="✕", bg=note["color"], fg="#333", font=f["bold"], cursor="hand2")
        close.pack(side="right", padx=6)
        close.bind("<Button-1>", lambda e: self.app.hide_note(self.note))
        self.text = tk.Text(self.win, bg=note["color"], fg="#222", font=f["normal"], relief="flat",
                            wrap="word", padx=8, pady=4, undo=True, insertbackground="#222")
        self.text.pack(fill="both", expand=True)
        self.text.insert("1.0", note.get("text", ""))
        self.text.bind("<KeyRelease>", self._changed)
        grip = tk.Label(self.win, text="◢", bg=note["color"], fg="#888", cursor="size_nw_se")
        grip.place(relx=1, rely=1, anchor="se")
        self.grip = grip
        self.make_draggable(bar, on_done=self._moved)
        self.make_resizable(grip, on_done=self._moved)
        self._pending = None
        self.text.bind("<FocusIn>", lambda e: self.to_front(focus=False))
        self.restyle()

    def restyle(self):
        """Follow the text size, font and card size settings."""
        s = self.app.settings
        f = theme.fonts(s["font_size"] * s["card_scale"])
        self.text.configure(font=f["normal"])
        for w in self.bar.winfo_children():
            w.configure(font=f["bold"])

    def _changed(self, e=None):
        if self._pending:
            self.win.after_cancel(self._pending)
        self._pending = self.win.after(600, self._store_text)

    def _store_text(self):
        self._pending = None
        self.note["text"] = self.text.get("1.0", "end-1c")
        self.app.save()

    def _moved(self):
        self.note["geometry"] = self.geometry()
        self.app.save()

    def set_color(self, color):
        self.note["color"] = color
        for w in (self.win, self.bar, self.text, self.grip, *self.bar.winfo_children()):
            w.configure(bg=color)
        self.app.save()

    def _menu(self, e):
        m = tk.Menu(self.win, tearoff=0)
        for col in theme.NOTE_COLORS:
            m.add_command(label="      ", background=col, activebackground=col,
                          command=lambda col=col: self.set_color(col))
        m.add_separator()
        m.add_command(label="New note", command=self.app.new_note)
        m.add_command(label="Hide note", command=lambda: self.app.hide_note(self.note))
        m.add_command(label="Delete note…", command=lambda: self.app.delete_note(self.note))
        m.tk_popup(e.x_root, e.y_root)

    def flush(self):
        if self._pending:
            self.win.after_cancel(self._pending)
            self._store_text()


class CountdownCard(PinnedWindow):
    BASE_H = 130  # card height at which text uses the chosen text size

    def __init__(self, app, cd):
        self.cd = cd
        super().__init__(app, cd.get("geometry") or "210x130+80+80", alpha=app.settings["opacity"],
                         bg=theme.BG, min_size=(140, 90))
        self.canvas = tk.Canvas(self.win, bg=theme.BG, highlightthickness=0, cursor="fleur")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.refresh())
        self.canvas.bind("<Button-3>", self._menu)
        self.canvas.bind("<Double-Button-1>", lambda e: self.app.edit_countdown(cd=self.cd))
        locked = lambda: self.app.settings["locked"]
        self.make_resizable(self.canvas, on_done=self._moved, locked=locked, tag="grip")
        self.make_draggable(self.canvas, on_done=self._moved, locked=locked)

    def _moved(self):
        self.cd["geometry"] = self.geometry()
        self.app.save()

    def refresh(self):
        c = self.canvas
        c.delete("all")
        W, H = c.winfo_width(), c.winfo_height()
        if W < 20:
            return
        z = min(3.0, max(0.7, H / (self.BASE_H * self.win.winfo_fpixels("1i") / 96)))
        f = theme.fonts(self.app.settings["font_size"] * z)
        P = lambda v: int(v * z)
        color = self.cd.get("color") or theme.ACCENT
        style = self.cd.get("style", "minimal")
        days, target, years = model.countdown_info(self.cd, self.app.today())
        if days == 0:
            big, unit = "Today", ""
        else:
            big, unit = str(abs(days)), ("days left" if days > 0 else "days ago")
            if abs(days) == 1:
                unit = unit.replace("days", "day")
        sub = target.strftime("%a, %d %b %Y")
        if years is not None and years > 0:
            sub += f"  ·  {self._ordinal(years)} year"

        # Background and text colours for each style.
        if style == "solid":
            c.configure(bg=color)
            fg = theme.readable_on(color)
            num_fg, soft = fg, theme.mix(fg, color, 0.75)
        elif style == "gradient":
            c.configure(bg=color)
            dark = theme.mix("#000000", color, 0.55)
            steps = 32
            for i in range(steps):
                c.create_rectangle(0, H * i / steps, W, H * (i + 1) / steps + 1, width=0,
                                   fill=theme.mix(dark, color, i / (steps - 1)))
            fg = "#ffffff"
            num_fg, soft = fg, theme.mix(fg, color, 0.8)
        else:
            c.configure(bg=theme.BG)
            fg, num_fg, soft = theme.TEXT, color, theme.MUTED
            if style == "minimal":
                c.create_rectangle(0, 0, W, P(5), fill=color, width=0)

        left = P(12)
        if style == "ring":
            # Ring fills up as the date gets closer (over the last year, or since the card was made).
            span = 365 if self.cd.get("yearly") else max(1, (target - model.s2d(self.cd.get("created") or self.cd["date"])).days)
            span = max(span, days, 1)
            progress = 1.0 if days <= 0 else max(0.0, 1 - days / span)
            d = min(H - P(24), W * 0.42)
            rx, ry = P(12), (H - d) / 2
            c.create_oval(rx, ry, rx + d, ry + d, outline=theme.mix(color, theme.BG, 0.25), width=P(7))
            if progress > 0:
                c.create_arc(rx, ry, rx + d, ry + d, start=90, extent=-359.9 * progress, style="arc",
                             outline=color, width=P(7))
            ring_font = f["title"] if len(big) < 4 else f["bold"]
            c.create_text(rx + d / 2, ry + d / 2, text=big, fill=fg, font=ring_font)
            left = rx + d + P(12)
            c.create_text(left, H / 2 - P(14), anchor="w", fill=fg, font=f["bold"],
                          text=theme.fit(f["bold"], self.cd["title"], W - left - P(8)))
            c.create_text(left, H / 2 + P(4), anchor="w", text=unit, fill=soft, font=f["normal"])
            c.create_text(left, H / 2 + P(20), anchor="w", fill=soft, font=f["small"],
                          text=theme.fit(f["small"], sub, W - left - P(8)))
        else:
            c.create_text(left, P(16), anchor="nw", text=theme.fit(f["bold"], self.cd["title"], W - 2 * left),
                          fill=fg, font=f["bold"])
            item = c.create_text(left, H / 2 + P(4), anchor="w", text=big, fill=num_fg, font=f["big"])
            c.create_text(c.bbox(item)[2] + P(8), H / 2 + P(10), anchor="w", text=unit, fill=soft, font=f["normal"])
            c.create_text(left, H - P(10), anchor="sw", text=theme.fit(f["small"], sub, W - 2 * left),
                          fill=soft, font=f["small"])
        g = P(12)
        c.create_polygon(W, H - g, W, H, W - g, H, fill=theme.mix(fg, c["bg"], 0.35), outline="",
                         tags=("grip",))

    @staticmethod
    def _ordinal(n):
        suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return f"{n}{suffix}"

    def _menu(self, e):
        m = tk.Menu(self.win, tearoff=0)
        m.add_command(label="Edit…", command=lambda: self.app.edit_countdown(cd=self.cd))
        m.add_command(label="Hide card", command=lambda: self.app.hide_countdown(self.cd))
        m.add_command(label="Delete…", command=lambda: self.app.delete_countdown(self.cd))
        m.tk_popup(e.x_root, e.y_root)


class MiniCalendar(PinnedWindow):
    """Small month view on the wallpaper for a quick look; click a day to list its tasks.
    Like the main calendar it stays behind your apps until the hotkey brings it forward."""

    def __init__(self, app):
        t = app.today()
        self.year, self.month, self.selected = t.year, t.month, t
        l, top, r, b = winapi.work_area()
        super().__init__(app, app.settings.get("mini_geometry") or f"250x330+{r - 270}+{b - 350}", bg=theme.BG)
        self.canvas = tk.Canvas(self.win, bg=theme.BG, highlightthickness=1,
                                highlightbackground=theme.GRID)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.redraw())
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Double-Button-1>", self._double)
        self.canvas.bind("<ButtonPress-1>", self._press, add="+")
        self.canvas.bind("<B1-Motion>", self._motion)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<MouseWheel>", lambda e: self.go(-1 if e.delta > 0 else 1))
        self.hits, self._drag = [], None
        self.animating, self._task_items = set(), {}

    def go(self, delta):
        self.year, self.month = shift_month(self.year, self.month, delta)
        self.redraw()

    def redraw(self):
        c = self.canvas
        c.delete("all")
        c.configure(bg=theme.BG, highlightbackground=theme.GRID)
        self.hits, self._task_items = [], {}
        W, H = c.winfo_width(), c.winfo_height()
        f = theme.fonts(max(8, self.app.settings["font_size"] - 1))
        today = self.app.today()
        c.create_rectangle(0, 0, W, 30, fill=theme.PANEL, width=0)
        self.drag_band = 30
        for x, text, action in ((14, "‹", lambda: self.go(-1)), (34, "›", lambda: self.go(1)),
                                (W - 14, "✕", self.app.toggle_mini)):
            item = c.create_text(x, 15, text=text, fill=theme.TEXT, font=f["bold"])
            self.hits.append((*self._pad(c.bbox(item)), "btn", action))
        c.create_text(W / 2, 15, text=date(self.year, self.month, 1).strftime("%B %Y"),
                      fill=theme.TEXT, font=f["bold"])
        monday_first = self.app.settings["week_starts_monday"]
        names = WEEKDAYS if monday_first else WEEKDAYS[-1:] + WEEKDAYS[:-1]
        cw = (W - 10) / 7
        for i, n in enumerate(names):
            c.create_text(5 + cw * i + cw / 2, 42, text=n[:2], fill=theme.MUTED, font=f["small"])
        rh = 26
        tasks = self.app.store.data["tasks"]
        for r, week in enumerate(model.month_grid(self.year, self.month, 0 if monday_first else 6)):
            for i, d in enumerate(week):
                cx, cy = 5 + cw * i + cw / 2, 62 + r * rh
                if d == self.selected:
                    c.create_oval(cx - 11, cy - 11, cx + 11, cy + 11, fill=theme.ACCENT, width=0)
                elif d == today:
                    c.create_oval(cx - 11, cy - 11, cx + 11, cy + 11, outline=theme.ACCENT)
                col = theme.DIM if d.month != self.month else (
                    theme.HOLIDAY if self.app.settings["show_holidays"] and holiday_name(d)
                    else theme.WEEKEND if d.weekday() >= 5 else theme.TEXT)
                c.create_text(cx, cy, text=str(d.day), fill=col, font=f["normal"])
                if any(model.occurs_on(t, d) for t in tasks):
                    c.create_oval(cx - 2, cy + 9, cx + 2, cy + 13, fill=theme.HOLIDAY, width=0)
                self.hits.append((cx - cw / 2, cy - rh / 2, cx + cw / 2, cy + rh / 2, "day", d))
        y = 62 + 6 * rh - 4
        c.create_line(8, y, W - 8, y, fill=theme.GRID)
        label = self.selected.strftime("%a %d %b")
        hol = holiday_name(self.selected) if self.app.settings["show_holidays"] else None
        if hol:
            label += f" · {hol}"
        c.create_text(10, y + 6, anchor="nw", text=theme.fit(f["bold"], label, W - 20),
                      fill=theme.TEXT, font=f["bold"])
        y += 26
        day_tasks = model.tasks_on(tasks, self.selected)
        if not day_tasks:
            c.create_text(10, y, anchor="nw", text="No tasks", fill=theme.MUTED, font=f["small"])
        for t in day_tasks:
            if y > H - 16:
                break
            done = model.is_done(t, self.selected)
            color = theme.DONE if done else (theme.ink(t["color"], theme.BG) if t.get("color") else theme.TEXT)
            box = c.create_text(10, y, anchor="nw", text="☑" if done else "☐", fill=color, font=f["normal"])
            self.hits.append((*self._pad(c.bbox(box)), "check", t))
            text = (t["time"] + " " if t.get("time") else "") + t["title"]
            ticked, total = model.progress(t, self.selected)
            count = f"{ticked}/{total}" if total else ""
            count_w = f["small"].measure(" " + count) if count else 0
            title = c.create_text(28, y, anchor="nw", text=theme.fit(f["normal"], text, W - 38 - count_w),
                                  fill=color, font=f["strike"] if done else f["normal"])
            if count:
                c.create_text(c.bbox(title)[2] + 3, y + 1, anchor="nw", text=count, font=f["small"],
                              fill=theme.DONE if done else (theme.ACCENT if ticked == total else theme.MUTED))
            self._task_items[t["id"]] = (box, title)
            y += 20

    @staticmethod
    def _pad(bb, p=3):
        return bb[0] - p, bb[1] - p, bb[2] + p, bb[3] + p

    def _hit(self, e):
        for h in self.hits:
            if h[0] <= e.x <= h[2] and h[1] <= e.y <= h[3]:
                return h
        return None

    def _click(self, e):
        h = self._hit(e)
        if not h:
            return
        if h[4] == "btn":
            h[5]()
        elif h[4] == "day":
            self.selected = h[5]
            self.redraw()
        elif h[4] == "check":
            self._animate_tick(h[5], self.selected)

    def _animate_tick(self, t, day):
        key = (t["id"], day)
        items = self._task_items.get(t["id"])
        if key in self.animating:
            return
        ticking = not model.is_done(t, day)
        if not items:
            self.app.toggle_done(t, day, ticking)
            return
        self.animating.add(key)

        def finished():
            self.animating.discard(key)
            self.app.toggle_done(t, day, ticking)
        x0, y0, x1, y1 = self.canvas.bbox(items[0])
        side = min(x1 - x0, y1 - y0) - 2
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        TickAnimation(self.canvas, (cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2), items[1],
                      theme.ACCENT, theme.DONE, finished, ticking).start()

    def _double(self, e):
        h = self._hit(e)
        if h and h[4] == "day":
            self.app.open_day(h[5])

    def _press(self, e):
        on_button = (h := self._hit(e)) and h[4] == "btn"
        self._drag = (e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y()) \
            if e.y < self.drag_band and not on_button else None

    def _motion(self, e):
        if self._drag:
            self.win.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")

    def _release(self, e):
        if self._drag:
            self._drag = None
            self.app.settings["mini_geometry"] = self.win.geometry()
            self.app.save()



class ReminderPopup:
    """Corner pop-up for a due task, stacked above earlier ones."""
    open_popups = []

    def __init__(self, app, task, day):
        self.app, self.task, self.day = app, task, day
        f = theme.fonts(app.settings["font_size"] + 1)
        w = tk.Toplevel(app.root, bg=theme.PANEL, highlightthickness=2, highlightbackground=theme.ACCENT)
        self.win = w
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        tk.Label(w, text="Reminder", bg=theme.PANEL, fg=theme.ACCENT, font=f["bold"]).pack(anchor="w", padx=14, pady=(10, 0))
        tk.Label(w, text=task["title"], bg=theme.PANEL, fg=theme.TEXT, font=f["title"], wraplength=300,
                 justify="left").pack(anchor="w", padx=14)
        when = day.strftime("%a %d %b") + (f" at {task['time']}" if task.get("time") else "")
        tk.Label(w, text=when, bg=theme.PANEL, fg=theme.MUTED, font=f["normal"]).pack(anchor="w", padx=14)
        if task.get("note"):
            tk.Label(w, text=task["note"][:200], bg=theme.PANEL, fg=theme.TEXT, font=f["small"],
                     wraplength=300, justify="left").pack(anchor="w", padx=14, pady=(4, 0))
        row = tk.Frame(w, bg=theme.PANEL)
        row.pack(fill="x", padx=10, pady=10)
        for text, action in (("Done", self.done), ("Snooze 10 min", self.snooze), ("Dismiss", self.close)):
            tk.Button(row, text=text, command=action, relief="flat", bg=theme.GRID, fg=theme.TEXT,
                      activebackground=theme.ACCENT, font=f["normal"], padx=10).pack(side="left", padx=4)
        ReminderPopup.open_popups.append(self)
        self._place()
        winsound.MessageBeep(winsound.MB_ICONASTERISK)

    def _place(self):
        l, t, r, b = winapi.work_area()
        y = b - 12
        for p in ReminderPopup.open_popups:
            p.win.update_idletasks()
            y -= p.win.winfo_reqheight() + 8
            p.win.geometry(f"340x{p.win.winfo_reqheight()}+{r - 352}+{y}")

    def done(self):
        self.app.toggle_done(self.task, self.day, value=True)
        self.close()

    def snooze(self):
        self.app.snooze(self.task, self.day, minutes=10)
        self.close()

    def close(self):
        ReminderPopup.open_popups.remove(self)
        self.win.destroy()
        if ReminderPopup.open_popups:
            ReminderPopup.open_popups[0]._place()
