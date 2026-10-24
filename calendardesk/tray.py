"""Notification-area icon. Runs on its own thread; every action is posted to the app queue."""
import threading

import pystray
from PIL import Image, ImageDraw


def make_icon_image(size=64):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((4, 8, size - 4, size - 4), radius=10, fill=(35, 38, 46, 255), outline=(77, 171, 247, 255), width=4)
    d.rectangle((4, 8, size - 4, 24), fill=(77, 171, 247, 255))
    for i in range(3):
        for j in range(3):
            x, y = 14 + i * 14, 30 + j * 9
            d.rectangle((x, y, x + 8, y + 5), fill=(236, 239, 244, 255))
    return img


class Tray:
    def __init__(self, post):
        """`post(action_name)` is called from the tray thread."""
        item = pystray.MenuItem
        p = lambda name: (lambda icon, it: post(name))
        menu = pystray.Menu(
            item("Show / edit calendar", p("toggle_front"), default=True),
            item("Mini calendar", p("toggle_mini")),
            pystray.Menu.SEPARATOR,
            item("New task", p("new_task")),
            item("New note", p("new_note")),
            item("New countdown", p("new_countdown")),
            item("Show all notes and cards", p("show_all")),
            pystray.Menu.SEPARATOR,
            item("Countdowns…", p("countdowns")),
            item("Search…", p("search")),
            item("Export to Excel…", p("export")),
            item("Settings…", p("settings")),
            item("Undo last settings change", p("undo_settings")),
            pystray.Menu.SEPARATOR,
            item("Exit", p("quit")),
        )
        self.icon = pystray.Icon("CalendarDesk", make_icon_image(), "CalendarDesk", menu)

    def start(self):
        threading.Thread(target=self.icon.run, daemon=True).start()

    def stop(self):
        self.icon.stop()
