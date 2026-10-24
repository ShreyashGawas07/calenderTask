"""Indian public holidays, cached per year."""
from functools import lru_cache

try:
    import holidays as _holidays
except ImportError:  # the calendar still works without the package
    _holidays = None


@lru_cache(maxsize=8)
def _year(year):
    if _holidays is None:
        return {}
    return dict(_holidays.India(years=year))


def holiday_name(day):
    return _year(day.year).get(day)


def holidays_in(year):
    return sorted(_year(year).items())
