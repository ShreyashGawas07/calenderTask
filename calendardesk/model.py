"""Pure calendar logic. No Tk, no files: everything here is unit-tested."""
import calendar
import re
import uuid
from datetime import date, datetime, timedelta

REPEATS = ("none", "daily", "weekly", "monthly", "yearly")
COLORS = ["#e8e8e8", "#ff6b6b", "#ffa94d", "#ffd43b", "#69db7c", "#4dabf7", "#b197fc", "#f783ac"]


def d2s(d):
    return d.isoformat()


def s2d(s):
    return date.fromisoformat(s) if s else None


def new_id():
    return uuid.uuid4().hex[:12]


def new_task(title, day):
    return {
        "id": new_id(), "title": title, "note": "",
        "date": day if isinstance(day, str) else d2s(day),
        "time": None, "remind": False, "remind_before": 0,
        "repeat": "none", "interval": 1, "weekdays": [], "until": None,
        "done": False, "done_dates": [], "skip_dates": [],
        "color": None, "created": datetime.now().isoformat(timespec="seconds"),
    }


def _clamp_day(year, month, day):
    return min(day, calendar.monthrange(year, month)[1])


def occurs_on(t, day):
    start = s2d(t["date"])
    if day < start:
        return False
    if t.get("until") and day > s2d(t["until"]):
        return False
    if d2s(day) in t.get("skip_dates", ()):
        return False
    rep, n = t.get("repeat", "none"), max(1, int(t.get("interval") or 1))
    if rep == "none":
        return day == start
    if rep == "daily":
        return (day - start).days % n == 0
    if rep == "weekly":
        weekdays = t.get("weekdays") or [start.weekday()]
        if day.weekday() not in weekdays:
            return False
        weeks = ((day - timedelta(day.weekday())) - (start - timedelta(start.weekday()))).days // 7
        return weeks % n == 0
    if rep == "monthly":
        months = (day.year - start.year) * 12 + day.month - start.month
        return months % n == 0 and day.day == _clamp_day(day.year, day.month, start.day)
    if rep == "yearly":
        if (day.year - start.year) % n or day.month != start.month:
            return False
        return day.day == _clamp_day(day.year, day.month, start.day)
    return False


def is_done(t, day):
    if t.get("repeat", "none") == "none":
        return bool(t.get("done"))
    return d2s(day) in t.get("done_dates", ())


def set_done(t, day, done):
    if t.get("repeat", "none") == "none":
        t["done"] = done
        return
    dates = set(t.get("done_dates", ()))
    (dates.add if done else dates.discard)(d2s(day))
    t["done_dates"] = sorted(dates)


# -- checklists ---------------------------------------------------------------
# Items follow their task: one-off tasks use `done`, repeating tasks use `done_dates` per day.

def new_item(text):
    return {"id": new_id(), "text": text, "done": False, "done_dates": []}


def item_done(t, item, day):
    if t.get("repeat", "none") == "none":
        return bool(item.get("done"))
    return d2s(day) in item.get("done_dates", ())


def _mark_item(t, item, day, done):
    if t.get("repeat", "none") == "none":
        item["done"] = done
        return
    dates = set(item.get("done_dates", ()))
    (dates.add if done else dates.discard)(d2s(day))
    item["done_dates"] = sorted(dates)


def set_item_done(t, item, day, done):
    """Tick or untick one item. Ticking the last open item ticks the task; unticking any unticks it."""
    _mark_item(t, item, day, done)
    if not done:
        set_done(t, day, False)
    elif all(item_done(t, i, day) for i in t.get("items", ())):
        set_done(t, day, True)


def set_task_done(t, day, done):
    """Tick the task (and all its items), or untick it while keeping the items' progress."""
    set_done(t, day, done)
    if done:
        for item in t.get("items", ()):
            _mark_item(t, item, day, True)


def progress(t, day):
    items = t.get("items") or []
    return sum(item_done(t, i, day) for i in items), len(items)


def tasks_on(tasks, day):
    """Tasks occurring on `day`: open ones first, by time (untimed last), then creation."""
    found = [t for t in tasks if occurs_on(t, day)]
    return sorted(found, key=lambda t: (is_done(t, day), t.get("time") or "99:99", t.get("created", "")))


def rollover(tasks, today):
    """Move unfinished one-off tasks from past days to today. Returns how many moved."""
    moved = 0
    for t in tasks:
        if t.get("repeat", "none") == "none" and not t.get("done") and s2d(t["date"]) < today:
            t.setdefault("moved_from", t["date"])
            t["date"] = d2s(today)
            moved += 1
    return moved


def reminder_time(t, day):
    if not (t.get("remind") and t.get("time")):
        return None
    hh, mm = map(int, t["time"].split(":"))
    return datetime(day.year, day.month, day.day, hh, mm) - timedelta(minutes=int(t.get("remind_before") or 0))


def countdown_info(c, today):
    """Return (days until target, target date, completed years or None)."""
    base = s2d(c["date"])
    if not c.get("yearly"):
        return (base - today).days, base, None
    year = today.year
    target = date(year, base.month, _clamp_day(year, base.month, base.day))
    if target < today:
        year += 1
        target = date(year, base.month, _clamp_day(year, base.month, base.day))
    return (target - today).days, target, year - base.year


def school_week(terms, day):
    for term in terms:
        start, end = s2d(term["start"]), s2d(term["end"])
        if start and end and start <= day <= end:
            monday = start - timedelta(start.weekday())
            return term["name"], (day - monday).days // 7 + 1
    return None


def month_grid(year, month, first_weekday=0):
    """6 rows x 7 dates covering the month."""
    first = date(year, month, 1)
    start = first - timedelta((first.weekday() - first_weekday) % 7)
    return [[start + timedelta(r * 7 + c) for c in range(7)] for r in range(6)]


def matches(t, query):
    q = query.lower()
    return q in t.get("title", "").lower() or q in t.get("note", "").lower()


# -- smart typing ----------------------------------------------------------------
# "call mom 7pm tomorrow" -> title "call mom", 19:00, the next day. English only, offline.

_WD_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_WD = r"(mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:r(?:s(?:day)?)?)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)"
_MON = (r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
        r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")
_ORD = r"(?:st|nd|rd|th)?"
_L, _R = r"(?<![\w.])", r"(?![\w])(?!\.\w)"  # whole words only: "monday.com" is not Monday
_UNITS = {"day": "daily", "week": "weekly", "month": "monthly", "year": "yearly"}


def _wd(name):
    return ["mon", "tue", "wed", "thu", "fri", "sat", "sun"].index(name[:3].lower())


def _mon(name):
    return ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"].index(name[:3].lower()) + 1


def _upcoming(base, weekday):
    return base + timedelta((weekday - base.weekday()) % 7)


def _day_month(base, d, m, y=None):
    """The date d/m in year y, or the next one on/after base when no year is given; None if invalid."""
    try:
        if y:
            return date(y if y > 99 else 2000 + y, m, d)
        found = date(base.year, m, d)
        return found if found >= base else date(base.year + 1, m, d)
    except ValueError:
        return None


def _nth_of_month(base, d):
    y, m = base.year, base.month
    for _ in range(13):
        if d <= calendar.monthrange(y, m)[1] and date(y, m, d) >= base:
            return date(y, m, d)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return None


def _date_label(day, base):
    if day == base:
        return "Today"
    if day == base + timedelta(1):
        return "Tomorrow"
    return f"{_WD_NAMES[day.weekday()]} {day.day} {calendar.month_abbr[day.month]}" + (
        f" {day.year}" if day.year != base.year else "")


def parse_quick(text, base_day):
    """Split quick-add text into a title plus date, time, repeat and reminder. Recognised words are
    removed from the title; if nothing would be left, the original text stays the title."""
    work = f" {text} "
    out = {"title": text.strip(), "date": base_day, "time": None, "repeat": "none", "interval": 1,
           "weekdays": [], "remind": False, "found": []}
    flags = re.IGNORECASE
    labels = {}

    def take(pattern):
        nonlocal work
        m = re.search(_L + pattern + _R, work, flags)
        if m:
            work = work[:m.start()] + " " + work[m.end():]
        return m

    # reminder
    remind = bool(take(r"remind\s+me"))
    if re.search(r"!+\s*$", work):
        work = re.sub(r"!+\s*$", " ", work)
        remind = True

    # repeat
    if m := take(r"every\s+(\d{1,3})\s+(day|week|month|year)s?"):
        out["repeat"], out["interval"] = _UNITS[m.group(2).lower()], max(1, int(m.group(1)))
        n = out["interval"]
        labels["repeat"] = f"Every {n} {m.group(2).lower()}s" if n > 1 else out["repeat"].capitalize()
    elif m := take(rf"every\s+{_WD}(?:\s*(?:,|and|&)\s*{_WD})*"):
        days = sorted({_wd(w) for w in re.findall(_L + _WD + _R, m.group(0), flags)})
        out["repeat"], out["weekdays"] = "weekly", days
        labels["repeat"] = "Weekly on " + ", ".join(_WD_NAMES[d] for d in days)
    elif m := take(r"(daily|every\s+day|weekly|every\s+week|monthly|every\s+month|yearly|annually|every\s+year)"):
        word = m.group(1).lower()
        out["repeat"] = "daily" if word == "daily" else next((v for k, v in _UNITS.items() if k in word), "yearly")
        labels["repeat"] = out["repeat"].capitalize()

    # date
    day = None
    if take(r"day\s+after\s+tomorrow"):
        day = base_day + timedelta(2)
    elif take(r"(tomorrow|tmrw|tmr)"):
        day = base_day + timedelta(1)
    elif take(r"(today|tonight)"):
        day = base_day
    elif m := take(rf"(?:on\s+)?next\s+{_WD}"):
        day = _upcoming(base_day, _wd(m.group(1))) + timedelta(7)
    elif m := re.search(_L + r"(?:on\s+)?(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?" + _R, work, flags):
        day = _day_month(base_day, int(m.group(1)), int(m.group(2)), int(m.group(3)) if m.group(3) else None)
        if day:
            take(re.escape(m.group(0).strip()))
    elif m := re.search(_L + rf"(?:on\s+)?(?:the\s+)?(\d{{1,2}}){_ORD}\s+(?:of\s+)?{_MON}(?:\s+(\d{{4}}))?" + _R,
                        work, flags):
        day = _day_month(base_day, int(m.group(1)), _mon(m.group(2)), int(m.group(3)) if m.group(3) else None)
        if day:
            take(re.escape(m.group(0).strip()))
    elif m := re.search(_L + rf"(?:on\s+)?{_MON}\s+(\d{{1,2}}){_ORD}(?:,?\s+(\d{{4}}))?" + _R, work, flags):
        day = _day_month(base_day, int(m.group(2)), _mon(m.group(1)), int(m.group(3)) if m.group(3) else None)
        if day:
            take(re.escape(m.group(0).strip()))
    elif m := re.search(_L + r"(?:on\s+)?(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)" + _R, work, flags):
        day = _nth_of_month(base_day, int(m.group(1)))
        if day:
            take(re.escape(m.group(0).strip()))
    elif m := take(rf"(?:on\s+)?{_WD}"):
        day = _upcoming(base_day, _wd(m.group(1)))
    if day is None and out["weekdays"]:
        day = min(_upcoming(base_day, d) for d in out["weekdays"])  # first occurrence
    elif day is not None:
        labels["date"] = _date_label(day, base_day)
    out["date"] = day or base_day

    # time
    if m := take(r"(?:at\s+)?(1[0-2]|0?[1-9])(?:[:.]([0-5]\d))?\s*(am|pm)"):
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        h = h % 12 + (12 if m.group(3).lower() == "pm" else 0)
        out["time"] = f"{h:02d}:{mi:02d}"
    elif m := take(r"(?:at\s+)?([01]?\d|2[0-3])[:.]([0-5]\d)"):
        out["time"] = f"{int(m.group(1)):02d}:{m.group(2)}"
    elif m := take(r"at\s+([01]?\d|2[0-3])"):
        out["time"] = f"{int(m.group(1)):02d}:00"
    elif m := take(r"(?:at\s+)?(noon|midnight)"):
        out["time"] = "12:00" if m.group(1).lower() == "noon" else "00:00"
    if out["time"]:
        labels["time"] = out["time"]

    out["remind"] = remind and out["time"] is not None
    if out["remind"]:
        labels["remind"] = "Reminder"
    out["found"] = [labels[k] for k in ("repeat", "date", "time", "remind") if k in labels]
    title = re.sub(r"\s+", " ", work).strip(" ,;-")
    if title:
        out["title"] = title
    return out
