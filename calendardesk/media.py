"""Background pictures and videos: checking, one-time conversion and sharpening, stills, quality advice.

Everything slow happens once, when a file is chosen: it is copied (or converted) into the data folder,
so the calendar never depends on the original file and never re-processes it while running.
- Pictures (PNG, JPG, WebP, BMP, TIFF) are kept as a PNG and scaled to the calendar when drawn.
- MP4 / M4V / MOV / WMV are played as they are by Windows' video player.
- GIF, animated WebP, WebM, MKV, AVI are converted to H.264 MP4 (PyAV), so Windows can play them in
  hardware; small videos and GIFs are also upscaled (Lanczos) and sharpened while converting.
"""
import os
import shutil
import uuid
from fractions import Fraction

from PIL import Image, ImageFilter, ImageOps

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}
PLAYABLE_EXT = {".mp4", ".m4v", ".mov", ".wmv"}
CONVERT_EXT = {".gif", ".webm", ".mkv", ".avi", ".flv", ".apng"}
SUPPORTED = IMAGE_EXT | PLAYABLE_EXT | CONVERT_EXT
FILETYPES = [("Pictures, GIFs and videos", " ".join("*" + e for e in sorted(SUPPORTED))),
             ("Pictures", " ".join("*" + e for e in sorted(IMAGE_EXT))),
             ("GIFs and videos", " ".join("*" + e for e in sorted(PLAYABLE_EXT | CONVERT_EXT)))]
MAX_SIZE = (3840, 2160)      # never make a copy bigger than 4K
ENHANCE_MAX_SECONDS = 120    # longer clips are played as they are: converting would take minutes
SOFT = 0.9                   # source smaller than this share of the calendar looks soft
PREFIX = "bg-"


def probe(path):
    """{'kind': 'image'|'video', 'w', 'h', 'seconds'} or raises ValueError for files it can't use."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED:
        raise ValueError(f"{ext or 'This file type'} is not supported. Use a picture, GIF or video.")
    if ext in IMAGE_EXT or ext == ".gif":
        try:
            with Image.open(path) as im:
                frames = getattr(im, "n_frames", 1)
                w, h = im.size
                seconds = sum(_frame_ms(im, i) for i in range(frames)) / 1000 if frames > 1 else 0
        except OSError as err:
            raise ValueError(f"Could not read this picture: {err}") from err
        return {"kind": "video" if frames > 1 else "image", "w": w, "h": h, "seconds": seconds}
    try:
        import av
        with av.open(path) as c:
            if not c.streams.video:
                raise ValueError("This file has no video in it.")
            s = c.streams.video[0]
            seconds = float(c.duration / 1_000_000) if c.duration else 0
            return {"kind": "video", "w": s.width, "h": s.height, "seconds": seconds}
    except ImportError as err:
        raise ValueError("Videos need the 'av' package (pip install av).") from err
    except (OSError, av.error.FFmpegError) as err:
        raise ValueError(f"Could not read this video: {err}") from err


def _frame_ms(im, i):
    im.seek(i)
    return max(20, im.info.get("duration", 100) or 100)


def cover_size(w, h, target):
    """Output size that fills `target` without being smaller than the source, even and at most 4K."""
    scale = max(target[0] / w, target[1] / h, 1.0)
    scale = min(scale, max(1.0, min(MAX_SIZE[0] / w, MAX_SIZE[1] / h)))
    return max(2, int(w * scale) // 2 * 2), max(2, int(h * scale) // 2 * 2)


def is_soft(w, h, target):
    """True when filling the calendar enlarges the source by more than about 10 %."""
    return max(target[0] / w, target[1] / h) > 1 / SOFT


def import_media(src, folder, target, enhance=True, progress=None):
    """Copy or convert `src` into `folder`. Returns the background record stored in the settings."""
    info = probe(src)
    os.makedirs(folder, exist_ok=True)
    stem = PREFIX + uuid.uuid4().hex[:10]
    ext = os.path.splitext(src)[1].lower()
    record = {"kind": info["kind"], "name": os.path.basename(src)[:80], "source_w": info["w"],
              "source_h": info["h"], "w": info["w"], "h": info["h"], "enhanced": False, "poster": None}
    if info["kind"] == "image":
        with Image.open(src) as im:
            im = _flatten(ImageOps.exif_transpose(im))
            im.thumbnail((MAX_SIZE[0], MAX_SIZE[0]), Image.LANCZOS)  # a huge photo would slow every redraw
            record["w"], record["h"] = im.size
            record["file"] = stem + ".png"
            im.save(os.path.join(folder, record["file"]))
        return record
    sharpen = enhance and is_soft(info["w"], info["h"], target) and info["seconds"] <= ENHANCE_MAX_SECONDS
    record["poster"] = stem + "-poster.png"
    if ext in PLAYABLE_EXT and not sharpen:
        record["file"] = stem + ext
        shutil.copyfile(src, os.path.join(folder, record["file"]))
        _poster(src, os.path.join(folder, record["poster"]))
        return record
    size = cover_size(info["w"], info["h"], target) if sharpen else (info["w"] // 2 * 2, info["h"] // 2 * 2)
    record["file"] = stem + ".mp4"
    _convert(src, os.path.join(folder, record["file"]), os.path.join(folder, record["poster"]), size, sharpen,
             info["seconds"], progress)
    record["w"], record["h"], record["enhanced"] = size[0], size[1], sharpen
    return record


def _flatten(im):
    """RGB copy; transparent parts become black (the calendar's backdrop is dark)."""
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        back = Image.new("RGBA", im.size, (0, 0, 0, 255))
        return Image.alpha_composite(back, im).convert("RGB")
    return im.convert("RGB")


def _source_frames(src):
    """(seconds, frame) for each frame, then (end time, None). GIF and animated WebP come from Pillow as
    pictures (exact frame times); other videos from PyAV as decoded video frames."""
    ext = os.path.splitext(src)[1].lower()
    if ext in IMAGE_EXT or ext == ".gif":
        with Image.open(src) as im:
            t = 0.0
            for i in range(getattr(im, "n_frames", 1)):
                ms = _frame_ms(im, i)
                yield t, _flatten(im)
                t += ms / 1000
            yield t, None
        return
    import av
    with av.open(src) as c:
        s = c.streams.video[0]
        s.thread_type = "AUTO"
        last = 0.0
        step = float(1 / s.average_rate) if s.average_rate else 1 / 30
        for frame in c.decode(s):
            last = float(frame.time) if frame.time is not None else last + step
            yield last, frame
        yield last + step, None


def _rate(src):
    ext = os.path.splitext(src)[1].lower()
    if ext in IMAGE_EXT or ext == ".gif":
        return Fraction(30)  # GIF frame times are multiples of 10 ms; 30 fps shows them closely enough
    import av
    with av.open(src) as c:
        r = c.streams.video[0].average_rate
    return Fraction(r).limit_denominator(1001) if r and 1 <= r <= 120 else Fraction(30)


class _Scaler:
    """FFmpeg filters (in C, fast): Lanczos scale, optional unsharp mask, then yuv420p for H.264."""

    def __init__(self, first, size, sharpen):
        import av
        self.graph = g = av.filter.Graph()
        nodes = [g.add_buffer(template=first),
                 g.add("scale", f"{size[0]}:{size[1]}:flags=lanczos")]
        if sharpen:
            nodes.append(g.add("unsharp", "5:5:0.8:5:5:0.0"))
        nodes += [g.add("format", "yuv420p"), g.add("buffersink")]
        g.link_nodes(*nodes).configure()

    def __call__(self, frame):
        self.graph.push(frame)
        return self.graph.pull()


def _convert(src, dst, poster, size, sharpen, seconds, progress):
    """Re-encode to H.264 at a constant frame rate (GIF frames are repeated for their duration)."""
    import av
    rate = _rate(src)
    tmp = dst + ".part"
    out = av.open(tmp, "w", format="mp4")
    try:
        stream = out.add_stream("libx264", rate=rate)
        stream.width, stream.height = size
        stream.pix_fmt = "yuv420p"
        stream.options = {"crf": "18", "preset": "veryfast", "movflags": "+faststart"}
        scaler = None

        def emit(frame, n):
            frame.pts = n
            frame.time_base = 1 / rate
            out.mux(stream.encode(frame))
            if progress and seconds:
                progress(min(1.0, float(n / rate) / seconds))

        n, prev = 0, None
        for t, frame in _source_frames(src):
            while prev is not None and n / rate < t:  # show the previous frame until this one starts
                emit(prev, n)
                n += 1
            if frame is None:
                break
            if isinstance(frame, Image.Image):
                frame = av.VideoFrame.from_image(frame)
                frame.time_base = Fraction(1, 1000)
            frame.pts = None
            if scaler is None:
                scaler = _Scaler(frame, size, sharpen)
            prev = scaler(frame)
            if n == 0 and not os.path.exists(poster):
                prev.to_image().save(poster)
        if n == 0 and prev is not None:  # a single frame
            emit(prev, 0)
        out.mux(stream.encode(None))
    finally:
        out.close()
    os.replace(tmp, dst)


def _poster(src, dst):
    for _, frame in _source_frames(src):
        if frame is not None:
            (frame if isinstance(frame, Image.Image) else frame.to_image()).save(dst)
        return


def render_still(path, size):
    """The picture scaled and cropped to fill `size` (Lanczos), sharpened a little if it was upscaled."""
    with Image.open(path) as im:
        im = _flatten(im)
        w, h = im.size
        scale = max(size[0] / w, size[1] / h)
        out = ImageOps.fit(im, size, Image.LANCZOS)
    if scale > 1.2:
        out = out.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2))
    return out


def advice(record, target):
    """A tip when the background will look soft at this calendar size, else ''."""
    if not record:
        return ""
    sw, sh = record["source_w"], record["source_h"]
    if not is_soft(sw, sh, target):
        return ""
    times = max(target[0] / sw, target[1] / sh)
    size = f"{sw}×{sh}"
    if record["kind"] == "image":
        return (f"This picture is {size} and the calendar is {target[0]}×{target[1]}, so it is enlarged "
                f"{times:.1f}× and looks soft. For a sharp result, upscale it 2–4× first with a free AI upscaler "
                f"such as Upscayl (Real-ESRGAN; pick an anime or digital-art model for drawings), then choose "
                f"the upscaled file.")
    done = (f"A sharpened {record['w']}×{record['h']} copy was made. " if record.get("enhanced") else "")
    return (f"This video is {size} and the calendar is {target[0]}×{target[1]}, so it is enlarged {times:.1f}×. "
            f"{done}For real extra detail, upscale it first with a free AI video upscaler such as Video2X "
            f"(Real-ESRGAN or Anime4K for anime), then choose the upscaled file.")


def prune(folder, keep):
    """Delete background files in `folder` that no setting refers to any more."""
    if not os.path.isdir(folder):
        return
    for name in os.listdir(folder):
        if name.startswith(PREFIX) and name not in keep:
            try:
                os.remove(os.path.join(folder, name))
            except OSError:
                pass
