import os
import tempfile
import unittest

from PIL import Image

from calendardesk import media
from calendardesk.videoplayer import cover_rect


def make_gif(path, frames=3, ms=(100, 200, 300), size=(64, 48)):
    ims = [Image.new("RGB", size, c) for c in ((255, 0, 0), (0, 255, 0), (0, 0, 255))[:frames]]
    ims[0].save(path, save_all=True, append_images=ims[1:], duration=list(ms[:frames]), loop=0)


def make_mp4(path, size=(320, 180), frames=30, rate=30):
    import av
    with av.open(path, "w") as out:
        s = out.add_stream("libx264", rate=rate)
        s.width, s.height = size
        s.pix_fmt = "yuv420p"
        for i in range(frames):
            f = av.VideoFrame.from_image(Image.new("RGB", size, (i * 8 % 256, 80, 160)))
            f.pts = i
            out.mux(s.encode(f))
        out.mux(s.encode(None))


def count_frames(path):
    import av
    with av.open(path) as c:
        s = c.streams.video[0]
        return sum(1 for _ in c.decode(s)), (s.width, s.height), float(s.average_rate)


class GeometryTests(unittest.TestCase):
    def test_cover_rect_crops_the_overflow(self):
        self.assertEqual(cover_rect(1920, 1080, 1920, 1080), (0.0, 0.0, 1.0, 1.0))
        l, t, r, b = cover_rect(1600, 900, 900, 900)  # wide video, square window: crop the sides
        self.assertAlmostEqual(r - l, 900 / 1600)
        self.assertEqual((t, b), (0.0, 1.0))
        l, t, r, b = cover_rect(900, 900, 1600, 900)  # square video, wide window: crop top and bottom
        self.assertAlmostEqual(b - t, 900 / 1600)
        self.assertEqual(cover_rect(0, 0, 10, 10), (0.0, 0.0, 1.0, 1.0))

    def test_cover_size(self):
        self.assertEqual(media.cover_size(736, 414, (1500, 900)), (1600, 900))
        self.assertEqual(media.cover_size(4000, 3000, (1500, 900)), (4000, 3000))  # never shrinks
        w, h = media.cover_size(100, 100, (5000, 5000))
        self.assertLessEqual((w, h), (3840, 3840))
        self.assertTrue(w % 2 == 0 and h % 2 == 0)

    def test_soft(self):
        self.assertTrue(media.is_soft(736, 414, (1500, 900)))
        self.assertFalse(media.is_soft(1920, 1080, (1500, 900)))
        self.assertFalse(media.is_soft(1450, 870, (1500, 900)))  # 3 % enlargement is fine


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="cd-test-")
        self.out = os.path.join(self.dir, "backgrounds")

    def test_picture_is_copied_as_png(self):
        src = os.path.join(self.dir, "p.jpg")
        Image.new("RGB", (400, 300), "orange").save(src)
        r = media.import_media(src, self.out, (800, 600))
        self.assertEqual((r["kind"], r["w"], r["h"], r["name"]), ("image", 400, 300, "p.jpg"))
        self.assertTrue(r["file"].endswith(".png"))
        self.assertTrue(os.path.exists(os.path.join(self.out, r["file"])))
        self.assertIn("Upscayl", media.advice(r, (800, 600)))
        self.assertEqual(media.advice(r, (380, 280)), "")

    def test_huge_picture_is_kept_at_most_4k(self):
        src = os.path.join(self.dir, "big.png")
        Image.new("RGB", (8000, 2000), "orange").save(src)
        r = media.import_media(src, self.out, (800, 600))
        self.assertEqual((r["w"], r["h"], r["source_w"]), (3840, 960, 8000))
        with Image.open(os.path.join(self.out, r["file"])) as im:
            self.assertEqual(im.size, (3840, 960))

    def test_transparent_picture_goes_black_not_white(self):
        src = os.path.join(self.dir, "t.png")
        Image.new("RGBA", (10, 10), (255, 255, 255, 0)).save(src)
        r = media.import_media(src, self.out, (10, 10))
        with Image.open(os.path.join(self.out, r["file"])) as im:
            self.assertEqual(im.getpixel((5, 5)), (0, 0, 0))

    def test_gif_becomes_mp4_with_its_timing(self):
        src = os.path.join(self.dir, "a.gif")
        make_gif(src)
        r = media.import_media(src, self.out, (64, 48))
        self.assertEqual(r["kind"], "video")
        self.assertTrue(r["file"].endswith(".mp4"))
        n, size, rate = count_frames(os.path.join(self.out, r["file"]))
        self.assertEqual(size, (64, 48))
        self.assertAlmostEqual(n / rate, 0.6, delta=0.05)  # 100 + 200 + 300 ms
        self.assertTrue(os.path.exists(os.path.join(self.out, r["poster"])))

    def test_small_gif_is_upscaled_and_sharpened(self):
        src = os.path.join(self.dir, "a.gif")
        make_gif(src)
        r = media.import_media(src, self.out, (640, 480))
        self.assertTrue(r["enhanced"])
        self.assertEqual((r["w"], r["h"]), (640, 480))
        self.assertEqual(count_frames(os.path.join(self.out, r["file"]))[1], (640, 480))

    def test_big_mp4_is_copied_as_is(self):
        src = os.path.join(self.dir, "v.mp4")
        make_mp4(src)
        r = media.import_media(src, self.out, (300, 160))
        self.assertFalse(r["enhanced"])
        with open(src, "rb") as a, open(os.path.join(self.out, r["file"]), "rb") as b:
            self.assertEqual(a.read(), b.read())
        self.assertTrue(os.path.exists(os.path.join(self.out, r["poster"])))
        self.assertEqual(media.advice(r, (300, 160)), "")

    def test_small_mp4_gets_a_sharper_copy(self):
        src = os.path.join(self.dir, "v.mp4")
        make_mp4(src)
        r = media.import_media(src, self.out, (640, 360))
        self.assertTrue(r["enhanced"])
        n, size, rate = count_frames(os.path.join(self.out, r["file"]))
        self.assertEqual((n, size, rate), (30, (640, 360), 30.0))
        self.assertIn("Video2X", media.advice(r, (640, 360)))

    def test_without_enhancing_small_mp4_is_copied(self):
        src = os.path.join(self.dir, "v.mp4")
        make_mp4(src)
        self.assertFalse(media.import_media(src, self.out, (640, 360), enhance=False)["enhanced"])

    def test_unsupported_and_broken_files(self):
        bad = os.path.join(self.dir, "x.txt")
        open(bad, "w").close()
        with self.assertRaises(ValueError):
            media.import_media(bad, self.out, (100, 100))
        broken = os.path.join(self.dir, "x.mp4")
        with open(broken, "wb") as f:
            f.write(b"not a video")
        with self.assertRaises(ValueError):
            media.import_media(broken, self.out, (100, 100))
        self.assertEqual(os.listdir(self.out) if os.path.isdir(self.out) else [], [])

    def test_render_still_fills_the_size(self):
        src = os.path.join(self.dir, "p.png")
        Image.new("RGB", (100, 50), "white").save(src)
        self.assertEqual(media.render_still(src, (300, 300)).size, (300, 300))

    def test_prune_keeps_only_what_is_used(self):
        os.makedirs(self.out)
        for name in ("bg-a.png", "bg-b.mp4", "bg-b-poster.png", "other.txt"):
            open(os.path.join(self.out, name), "w").close()
        media.prune(self.out, {"bg-b.mp4", "bg-b-poster.png"})
        self.assertEqual(sorted(os.listdir(self.out)), ["bg-b-poster.png", "bg-b.mp4", "other.txt"])
