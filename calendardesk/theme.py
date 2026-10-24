"""Colours and fonts. `apply(settings)` swaps the module-level values, so every window
reads the current theme the next time it draws."""
import tkinter.font as tkfont

PRESETS = {
    "dark": {
        "bg": "#1b1d23", "panel": "#23262e", "grid": "#353944", "text": "#eceff4", "muted": "#8a909c",
        "dim": "#555b66", "accent": "#4dabf7", "weekend": "#ff8787", "holiday": "#ffa94d", "done": "#6c727d",
        "opacity": 0.88,
        "date_colors": ["#5c2b2b", "#5c472b", "#56532a", "#2f5530", "#2a4a5c", "#3d2f5c", "#5a2c4a", "#3a3f4a"],
    },
    "light": {
        "bg": "#ffffff", "panel": "#eef1f5", "grid": "#d5dae1", "text": "#1f2329", "muted": "#6b7380",
        "dim": "#b3b9c2", "accent": "#1c7ed6", "weekend": "#e03131", "holiday": "#e8590c", "done": "#9aa1ab",
        "opacity": 0.93,
        "date_colors": ["#ffe3e3", "#ffe8cc", "#fff3bf", "#d3f9d8", "#d0ebff", "#e5dbff", "#ffdeeb", "#e9ecef"],
    },
    "glass": {
        "bg": "#0f1218", "panel": "#161a22", "grid": "#2b313d", "text": "#f5f7fa", "muted": "#a3abb8",
        "dim": "#5d6573", "accent": "#63e6be", "weekend": "#ff8fa3", "holiday": "#ffd43b", "done": "#7a8291",
        "opacity": 0.6,
        "date_colors": ["#5c2b2b", "#5c472b", "#56532a", "#2f5530", "#2a4a5c", "#3d2f5c", "#5a2c4a", "#3a3f4a"],
    },
    "paper": {
        "bg": "#f8f3e6", "panel": "#efe6d0", "grid": "#d9cdb0", "text": "#3b3326", "muted": "#857a66",
        "dim": "#bfb39a", "accent": "#c0392b", "weekend": "#c0392b", "holiday": "#b9770e", "done": "#a99f8b",
        "opacity": 0.95,
        "date_colors": ["#f5c6c0", "#f6d5a8", "#f3e7a1", "#cfe5c0", "#c3dbe8", "#d9cce8", "#f0c9dc", "#e2d9c6"],
    },
}
THEME_NAMES = {"dark": "Dark", "light": "Light", "glass": "Glass", "paper": "Paper"}
FINE_COLOURS = {"text": "Text", "weekend": "Weekends", "holiday": "Holidays", "grid": "Grid lines"}

# Current values (replaced by apply()).
BG = PANEL = GRID = TEXT = MUTED = DIM = ACCENT = TODAY = WEEKEND = HOLIDAY = DONE = ""
DATE_COLORS = []
FAMILY = "Segoe UI"

NOTE_COLORS = ["#fff3a8", "#ffd6a5", "#caffbf", "#9bf6ff", "#bdb2ff", "#ffc6ff", "#f1f1f1"]
CARD_COLORS = ["#4dabf7", "#ff6b6b", "#ffa94d", "#69db7c", "#b197fc", "#f783ac", "#20c997"]
CARD_STYLES = {"minimal": "Minimal", "solid": "Solid", "gradient": "Gradient", "ring": "Progress ring"}


def palette(settings):
    p = dict(PRESETS.get(settings.get("theme"), PRESETS["dark"]))
    if settings.get("accent"):
        p["accent"] = settings["accent"]
    p.update({k: v for k, v in (settings.get("colors") or {}).items() if v})
    return p


def apply(settings):
    global BG, PANEL, GRID, TEXT, MUTED, DIM, ACCENT, TODAY, WEEKEND, HOLIDAY, DONE, DATE_COLORS, FAMILY
    p = palette(settings)
    BG, PANEL, GRID, TEXT, MUTED, DIM = p["bg"], p["panel"], p["grid"], p["text"], p["muted"], p["dim"]
    ACCENT = TODAY = p["accent"]
    WEEKEND, HOLIDAY, DONE = p["weekend"], p["holiday"], p["done"]
    DATE_COLORS = p["date_colors"]
    FAMILY = settings.get("font_family") or "Segoe UI"


def _rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def mix(c1, c2, t):
    """Blend: t=1 gives c1, t=0 gives c2."""
    a, b = _rgb(c1), _rgb(c2)
    return "#%02x%02x%02x" % tuple(round(x * t + y * (1 - t)) for x, y in zip(a, b))


def readable_on(c):
    """Black or white, whichever reads better on background c."""
    r, g, b = _rgb(c)
    return "#111111" if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else "#ffffff"


def ink(color, bg):
    """A user colour adjusted to stay readable on bg (darkened on light backgrounds)."""
    return mix(color, "#000000", 0.6) if readable_on(bg) == "#111111" and readable_on(color) == "#111111" else color


_font_cache = {}


def _font(size, **kw):
    key = (FAMILY, size, tuple(sorted(kw.items())))
    if key not in _font_cache:
        _font_cache[key] = tkfont.Font(family=FAMILY, size=size, **kw)
    return _font_cache[key]


def fonts(size):
    size = max(6, round(size))
    return {
        "normal": _font(size),
        "bold": _font(size, weight="bold"),
        "small": _font(max(6, size - 1)),
        "strike": _font(size, overstrike=1),
        "title": _font(size + 5, weight="bold"),
        "big": _font(size + 15, weight="bold"),
    }


def fit(font, text, width):
    """Truncate text with an ellipsis so it fits in `width` pixels."""
    if width <= 0:
        return ""
    if font.measure(text) <= width:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if font.measure(text[:mid] + "…") <= width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo] + "…" if lo else ""


apply({})
