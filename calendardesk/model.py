"""Pure calendar logic. No Tk, no files: everything here is unit-tested."""
import calendar
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
