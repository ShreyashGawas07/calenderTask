"""Keyboard shortcuts: the command list, shortcut text, and conflict checks (pure, no Tk).

A shortcut is one or two steps. A step is (modifiers, key), e.g. (("Ctrl", "Shift"), "O").
Text form: "Ctrl+Shift+O, D" (a chord: Ctrl+Shift+O, then D within CHORD_MS).
"""
import os
import struct

CHORD_MS = 1500
MODS = ("Win", "Ctrl", "Alt", "Shift")
_MOD_NAMES = {"ctrl": "Ctrl", "control": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win", "windows": "Win"}

KEYS = {chr(c): c for c in range(ord("A"), ord("Z") + 1)}
KEYS.update({str(d): 0x30 + d for d in range(10)})
KEYS.update({f"F{n}": 0x6F + n for n in range(1, 25)})
KEYS.update({"Left": 0x25, "Up": 0x26, "Right": 0x27, "Down": 0x28, "Home": 0x24, "End": 0x23,
             "PageUp": 0x21, "PageDown": 0x22, "Insert": 0x2D, "Delete": 0x2E, "Space": 0x20,
             "Enter": 0x0D, "Tab": 0x09, "Esc": 0x1B, "Backspace": 0x08,
             ",": 0xBC, ".": 0xBE, "/": 0xBF, ";": 0xBA, "'": 0xDE, "[": 0xDB, "]": 0xDD,
             "\\": 0xDC, "-": 0xBD, "=": 0xBB, "`": 0xC0})
_KEY_NAMES = {k.lower(): k for k in KEYS}
_KEY_NAMES.update({"escape": "Esc", "del": "Delete", "return": "Enter", "pgup": "PageUp",
                   "pgdn": "PageDown", "ins": "Insert", "back": "Backspace"})
_VK_KEYS = {vk: k for k, vk in KEYS.items()}

# (id, label, default shortcut, works everywhere by default). "{hotkey}" is the old hotkey letter.
ACTIONS = [
    ("toggle_front", "Show / hide calendar", "Ctrl+Alt+{hotkey}", True),
    ("open_today", "Open today's day panel", "Ctrl+Shift+O, D", False),
    ("menu", "Open the ☰ menu", "Ctrl+Shift+C, H", False),
    ("quick_add", "Add a task to today (smart typing)", "Ctrl+Shift+N", False),
    ("new_task", "New task…", "Ctrl+N", False),
    ("search", "Search", "Ctrl+F", False),
    ("settings", "Settings", "Ctrl+,", False),
    ("next_month", "Next month", "Right", False),
    ("prev_month", "Previous month", "Left", False),
    ("go_today", "Go to today", "Home", False),
    ("send_back", "Send calendar back to the wallpaper", "Esc", False),
    ("toggle_mini", "Mini calendar", "Ctrl+M", False),
    ("new_note", "New note", "", False),
    ("new_countdown", "New countdown…", "", False),
    ("countdowns", "Countdowns…", "", False),
    ("show_all", "Show all notes and cards", "", False),
    ("export", "Export…", "", False),
    ("undo_settings", "Undo last settings change", "", False),
    ("shortcuts", "Keyboard shortcuts…", "", False),
    ("quit", "Exit", "", False),
]
LABELS = {a[0]: a[1] for a in ACTIONS}

# Windows keeps these for itself: Win+<key> alone is reserved as a rule, plus these steps.
RESERVED = {"Ctrl+Alt+Delete", "Ctrl+Shift+Esc", "Alt+Tab", "Alt+Shift+Tab", "Ctrl+Alt+Tab", "Alt+F4",
            "Ctrl+Esc", "Alt+Esc", "Alt+Shift+Esc", "Win+Ctrl+D", "Win+Ctrl+Left", "Win+Ctrl+Right",
            "Win+Ctrl+F4", "Win+Shift+S", "Win+Shift+Left", "Win+Shift+Right", "Win+Shift+Up",
            "Win+Shift+Down", "Win+Ctrl+Shift+B", "Win+Alt+R", "Win+Alt+G", "Win+Alt+B"}

# Keys other programs commonly use; a global shortcut takes them away from those programs.
COMMON = {f"Ctrl+{k}": "most programs (copy, paste, save, find, new, print…)" for k in "ACVXZYSFNOPWTRHJKLDEGBIUQ"}
COMMON.update({f"Ctrl+Shift+{k}": "browsers and editors (reopen tab, private window, dev tools…)"
               for k in "TNOIJCPWRZSKEFDBV"})
COMMON.update({k: "browsers and editors" for k in ("Ctrl+Tab", "Ctrl+Shift+Tab", "Ctrl+Enter", "Ctrl+Space",
                                                   "Ctrl+F4", "Ctrl+F5", "Alt+Enter", "Alt+Left", "Alt+Right",
                                                   "Alt+Space", "Ctrl+Alt+Left", "Ctrl+Alt+Right")})
CALCULATOR = {**{f"Alt+{n}": "switch modes" for n in "12345"},
              **{f"Ctrl+{k}": "memory and history" for k in "MPQRLH"}, "Ctrl+Shift+D": "clear history"}


def _step_text(step):
    mods, key = step
    return "+".join(mods + (key,))


def fmt(steps):
    return ", ".join(_step_text(s) for s in steps)


def _parse_step(text, i):
    """Read 'Mod+Mod+Key' from text[i:]; return (step, next index)."""
    mods, key = [], None
    while True:
        while i < len(text) and text[i] == " ":
            i += 1
        if i >= len(text):
            raise ValueError("a key is missing")
        j = i
        if text[i].isalnum():
            while j < len(text) and text[j].isalnum():
                j += 1
        else:
            j += 1
        token, i = text[i:j], j
        low = token.lower()
        if low in _MOD_NAMES and key is None and (i < len(text) and text[i:].lstrip().startswith("+")):
            if _MOD_NAMES[low] not in mods:
                mods.append(_MOD_NAMES[low])
        elif low in _KEY_NAMES:
            if key is not None:
                raise ValueError("only one key per step (use a comma for a second key)")
            key = _KEY_NAMES[low]
        elif low in _MOD_NAMES:
            raise ValueError("a key is missing after " + _MOD_NAMES[low])
        else:
            raise ValueError(f"unknown key '{token}'")
        while i < len(text) and text[i] == " ":
            i += 1
        if i < len(text) and text[i] == "+":
            i += 1
            continue
        if key is None:
            raise ValueError("a key is missing")
        return (tuple(m for m in MODS if m in mods), key), i


def parse(text):
    """'Ctrl+Shift+O, D' -> (step, step). Empty text -> (). Raises ValueError if it is not a shortcut."""
    text = (text or "").strip()
    if not text:
        return ()
    steps, i = [], 0
    while True:
        step, i = _parse_step(text, i)
        steps.append(step)
        if i >= len(text):
            break
        if text[i] != ",":
            raise ValueError("use a comma between the two steps")
        i += 1
    if len(steps) > 2:
        raise ValueError("at most two steps")
    return tuple(steps)


def win32(step):
    """Step -> (RegisterHotKey modifiers, virtual-key code)."""
    mods, key = step
    bits = {"Alt": 0x1, "Ctrl": 0x2, "Shift": 0x4, "Win": 0x8}
    return sum(bits[m] for m in mods), KEYS[key]


def key_from_vk(vk):
    return _VK_KEYS.get(vk)


def step_from_tk(state, keycode, win=False):
    """A Tk <KeyPress> on Windows (keycode = virtual-key code) -> step, or None for a lone modifier."""
    key = key_from_vk(keycode)
    if key is None:
        return None
    mods = [m for m, bit in (("Ctrl", 0x4), ("Alt", 0x20000), ("Shift", 0x1)) if state & bit]
    if win:
        mods.append("Win")
    return tuple(m for m in MODS if m in mods), key


def defaults(hotkey="C"):
    letter = (hotkey or "C").upper()
    return {a: {"keys": keys.replace("{hotkey}", letter), "global": glob} for a, _, keys, glob in ACTIONS}


def effective(settings):
    """Every command's shortcut: the user's choice where it is valid, else the default."""
    out = defaults(settings.get("hotkey") or "C")
    for action, value in (settings.get("shortcuts") or {}).items():
        if action not in out or not isinstance(value, dict):
            continue
        try:
            keys = fmt(parse(value.get("keys", "")))
        except (ValueError, AttributeError, TypeError):
            continue
        out[action] = {"keys": keys, "global": bool(value.get("global", out[action]["global"]))}
    return out


def conflicts(action, keys, glob, eff, taken=None, lnk=None):
    """Problems with giving `action` the shortcut `keys`: [(\"error\"|\"warning\", message)], errors first.

    eff: every command's current shortcut (from effective()). taken(step) -> True when another program
    has registered that step. lnk: {step text: shortcut name} from Start-menu / desktop shortcut keys.
    """
    try:
        steps = parse(keys)
    except ValueError as e:
        return [("error", f"Not a valid shortcut: {e}.")]
    if not steps:
        return []
    errors, warnings = [], []
    first = _step_text(steps[0])
    for step in steps:
        text = _step_text(step)
        if text in RESERVED or step[0] == ("Win",):
            errors.append(f"{text} is reserved by Windows.")
    if glob and not set(steps[0][0]) & {"Ctrl", "Alt", "Win"}:
        errors.append("A shortcut that works everywhere needs Ctrl, Alt or Win, or that key would stop typing.")
    if not glob and any("Win" in s[0] for s in steps):
        errors.append("Win can only be used in shortcuts that work everywhere.")
    for other, b in eff.items():
        if other == action or not b.get("keys"):
            continue
        try:
            theirs = parse(b["keys"])
        except ValueError:
            continue
        label = LABELS.get(other, other)
        if theirs == steps:
            errors.append(f"{fmt(steps)} is already used by '{label}'.")
        elif theirs[0] == steps[0] and (len(theirs) == 1 or len(steps) == 1):
            errors.append(f"{first} already starts '{label}' ({fmt(theirs)}); one can't be the start of the other.")
    if glob and taken is not None:
        try:
            if taken(steps[0]):
                errors.append(f"{first} is already registered by another program (Windows doesn't say which).")
        except OSError:
            pass
    if lnk and first in lnk:
        warnings.append(f"{first} is the shortcut key of '{lnk[first]}' (Start menu or desktop).")
    if glob:
        if first in COMMON:
            warnings.append(f"{first} is used by {COMMON[first]}; it won't work there while this is set.")
        elif steps[0][0] == ("Alt",) and len(steps[0][1]) == 1 and steps[0][1].isalpha():
            warnings.append(f"{first} opens menus in many programs; it won't work there while this is set.")
        elif steps[0][1].startswith("F") and steps[0][1][1:].isdigit():
            warnings.append(f"{first} uses a function key that programs often use.")
        if first in CALCULATOR:
            warnings.append(f"{first} is used by Windows Calculator ({CALCULATOR[first]}).")
    return [("error", m) for m in errors] + [("warning", m) for m in warnings]


def lnk_folders():
    """Where Windows looks for shortcut keys: Start menu and desktop, for this user and everyone."""
    env = os.environ.get
    out = []
    for base in (env("APPDATA"), env("PROGRAMDATA")):
        if base:
            out.append(os.path.join(base, "Microsoft", "Windows", "Start Menu"))
    for base in (env("USERPROFILE"), env("PUBLIC")):
        if base:
            out.append(os.path.join(base, "Desktop"))
    return out


_LNK_CLSID = bytes.fromhex("0114020000000000c000000000000046")


def lnk_hotkeys(folders):
    """{step text: shortcut name} for every .lnk under folders that has a 'Shortcut key'."""
    out = {}
    for folder in folders:
        for root, _dirs, files in os.walk(folder):
            for name in files:
                if not name.lower().endswith(".lnk"):
                    continue
                try:
                    with open(os.path.join(root, name), "rb") as f:
                        head = f.read(0x42)
                except OSError:
                    continue
                if len(head) < 0x42 or struct.unpack_from("<I", head)[0] != 0x4C or head[4:20] != _LNK_CLSID:
                    continue
                vk, flags = head[0x40], head[0x41]
                key = key_from_vk(vk)
                if not key:
                    continue
                mods = tuple(m for m, bit in (("Ctrl", 2), ("Alt", 4), ("Shift", 1)) if flags & bit)
                out.setdefault(_step_text((tuple(m for m in MODS if m in mods), key)), name[:-4])
    return out
