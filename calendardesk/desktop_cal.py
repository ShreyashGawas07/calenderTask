"""The month calendar that sits on the desktop wallpaper."""
import math
import time
import tkinter as tk
from datetime import date, datetime, timedelta

from . import model, theme, winapi
from .anim import TickAnimation
from .holidays_in import holiday_name
from .pinned import PinnedWindow

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
BASE_W, BASE_H = 780, 560   # size at which text is drawn at the chosen text size
GLOW_RINGS = 5
CLICK_DELAY_MS = 260        # wait this long before treating a click as single (not double)


def shift_month(year, month, delta):
    m = year * 12 + month - 1 + delta
    return m // 12, m % 12 + 1


class DesktopCalendar(PinnedWindow):
    def __init__(self, app):
        s = app.settings
        geometry = s.get("calendar_geometry") or self._default_geometry(app.root)
        super().__init__(app, geometry, alpha=s["opacity"], bg=theme.BG, min_size=(360, 280))
        today = app.today()
        self.year, self.month = today.year, today.month
        self.canvas = tk.Canvas(self.win, bg=theme.BG, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.hits = []
        self.quick = None
        self.glow = []          # (item, strength, cell colour) for the pulsing today border
        self.animating = set()   # (task id, day) whose tick animation is playing; clicks on them wait
        self._task_items = {}    # (task id, day) -> (checkbox item, title item) for the animation
        self._pulse_job = None
        self._glow_steady = True  # rings currently show their full-strength (unanimated) colour
        self.zoom = 1.0
        self._click_job = None
        self.scale = self.win.winfo_fpixels("1i") / 96.0

        c = self.canvas
        c.bind("<Configure>", lambda e: self.redraw())
        c.bind("<Button-1>", self._click)
        c.bind("<Double-Button-1>", self._double)
        c.bind("<Button-3>", self._context)
        c.bind("<MouseWheel>", lambda e: self.go(-1 if e.delta > 0 else 1))
        locked = lambda: self.app.settings["locked"]
        self.make_draggable(c, on_done=self._save_geometry, locked=locked, tag="drag")
        self.make_resizable(c, on_done=self._save_geometry, locked=locked, tag="grip")

    @staticmethod
    def _default_geometry(root):
        w, h = BASE_W, BASE_H
        x = max(0, root.winfo_screenwidth() - w - 40)
        return f"{w}x{h}+{x}+60"

    def _save_geometry(self):
        self.app.settings["calendar_geometry"] = self.geometry()
        self.app.save()

    def px(self, v):
        return int(v * self.scale * self.zoom)

    # -- navigation --------------------------------------------------------
    def go(self, delta):
        self.year, self.month = shift_month(self.year, self.month, delta)
        self.redraw()

    def go_today(self):
        t = self.app.today()
        self.year, self.month = t.year, t.month
        self.redraw()

    def show_month_of(self, day):
        self.year, self.month = day.year, day.month
        self.redraw()

    def set_opacity(self, value):
        self.win.attributes("-alpha", value)

    # -- drawing -----------------------------------------------------------
    def redraw(self):
        c = self.canvas
        c.delete("all")
        c.configure(bg=theme.BG)
        self.win.configure(bg=theme.BG)
        self.hits, self.glow = [], []
        self._task_items = {}
        W, H = c.winfo_width(), c.winfo_height()
        if W < 50 or H < 50:
            return
        s = self.app.settings
        # Text and spacing grow and shrink with the window (relative to the default size).
        self.zoom = min(2.2, max(0.7, min(W / (BASE_W * self.scale), H / (BASE_H * self.scale)))) \
            if s["auto_scale"] else 1.0
        f = theme.fonts(s["font_size"] * self.zoom)
        P = self.px
        today = self.app.today()
        monday_first = s["week_starts_monday"]
        names = WEEKDAYS if monday_first else WEEKDAYS[-1:] + WEEKDAYS[:-1]
        terms = s["school_terms"]
        show_weeks = s["show_week_numbers"]
        this_month = (self.year, self.month) == (today.year, today.month)

        # Header: navigation, title and actions. The empty part of the header drags the window.
        hh = P(40)
        c.create_rectangle(0, 0, W, hh, fill=theme.PANEL, width=0, tags=("drag",))
        x = P(12)
        for label, action in (("‹", lambda: self.go(-1)), ("›", lambda: self.go(1))):
            item = c.create_text(x, hh / 2, text=label, fill=theme.TEXT, font=f["title"], anchor="w")
            self._button(item, action)
            x = c.bbox(item)[2] + P(10)
        title = date(self.year, self.month, 1).strftime("%B %Y")
        item = c.create_text(x + P(4), hh / 2, text=title, fill=theme.TEXT, font=f["title"],
                             anchor="w", tags=("drag",))
        x = c.bbox(item)[2] + P(14)
        if not this_month:
            self._button(c.create_text(x, hh / 2, text="Today", fill=theme.ACCENT,
                                       font=f["bold"], anchor="w"), self.go_today)
        right = W - P(12)
        for label, action in (("☰", self._main_menu), ("Search", self.app.search),
                              ("+ Task", lambda: self.app.edit_task(day=today))):
            item = c.create_text(right, hh / 2, text=label, fill=theme.TEXT, font=f["bold"], anchor="e")
            self._button(item, action)
            right = c.bbox(item)[0] - P(16)

        # Weekday names; today's weekday is lit when "highlight week" is on.
        wk_w = P(30) if show_weeks else 0
        top = hh + P(4)
        row_h_names = P(22)
        cw = (W - wk_w - P(8)) / 7
        today_col = (today.weekday() - (0 if monday_first else 6)) % 7
        for i, n in enumerate(names):
            weekend = (i >= 5) if monday_first else (i in (0, 6))
            cx = wk_w + P(4) + cw * i + cw / 2
            lit = s["today_week"] and this_month and i == today_col
            c.create_text(cx, top + row_h_names / 2, text=n, font=f["bold"],
                          fill=theme.ACCENT if lit else (theme.WEEKEND if weekend else theme.MUTED))
            if lit:
                c.create_line(cx - P(14), top + row_h_names - P(2), cx + P(14), top + row_h_names - P(2),
                              fill=theme.ACCENT, width=P(2), capstyle="round")
        grid_top = top + row_h_names
        rows = model.month_grid(self.year, self.month, 0 if monday_first else 6)
        rh = (H - grid_top - P(6)) / 6
        line_h = f["normal"].metrics("linespace") + P(1)

        for r, week in enumerate(rows):
            y0 = grid_top + r * rh
            current_week = s["today_week"] and today in week
            if show_weeks:
                sw = next((model.school_week(terms, d) for d in week if model.school_week(terms, d)), None)
                label = f"W{sw[1]}" if sw else f"{week[0].isocalendar()[1]}"
                c.create_text(wk_w / 2 + P(2), y0 + P(10), text=label,
                              font=f["bold"] if current_week else f["small"],
                              fill=theme.ACCENT if (sw or current_week) else theme.DIM)
            for col, day in enumerate(week):
                x0 = wk_w + P(4) + col * cw
                self._draw_cell(day, x0, y0, cw, rh, line_h, f, today, current_week)

        g = max(P(20), 16)
        c.create_polygon(W, H - g, W, H, W - g, H, fill=theme.MUTED, outline="", tags=("grip",))
        c.tag_bind("grip", "<Enter>", lambda e: c.config(cursor="size_nw_se"))
        c.tag_bind("grip", "<Leave>", lambda e: c.config(cursor=""))
        self._glow_steady = True
        if self.glow and not self._pulse_job:
            self._pulse_job = self.win.after(1000, self._pulse)

    def _draw_cell(self, day, x0, y0, cw, rh, line_h, f, today, current_week):
        c, P, s = self.canvas, self.px, self.app.settings
        x1, y1 = x0 + cw - P(2), y0 + rh - P(2)
        in_month = day.month == self.month
        is_today = day == today
        fill = self.app.store.data["date_colors"].get(day.isoformat())
        # On a user-coloured date, plain text switches to black/white to stay readable.
        plain = theme.readable_on(fill) if fill else theme.TEXT
        if not fill:
            fill = theme.BG
            if is_today and s["today_tint"]:
                fill = theme.mix(theme.ACCENT, theme.BG, 0.18)
            elif current_week:
                fill = theme.mix(theme.ACCENT, theme.BG, 0.07)
        c.create_rectangle(x0, y0, x1, y1, fill=fill, outline=theme.TODAY if is_today else theme.GRID,
                           width=P(2) if is_today else 1)
        self.hits.append((x0, y0, x1, y1, "cell", day, None))
        if is_today and s["today_glow"]:
            # Rings fading inward from the border; _pulse() animates their brightness.
            for i in range(1, GLOW_RINGS + 1):
                inset = P(1) + i
                strength = 1 - i / (GLOW_RINGS + 1)
                item = c.create_rectangle(x0 + inset, y0 + inset, x1 - inset, y1 - inset, width=1,
                                          outline=theme.mix(theme.ACCENT, fill, strength))
                self.glow.append((item, strength, fill))

        weekend = day.weekday() >= 5
        num_color = theme.DIM if not in_month else (theme.WEEKEND if weekend else plain)
        if plain != theme.TEXT:
            num_color = plain
        hol = holiday_name(day) if s["show_holidays"] else None
        if hol and in_month:
            num_color = theme.HOLIDAY
        if is_today and (s["today_tint"] or s["today_glow"]):
            num_color = theme.ACCENT
        num = c.create_text(x0 + P(6), y0 + P(4), text=str(day.day), anchor="nw",
                            fill=num_color, font=f["bold"])
        nb = c.bbox(num)
        self.hits.append((nb[0] - P(2), nb[1], nb[2] + P(2), nb[3], "day", day, None))
        label_right = x1 - P(3)
        if is_today and s["today_tint"]:
            badge = c.create_text(x1 - P(7), y0 + P(5), text="TODAY", anchor="ne", font=f["small"],
                                  fill=theme.readable_on(theme.ACCENT))
            bb = c.bbox(badge)
            pill = c.create_rectangle(bb[0] - P(4), bb[1] - P(1), bb[2] + P(4), bb[3] + P(1),
                                      fill=theme.ACCENT, width=0)
            c.tag_lower(pill, badge)
            label_right = bb[0] - P(8)
        if hol:
            c.create_text(nb[2] + P(5), y0 + P(5), anchor="nw", font=f["small"],
                          fill=theme.HOLIDAY if in_month else theme.DIM,
                          text=theme.fit(f["small"], hol, label_right - nb[2] - P(5)))

        bottom = y1 - P(2)
        if is_today and s["today_progress"]:
            now = datetime.now()
            frac = (now.hour * 60 + now.minute) / 1440
            by = y1 - P(5)
            c.create_line(x0 + P(6), by, x1 - P(6), by, fill=theme.mix(theme.ACCENT, fill, 0.25),
                          width=P(3), capstyle="round")
            c.create_line(x0 + P(6), by, x0 + P(6) + (x1 - x0 - P(12)) * frac, by, fill=theme.ACCENT,
                          width=P(3), capstyle="round")
            bottom = by - P(4)

        tasks = model.tasks_on(self.app.store.data["tasks"], day)
        y = nb[3] + P(2)
        room = int((bottom - y) // line_h)
        shown = tasks if len(tasks) <= room else tasks[:max(0, room - 1)]
        for t in shown:
            done = model.is_done(t, day)
            color = theme.DONE if done or not in_month else \
                (theme.ink(t["color"], fill) if t.get("color") else plain)
            box = c.create_text(x0 + P(6), y, text="☑" if done else "☐", anchor="nw",
                                fill=color, font=f["normal"])
            bb = c.bbox(box)
            self.hits.append((bb[0] - P(2), y, bb[2] + P(1), y + line_h, "check", day, t))
            label = (t["time"] + " " if t.get("time") else "") + t["title"]
            tx = bb[2] + P(3)
            ticked, total = model.progress(t, day)
            count = f"{ticked}/{total}" if total else ""
            count_w = f["small"].measure(" " + count) if count else 0
            title = c.create_text(tx, y, anchor="nw", fill=color, font=f["strike"] if done else f["normal"],
                                  text=theme.fit(f["normal"], label, x1 - tx - P(3) - count_w))
            if count:
                c.create_text(c.bbox(title)[2] + P(3), y + P(1), anchor="nw", text=count, font=f["small"],
                              fill=theme.DONE if done else (theme.ACCENT if ticked == total else theme.MUTED))
            self._task_items[(t["id"], day)] = (box, title)
            self.hits.append((tx, y, x1, y + line_h, "task", day, t))
            y += line_h
        hidden = len(tasks) - len(shown)
        if hidden > 0:
            item = c.create_text(x0 + P(6), y, anchor="nw", fill=theme.ACCENT, font=f["small"],
                                 text=f"+{hidden} more")
            bb = c.bbox(item)
            self.hits.append((bb[0], bb[1], bb[2], bb[3], "day", day, None))

    def to_front(self, focus=True):
        super().to_front(focus)
        if self.glow:  # start breathing now instead of at the next one-second check
            if self._pulse_job:
                self.win.after_cancel(self._pulse_job)
            self._pulse()

    def _pulse(self):
        """Breathe the glow around today, but only while someone can see it (calendar raised or the
        desktop in front). Otherwise draw it steady and look again in a second; with no glow, stop."""
        self._pulse_job = None
        if not self.glow or not self.win.winfo_exists():
            return
        if self.front or winapi.desktop_is_foreground():
            wave = 0.5 + 0.5 * math.sin(time.monotonic() * 2 * math.pi / 2.4)
            delay = 80
        else:
            wave, delay = 1.0, 1000
        if wave != 1.0 or not self._glow_steady:
            for item, strength, fill in self.glow:
                self.canvas.itemconfigure(item, outline=theme.mix(theme.ACCENT, fill, strength * (0.35 + 0.65 * wave)))
        self._glow_steady = wave == 1.0
        self._pulse_job = self.win.after(delay, self._pulse)

    def _button(self, item, action):
        c = self.canvas
        c.tag_bind(item, "<Button-1>", lambda e: action())
        c.tag_bind(item, "<Enter>", lambda e: c.config(cursor="hand2"))
        c.tag_bind(item, "<Leave>", lambda e: c.config(cursor=""))
        self.hits.append((*c.bbox(item), "button", None, None))

    # -- interaction -------------------------------------------------------
    def _hit(self, x, y):
        for h in reversed(self.hits):  # most specific (drawn last) first
            if h[0] <= x <= h[2] and h[1] <= y <= h[3]:
                return h
        return None

    def _click(self, e):
        h = self._hit(e.x, e.y)
        if not h:
            return
        kind, day, t = h[4:]
        if kind == "check":
            self._animate_tick(t, day)
        elif kind in ("task", "day"):
            # Wait briefly: if a double-click follows, it adds a task instead.
            action = (lambda: self.app.edit_task(task=t, day=day)) if kind == "task" else \
                     (lambda: self.app.open_day(day))
            self._cancel_click()
            self._click_job = self.win.after(CLICK_DELAY_MS, self._run_click, action)

    def _animate_tick(self, t, day):
        """Play the tick (or untick) animation, then save. Clicks on it meanwhile are ignored."""
        key = (t["id"], day)
        if key in self.animating:
            return
        ticking = not model.is_done(t, day)
        items = self._task_items.get(key)
        if not items:
            self.app.toggle_done(t, day, ticking)
            return
        self.animating.add(key)

        def finished():
            self.animating.discard(key)
            self.app.toggle_done(t, day, ticking)
        box = self.canvas.bbox(items[0])
        side = min(box[2] - box[0], box[3] - box[1]) - 2
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        TickAnimation(self.canvas, (cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2), items[1],
                      theme.ACCENT, theme.DONE, finished, ticking).start()

    def _run_click(self, action):
        self._click_job = None
        action()

    def _cancel_click(self):
        if self._click_job:
            self.win.after_cancel(self._click_job)
            self._click_job = None

    def _double(self, e):
        self._cancel_click()
        h = self._hit(e.x, e.y)
        if h and h[5] is not None and h[4] != "check":
            cell = next(x for x in self.hits if x[4] == "cell" and x[5] == h[5])
            self._quick_add(h[5], cell)

    def _quick_add(self, day, hit):
        """Inline box over the day; Enter saves, Esc cancels."""
        if self.quick:
            self.quick.destroy()
        x0, y0, x1, _ = hit[:4]
        f = theme.fonts(self.app.settings["font_size"] * self.zoom)
        e = tk.Entry(self.canvas, font=f["normal"], bg=theme.PANEL, fg=theme.TEXT,
                     insertbackground=theme.TEXT, relief="flat", highlightthickness=1,
                     highlightcolor=theme.ACCENT, highlightbackground=theme.ACCENT)
        self.quick = e
        self.canvas.create_window(x0 + self.px(3), y0 + self.px(24), anchor="nw", window=e,
                                  width=x1 - x0 - self.px(6))
        # Live preview of what smart typing understood ("Tomorrow · 19:00").
        preview = tk.Label(self.canvas, font=f["small"], bg=theme.PANEL, fg=theme.ACCENT, anchor="w")
        self.canvas.create_window(x0 + self.px(3), y0 + self.px(24) + e.winfo_reqheight(), anchor="nw",
                                  window=preview, width=x1 - x0 - self.px(6))
        e.bind("<KeyRelease>", lambda ev: preview.configure(
            text=" · ".join(model.parse_quick(e.get(), day)["found"]) if e.get().strip() else ""))
        self.to_front()
        e.focus_set()

        def done(save):
            if self.quick is not e:
                return
            text = e.get().strip()
            self.quick = None
            e.destroy()
            preview.destroy()
            if save and text:
                self.app.add_task(model.task_from_quick(model.parse_quick(text, day)))
            else:
                self.redraw()

        e.bind("<Return>", lambda ev: done(True))
        e.bind("<Escape>", lambda ev: done(False))
        e.bind("<FocusOut>", lambda ev: done(True))

    def _context(self, e):
        h = self._hit(e.x, e.y)
        if not h or h[5] is None:
            return
        day, t = h[5], h[6]
        m = tk.Menu(self.win, tearoff=0)
        if t:
            done = model.is_done(t, day)
            m.add_command(label="Edit task…", command=lambda: self.app.edit_task(task=t, day=day))
            m.add_command(label="Mark not done" if done else "Mark done",
                          command=lambda: self.app.toggle_done(t, day))
            if t.get("repeat", "none") == "none":
                m.add_command(label="Move to next day", command=lambda: self.app.move_task(t, day + timedelta(1)))
                m.add_command(label="Delete task", command=lambda: self.app.delete_task(t, day, whole=True))
            else:
                m.add_command(label="Delete this day only", command=lambda: self.app.delete_task(t, day, whole=False))
                m.add_command(label="Delete all repeats", command=lambda: self.app.delete_task(t, day, whole=True))
            m.add_separator()
        m.add_command(label="Add task…", command=lambda: self.app.edit_task(day=day))
        m.add_command(label="Open day…", command=lambda: self.app.open_day(day))
        colors = tk.Menu(m, tearoff=0)
        for col in theme.DATE_COLORS:
            colors.add_command(label="      ", background=col, activebackground=col,
                               command=lambda col=col: self.app.set_date_color(day, col))
        colors.add_command(label="Custom…", command=lambda: self.app.set_date_color(day, "custom"))
        colors.add_command(label="Clear", command=lambda: self.app.set_date_color(day, None))
        m.add_cascade(label="Date colour", menu=colors)
        m.add_command(label="Countdown to this date…", command=lambda: self.app.edit_countdown(day=day))
        m.tk_popup(e.x_root, e.y_root)

    def _main_menu(self):
        self.app.main_menu(self.win)
