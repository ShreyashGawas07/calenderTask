"""Short, self-stopping tick animation for a task checkbox drawn on a canvas.

Ticking (~350 ms): the box fills with the accent from its centre, a check mark draws itself, then a
line sweeps through the task text while the text fades to the "done" colour. Unticking is a quick
120 ms fade. Only the animation's own items are touched each frame; it then removes them and calls
`on_done` exactly once.
"""
import tkinter as tk

from . import theme

FRAME_MS = 16
TICK_MS, UNTICK_MS = 350, 120
TAG = "tickanim"


def _hex(widget, color):
    """Any Tk colour name ('black', 'SystemButtonFace', '#abc') as #rrggbb, for theme.mix."""
    r, g, b = widget.winfo_rgb(color)
    return f"#{r >> 8:02x}{g >> 8:02x}{b >> 8:02x}"


def _phase(t, start, end):
    """0..1 progress of a phase running from `start` to `end` ms."""
    return min(1.0, max(0.0, (t - start) / (end - start)))


class TickAnimation:
    def __init__(self, canvas, box_bbox, text_item, accent, done_color, on_done, ticking=True):
        self.c = canvas
        self.box = box_bbox
        self.text_item = text_item
        self.accent = accent
        self.done_color = done_color
        self.on_done = on_done
        self.ticking = ticking
        self.duration = TICK_MS if ticking else UNTICK_MS
        self.running = False
        self._job = None
        self._frame = 0
        self._items = {}
        # Frames run on the root: a destroyed canvas would silently drop its own timers (and on_done).
        self._root = canvas._root()
        self.tag = f"{TAG}{id(self)}"  # so several animations on one canvas clean up only their own items
        try:
            self._text_color = _hex(canvas, canvas.itemcget(text_item, "fill")) if text_item else None
            self._bg = _hex(canvas, canvas.cget("bg"))
        except tk.TclError:
            self._text_color, self._bg = None, "#000000"

    def start(self):
        self.running = True
        try:
            self._create_items()
        except tk.TclError:  # the canvas is already gone: finish at once so on_done still runs
            self._finish()
            return
        self._step()

    def _create_items(self):
        x0, y0, x1, y1 = self.box
        c = self.c
        self._items["fill"] = c.create_rectangle(x0, y0, x1, y1, fill=self.accent, width=0, tags=(TAG, self.tag))
        self._items["check"] = c.create_line(x0, y0, x0, y0, fill=theme.readable_on(self.accent),
                                             width=max(2, (x1 - x0) // 7), capstyle="round",
                                             joinstyle="round", tags=(TAG, self.tag), state="hidden")
        tb = c.bbox(self.text_item) if self.text_item else None
        if tb and self.ticking:
            mid = (tb[1] + tb[3]) / 2
            self._items["strike"] = c.create_line(tb[0], mid, tb[0], mid, fill=self.done_color, width=1,
                                                  tags=(TAG, self.tag), state="hidden")
            self._text_box = tb

    def _step(self):
        self._job = None
        try:
            self._draw(min(self.duration, self._frame * FRAME_MS))
        except tk.TclError:  # the canvas went away (window closed); just finish
            self._finish()
            return
        if self._frame * FRAME_MS >= self.duration:
            self._finish()
            return
        self._frame += 1
        self._job = self._root.after(FRAME_MS, self._step)

    def _draw(self, t):
        c, (x0, y0, x1, y1) = self.c, self.box
        cx, cy, w, h = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
        if not self.ticking:
            fade = _phase(t, 0, UNTICK_MS)
            c.itemconfigure(self._items["fill"], fill=theme.mix(self._bg, self.accent, fade))
            return
        # 1. box fills from the centre (0-120 ms)
        s = 0.6 + 0.4 * _phase(t, 0, 120)
        c.coords(self._items["fill"], cx - w * s / 2, cy - h * s / 2, cx + w * s / 2, cy + h * s / 2)
        # 2. check mark draws itself in two strokes (80-240 ms)
        k = _phase(t, 80, 240)
        if k > 0:
            p1, p2, p3 = (x0 + w * .22, y0 + h * .52), (x0 + w * .42, y0 + h * .74), (x0 + w * .80, y0 + h * .28)
            if k < 0.4:
                f = k / 0.4
                pts = [*p1, p1[0] + (p2[0] - p1[0]) * f, p1[1] + (p2[1] - p1[1]) * f]
            else:
                f = (k - 0.4) / 0.6
                pts = [*p1, *p2, p2[0] + (p3[0] - p2[0]) * f, p2[1] + (p3[1] - p2[1]) * f]
            c.coords(self._items["check"], *pts)
            c.itemconfigure(self._items["check"], state="normal")
        # 3. strike sweeps through the text while it fades to the done colour (120-350 ms)
        sweep = _phase(t, 120, TICK_MS)
        if sweep > 0 and "strike" in self._items:
            tb = self._text_box
            mid = (tb[1] + tb[3]) / 2
            c.coords(self._items["strike"], tb[0], mid, tb[0] + (tb[2] - tb[0]) * sweep, mid)
            c.itemconfigure(self._items["strike"], state="normal")
            if self._text_color:
                c.itemconfigure(self.text_item, fill=theme.mix(self.done_color, self._text_color, sweep))

    def _finish(self):
        if not self.running:
            return
        self.running = False
        if self._job:
            try:
                self._root.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        try:
            self.c.delete(self.tag)
        except tk.TclError:
            pass
        self.on_done()

    def cancel(self):
        """Stop without calling on_done (e.g. the view is being rebuilt)."""
        self.on_done = lambda: None
        self._finish()
