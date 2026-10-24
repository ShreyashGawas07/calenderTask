"""A picture, GIF or video behind the calendar.

Two borderless windows sit directly under the calendar on the wallpaper, always its size and place:
`base` is the theme colour (at the calendar's opacity), and `media` above it shows the picture or video,
let through by the dim amount so the theme colour darkens it and the calendar's text stays readable.
The calendar draws its empty parts in KEY, a colour Windows leaves out of the window, so the media shows
through. Those see-through pixels also pass clicks down to `media`, which hands them back to the calendar.

Videos are played by Windows (videoplayer.py), and only while someone can see them.
"""
import os
import tkinter as tk

from . import theme, winapi

KEY = "#010203"  # never used as a real colour anywhere in the app
PLAY_MODES = {"visible": "When the desktop or the calendar is in front",
              "front": "Only while the calendar is raised (shortcut or tray)",
              "never": "Never (show a still picture)"}
STILL_DELAY_MS = 150  # re-scale a picture only once a resize pauses


class Backdrop:
    def __init__(self, cal, record, folder):
        self.cal, self.record = cal, record
        self.path = os.path.join(folder, record["file"])
        self.poster = os.path.join(folder, record["poster"]) if record.get("poster") else None
        self.mode = "visible"
        self.player = None
        self.host = None
        self._photo = None
        self._size = None
        self._still_job = None
        self.base, self.base_hwnd = self._window(theme.BG)
        self.media, self.media_hwnd = self._window("#000000")
        self._configure_id = cal.win.bind("<Configure>", self._moved, add="+")
        self._show()

    def _window(self, bg):
        w = tk.Toplevel(self.cal.app.root, bg=bg)
        w.withdraw()
        w.overrideredirect(True)
        w.geometry(self.cal.geometry())
        w.deiconify()
        w.update_idletasks()
        hwnd = winapi.hwnd_of(w)
        winapi.pin_to_desktop(hwnd)
        winapi.never_activate(hwnd)
        return w, hwnd

    # -- what is shown -------------------------------------------------------
    def _show(self):
        """Play the video, or show the picture (a video's first frame when it is not played)."""
        if self.host:
            self.host.destroy()
        self.host, self._photo, self._size = None, None, None
        if self.player:
            self.player.close()
            self.player = None
        if self.record["kind"] == "video" and self.mode != "never":
            self.host = tk.Frame(self.media, bg="#000000")
            self._place_host()
            try:
                from .videoplayer import VideoPlayer
                self.player = VideoPlayer(self.host.winfo_id(), self.path,
                                          on_error=lambda hr: self.cal.win.after(0, self._video_failed))
            except OSError:
                self._video_failed()
                return
        else:
            self.host = tk.Label(self.media, bg="#000000", bd=0, highlightthickness=0)
            self._place_host()
            self._still()
        self.restack()
        self.update_play()

    def _place_host(self):
        self.host.place(x=0, y=0, relwidth=1, relheight=1)
        self.media.update_idletasks()
        c = self.cal
        for widget in (self.host, self.media):
            widget.bind("<Button-1>", c._click)
            widget.bind("<Double-Button-1>", c._double)
            widget.bind("<Button-3>", c._context)
            widget.bind("<MouseWheel>", lambda e: c.go(-1 if e.delta > 0 else 1))

    def _video_failed(self):
        """Windows could not play it: show its first frame instead."""
        if self.player:
            self.player.close()
            self.player = None
        self.record = dict(self.record, kind="image", file=None)
        self.path = self.poster
        self._show()

    def _still(self):
        self._still_job = None
        if not isinstance(self.host, tk.Label):
            return
        size = (self.media.winfo_width(), self.media.winfo_height())
        path = self.path if self.record["kind"] == "image" else self.poster
        if size == self._size or min(size) < 2 or not path or not os.path.exists(path):
            return
        from PIL import ImageTk
        from .media import render_still
        self._size = size
        self._photo = ImageTk.PhotoImage(render_still(path, size), master=self.media)
        self.host.configure(image=self._photo)

    # -- follow the calendar -------------------------------------------------
    def _moved(self, e):
        if e.widget is self.cal.win:
            self.sync()

    def sync(self):
        g = self.cal.geometry()
        for w in (self.base, self.media):
            if w.winfo_exists():
                w.geometry(g)
        if self.player:
            self.media.update_idletasks()
            self.player.fit()
        elif self._still_job is None:
            self._still_job = self.media.after(0 if self._size is None else STILL_DELAY_MS, self._still)

    def restack(self):
        """Keep media and then base directly under the calendar, wherever it is in the z-order."""
        winapi.place_below(self.media_hwnd, self.cal.hwnd)
        winapi.place_below(self.base_hwnd, self.media_hwnd)

    def set_look(self, opacity, dim):
        self.base.configure(bg=theme.BG)
        self.base.attributes("-alpha", opacity)
        self.media.attributes("-alpha", max(0.0, min(1.0, 1 - dim)))

    def set_mode(self, mode):
        mode = mode if mode in PLAY_MODES else "visible"
        if mode != self.mode:
            replay = self.record["kind"] == "video" and "never" in (mode, self.mode)
            self.mode = mode
            if replay:
                self._show()
        self.update_play()

    def update_play(self):
        """Play only while it can be seen; a paused video costs nothing."""
        if not self.player:
            return
        cal = self.cal
        seen = cal.front or (self.mode == "visible" and
                             (winapi.desktop_is_foreground() or winapi.foreground_is_ours()))
        if seen and not self.player.playing:
            self.player.play()
        elif not seen and self.player.playing:
            self.player.pause()

    def destroy(self):
        if self._still_job:
            self.media.after_cancel(self._still_job)
            self._still_job = None
        if self.player:
            self.player.close()
            self.player = None
        self.cal.win.unbind("<Configure>", self._configure_id)
        for w in (self.media, self.base):
            if w.winfo_exists():
                w.destroy()
