"""Picture and video backgrounds behind the calendar (backdrop.py, Settings → Appearance)."""
import os
import tempfile
import time
import unittest
from datetime import date
from unittest import mock

from PIL import Image

from calendardesk import media, model, winapi
from calendardesk.backdrop import KEY
from calendardesk.store import Store
from tests.test_media import make_mp4


def pump(root, ms=60):
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        root.update()
        time.sleep(0.005)


class BackgroundTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(tempfile.mkdtemp(prefix="cd-test-"))
        self.store.settings["hotkey"] = "K"  # leave Ctrl+Alt+C to a running CalendarDesk
        self.store.settings["calendar_geometry"] = "700x500+40+40"
        self.folder = os.path.join(self.store.folder, "backgrounds")
        self.app = None

    def tearDown(self):
        if self.app:
            self.app.quit()
        log = os.path.join(self.store.folder, "error.log")
        self.assertFalse(os.path.exists(log), open(log).read() if os.path.exists(log) else "")

    def picture(self, size=(400, 300)):
        src = os.path.join(self.store.folder, "pic.png")
        Image.new("RGB", size, (200, 120, 40)).save(src)
        return src

    def start(self, record=None, **settings):
        from calendardesk.app import App
        self.store.settings["background"] = record
        self.store.settings.update(settings)
        self.app = App(self.store, tray=False)
        pump(self.app.root, 150)
        return self.app.calendar

    def test_picture_shows_through_see_through_cells(self):
        cal = self.start(media.import_media(self.picture(), self.folder, (700, 500)))
        b = cal.backdrop
        self.assertIsNotNone(b)
        self.assertEqual(cal.canvas["bg"], KEY)
        self.assertEqual(str(cal.win.attributes("-transparentcolor")), KEY)
        self.assertEqual(b.media.winfo_geometry(), cal.win.winfo_geometry())
        self.assertEqual(b._photo.width(), cal.win.winfo_width())
        self.assertAlmostEqual(float(b.media.attributes("-alpha")), 0.65, places=2)
        cells = [i for i in cal.canvas.find_all() if cal.canvas.type(i) == "rectangle"
                 and cal.canvas.coords(i)[1] > cal.px(40) and cal.canvas.itemcget(i, "fill")
                 and cal.canvas.coords(i)[3] - cal.canvas.coords(i)[1] > cal.px(30)]  # not the small TODAY pill
        self.assertEqual(cells, [])  # no cell is filled, so the picture shows

    def test_every_calendar_text_gets_a_shadow_and_the_percent_keeps_its_shadow(self):
        today = date.today()
        self.store.data["tasks"].append(model.new_task("call mom", today))
        cal = self.start(media.import_media(self.picture(), self.folder, (700, 500)))
        c = cal.canvas
        pct = c.find_withtag("progress_pct")[0]
        self.assertIn(pct, cal._shadows)
        c.itemconfigure(cal._shadows[pct], text="")
        cal.update_progress()
        self.assertEqual(c.itemcget(cal._shadows[pct], "text"), c.itemcget(pct, "text"))
        shadow, title = [i for i in c.find_all() if c.type(i) == "text" and c.itemcget(i, "text") == "call mom"]
        self.assertEqual(cal._shadows[title], shadow)
        self.assertLess(c.find_all().index(shadow), c.find_all().index(title))  # drawn underneath

    def test_date_colour_becomes_a_band(self):
        day = date.today().replace(day=12)
        self.store.data["date_colors"][day.isoformat()] = "#2f5530"
        cal = self.start(media.import_media(self.picture(), self.folder, (700, 500)))
        cell = next(h for h in cal.hits if h[4] == "cell" and h[5] == day)
        bands = [i for i in cal.canvas.find_overlapping(*cell[:4]) if cal.canvas.itemcget(i, "fill") == "#2f5530"]
        self.assertEqual(len(bands), 1)
        x0, y0, x1, y1 = cal.canvas.coords(bands[0])
        self.assertLess(y1 - y0, (cell[3] - cell[1]) / 2)

    def test_clicks_on_the_picture_reach_the_calendar(self):
        cal = self.start(media.import_media(self.picture(), self.folder, (700, 500)))
        cell = next(h for h in cal.hits if h[4] == "cell" and h[5] == date.today().replace(day=15))
        x, y = int((cell[0] + cell[2]) / 2), int(cell[3] - 5)
        for _ in range(2):
            cal.backdrop.host.event_generate("<ButtonPress-1>", x=x, y=y)
            cal.backdrop.host.event_generate("<ButtonRelease-1>", x=x, y=y)
        pump(self.app.root)
        self.assertIsNotNone(cal.quick)  # double-click: quick add on that day
        cal.backdrop.host.event_generate("<ButtonPress-1>", x=5, y=cal.win.winfo_height() - 30)
        pump(self.app.root)
        self.assertIsNone(cal.quick)  # a single click elsewhere closes it

    def test_missing_file_falls_back_to_the_plain_calendar(self):
        cal = self.start({"kind": "image", "name": "x.png", "file": "bg-gone.png", "poster": None,
                          "source_w": 10, "source_h": 10, "w": 10, "h": 10, "enhanced": False})
        self.assertIsNone(cal.backdrop)
        self.assertNotEqual(cal.canvas["bg"], KEY)

    def test_startup_deletes_unused_background_files(self):
        record = media.import_media(self.picture(), self.folder, (700, 500))
        open(os.path.join(self.folder, "bg-old.mp4"), "w").close()
        self.start(record)
        self.assertEqual(sorted(os.listdir(self.folder)), [record["file"]])

    def test_video_plays_only_while_seen(self):
        src = os.path.join(self.store.folder, "v.mp4")
        make_mp4(src, size=(640, 360))
        cal = self.start(media.import_media(src, self.folder, (640, 360)))
        b = cal.backdrop
        self.assertIsNotNone(b.player)
        with mock.patch.object(winapi, "foreground_is_ours", return_value=False), \
                mock.patch.object(winapi, "desktop_is_foreground", return_value=False):
            cal.front = False
            b.update_play()
            self.assertFalse(b.player.playing)
            cal.front = True
            b.update_play()
            self.assertTrue(b.player.playing)
            cal.front = False
            b.update_play()
            self.assertFalse(b.player.playing)

    def test_never_play_shows_the_first_frame(self):
        src = os.path.join(self.store.folder, "v.mp4")
        make_mp4(src, size=(640, 360))
        cal = self.start(media.import_media(src, self.folder, (640, 360)), background_play="never")
        self.assertIsNone(cal.backdrop.player)
        self.assertIsNotNone(cal.backdrop._photo)

    def test_settings_choose_preview_cancel_and_save(self):
        from calendardesk.dialogs import SettingsDialog
        cal = self.start()
        src = self.picture((200, 150))
        d = SettingsDialog(self.app)
        with mock.patch("calendardesk.dialogs.filedialog.askopenfilename", return_value=src):
            d._choose_background()
        end = time.monotonic() + 10
        while d._import and time.monotonic() < end:
            pump(self.app.root, 50)
        pump(self.app.root, 300)
        self.assertIsNotNone(cal.backdrop)  # previewed live
        self.assertIn("Upscayl", d.bg_info["text"])  # 200×150 on a 700×500 calendar: advice to upscale
        d.close()
        pump(self.app.root, 100)
        self.assertIsNone(cal.backdrop)  # Cancel puts the plain calendar back
        self.assertEqual(str(cal.win.attributes("-transparentcolor")), "")

        d = SettingsDialog(self.app)
        with mock.patch("calendardesk.dialogs.filedialog.askopenfilename", return_value=src):
            d._choose_background()
        while d._import and time.monotonic() < end + 10:
            pump(self.app.root, 50)
        d.vars["background_dim"].set(0.5)
        d.save()
        pump(self.app.root, 100)
        self.assertEqual(self.store.settings["background"]["name"], "pic.png")
        self.assertEqual(self.store.settings["background_dim"], 0.5)
        self.assertAlmostEqual(float(cal.backdrop.media.attributes("-alpha")), 0.5, places=2)

        d = SettingsDialog(self.app)
        d._remove_background()
        d.save()
        pump(self.app.root, 100)
        self.assertIsNone(cal.backdrop)
        self.assertIsNone(self.store.settings["background"])

    def test_settings_shows_import_errors(self):
        from calendardesk.dialogs import SettingsDialog
        self.start()
        bad = os.path.join(self.store.folder, "x.mp4")
        with open(bad, "wb") as f:
            f.write(b"not a video")
        d = SettingsDialog(self.app)
        with mock.patch("calendardesk.dialogs.filedialog.askopenfilename", return_value=bad), \
                mock.patch("calendardesk.dialogs.messagebox.showerror") as shown:
            d._choose_background()
            end = time.monotonic() + 10
            while d._import and time.monotonic() < end:
                pump(self.app.root, 50)
        shown.assert_called_once()
        self.assertIsNone(d.background)
        d.close()


if __name__ == "__main__":
    unittest.main()
