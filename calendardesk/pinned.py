"""Borderless window that lives on the desktop wallpaper, with drag-to-move and drag-to-resize."""
import tkinter as tk

from . import winapi


class PinnedWindow:
    def __init__(self, app, geometry, alpha=None, bg="#000000", min_size=(120, 80)):
        self.app = app
        self.min_size = min_size
        self.win = tk.Toplevel(app.root, bg=bg)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.geometry(geometry)
        if alpha is not None:
            self.win.attributes("-alpha", alpha)
        self.win.deiconify()
        self.win.update_idletasks()
        self.hwnd = winapi.hwnd_of(self.win)
        winapi.pin_to_desktop(self.hwnd)
        # True while raised above other apps; the app drops it back once another app is in front.
        self.front = False
        self._drag = None

    # -- z-order ---------------------------------------------------------
    def to_front(self, focus=True):
        self.win.deiconify()
        if focus:
            winapi.bring_to_front(self.hwnd)
            self.win.focus_force()
        else:
            winapi.raise_window(self.hwnd)
        self.front = True

    def to_back(self):
        winapi.send_to_bottom(self.hwnd)
        self.front = False

    # -- move / resize ---------------------------------------------------
    def make_draggable(self, widget, on_done=None, locked=lambda: False, tag=None):
        def press(e):
            if self._drag and self._drag[0] == "size":
                return  # the resize grip under the pointer already took this press
            if locked():
                self._drag = None
                return
            self._drag = ("move", e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y())

        def motion(e):
            if self._drag and self._drag[0] == "move":
                self.win.geometry(f"+{e.x_root - self._drag[1]}+{e.y_root - self._drag[2]}")

        self._bind_drag(widget, tag, press, motion, on_done)

    def make_resizable(self, widget, on_done=None, locked=lambda: False, tag=None):
        def press(e):
            if locked():
                self._drag = None
                return
            self._drag = ("size", e.x_root, e.y_root, self.win.winfo_width(), self.win.winfo_height())

        def motion(e):
            if self._drag and self._drag[0] == "size":
                _, x0, y0, w0, h0 = self._drag
                w = max(self.min_size[0], w0 + e.x_root - x0)
                h = max(self.min_size[1], h0 + e.y_root - y0)
                self.win.geometry(f"{w}x{h}")

        self._bind_drag(widget, tag, press, motion, on_done)

    def _bind_drag(self, widget, tag, press, motion, on_done):
        def release(e):
            was = self._drag
            self._drag = None
            if was and on_done:
                on_done()

        # Only the press needs the tag. Motion and release go on the whole widget: a canvas redraw
        # during the drag replaces the tagged item, which would otherwise cut the drag short.
        if tag:
            widget.tag_bind(tag, "<ButtonPress-1>", press, add="+")
        else:
            widget.bind("<ButtonPress-1>", press, add="+")
        widget.bind("<B1-Motion>", motion, add="+")
        widget.bind("<ButtonRelease-1>", release, add="+")

    def set_size(self, w, h):
        """Resize, keeping the window on screen (it moves left/up if it would overflow)."""
        l, t, r, b = winapi.work_area()
        w, h = min(max(self.min_size[0], int(w)), r - l), min(max(self.min_size[1], int(h)), b - t)
        x = min(max(l, self.win.winfo_x()), r - w)
        y = min(max(t, self.win.winfo_y()), b - h)
        self.win.geometry(f"{w}x{h}+{x}+{y}")

    def geometry(self):
        return f"{self.win.winfo_width()}x{self.win.winfo_height()}+{self.win.winfo_x()}+{self.win.winfo_y()}"

    def destroy(self):
        self.win.destroy()
