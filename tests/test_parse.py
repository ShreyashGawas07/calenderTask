import unittest
from datetime import date

from calendardesk.model import parse_quick

BASE = date(2026, 10, 24)  # a Saturday


def p(text):
    return parse_quick(text, BASE)


class TimeTests(unittest.TestCase):
    def test_pm(self):
        r = p("call mom 7pm")
        self.assertEqual((r["title"], r["time"], r["date"]), ("call mom", "19:00", BASE))

    def test_minutes_with_space_and_tomorrow(self):
        r = p("submit 7:30 pm tomorrow")
        self.assertEqual((r["title"], r["time"], r["date"]), ("submit", "19:30", date(2026, 10, 25)))

    def test_dot_minutes(self):
        self.assertEqual(p("call 7.30 pm")["time"], "19:30")

    def test_24_hour(self):
        r = p("train 19:30")
        self.assertEqual((r["title"], r["time"]), ("train", "19:30"))

    def test_at_hour_is_24_hour(self):
        r = p("meet at 7")
        self.assertEqual((r["title"], r["time"]), ("meet", "07:00"))

    def test_12am_12pm(self):
        self.assertEqual(p("a 12am")["time"], "00:00")
        self.assertEqual(p("a 12pm")["time"], "12:00")

    def test_noon_midnight(self):
        self.assertEqual(p("lunch noon")["time"], "12:00")
        self.assertEqual(p("x midnight")["time"], "00:00")

    def test_no_time(self):
        r = p("buy milk")
        self.assertIsNone(r["time"])


class DateTests(unittest.TestCase):
    def test_relative_words(self):
        self.assertEqual(p("x today")["date"], BASE)
        self.assertEqual(p("x tmrw")["date"], date(2026, 10, 25))
        self.assertEqual(p("x day after tomorrow")["title"], "x")
        self.assertEqual(p("x day after tomorrow")["date"], date(2026, 10, 26))

    def test_weekday_next_occurrence_including_today(self):
        self.assertEqual(p("gym friday")["date"], date(2026, 10, 30))
        self.assertEqual(p("gym saturday")["date"], BASE)
        self.assertEqual(p("gym mon")["date"], date(2026, 10, 26))

    def test_next_weekday_skips_a_week(self):
        r = p("review next monday")
        self.assertEqual((r["title"], r["date"]), ("review", date(2026, 11, 2)))

    def test_day_month_forms(self):
        for text in ("party 24 oct", "party oct 24", "party 24/10", "party 24-10-2026", "party 24th october"):
            r = p(text)
            self.assertEqual((r["title"], r["date"]), ("party", BASE), text)

    def test_past_day_month_goes_to_next_year(self):
        self.assertEqual(p("x 3 jan")["date"], date(2027, 1, 3))

    def test_ordinal_day(self):
        r = p("bill on the 5th")
        self.assertEqual((r["title"], r["date"]), ("bill", date(2026, 11, 5)))

    def test_invalid_date_is_left_in_title(self):
        r = p("x 31/02")
        self.assertEqual((r["title"], r["date"]), ("x 31/02", BASE))


class RepeatTests(unittest.TestCase):
    def test_monthly_with_ordinal(self):
        r = p("rent 1st every month")
        self.assertEqual((r["title"], r["date"], r["repeat"]), ("rent", date(2026, 11, 1), "monthly"))

    def test_every_weekdays(self):
        r = p("standup every mon and thu 9:30")
        self.assertEqual((r["title"], r["repeat"], r["weekdays"], r["time"]), ("standup", "weekly", [0, 3], "09:30"))
        self.assertEqual(r["date"], date(2026, 10, 26))  # first occurrence

    def test_every_n_days(self):
        r = p("water every 2 days")
        self.assertEqual((r["title"], r["repeat"], r["interval"]), ("water", "daily", 2))

    def test_every_n_weeks(self):
        r = p("clean every 3 weeks")
        self.assertEqual((r["repeat"], r["interval"]), ("weekly", 3))

    def test_simple_words(self):
        self.assertEqual(p("tax yearly")["repeat"], "yearly")
        self.assertEqual(p("pills daily")["repeat"], "daily")
        self.assertEqual(p("pills every day")["repeat"], "daily")
        self.assertEqual(p("call weekly")["repeat"], "weekly")
        self.assertEqual(p("x")["repeat"], "none")


class RemindTests(unittest.TestCase):
    def test_remind_me(self):
        r = p("pay bill 6pm remind me")
        self.assertEqual((r["title"], r["time"], r["remind"]), ("pay bill", "18:00", True))

    def test_bang(self):
        r = p("pay bill 6pm!")
        self.assertEqual((r["title"], r["remind"]), ("pay bill", True))

    def test_no_reminder(self):
        self.assertFalse(p("pay bill 6pm")["remind"])


class FallbackTests(unittest.TestCase):
    def test_only_recognised_words_keeps_original_title(self):
        r = p("tomorrow 7pm")
        self.assertEqual((r["title"], r["date"], r["time"]), ("tomorrow 7pm", date(2026, 10, 25), "19:00"))

    def test_nothing_recognised(self):
        r = p("hello world")
        self.assertEqual((r["title"], r["found"], r["date"]), ("hello world", [], BASE))

    def test_words_inside_other_words(self):
        r = p("monday.com sync")
        self.assertEqual((r["title"], r["date"], r["found"]), ("monday.com sync", BASE, []))
        self.assertEqual(p("saturdays are fun")["title"], "saturdays are fun")

    def test_found_labels(self):
        self.assertEqual(p("x tomorrow 7pm every mon and thu")["found"],
                         ["Weekly on Mon, Thu", "Tomorrow", "19:00"])

    def test_blank(self):
        r = p("   ")
        self.assertEqual(r["title"], "")

    def test_invalid_am_pm_stays_in_title(self):
        r = p("13pm test")
        self.assertEqual((r["title"], r["time"]), ("13pm test", None))

    def test_every_one_day_label(self):
        r = p("water every 1 day")
        self.assertEqual((r["repeat"], r["interval"], r["found"]), ("daily", 1, ["Daily"]))


class FalsePositiveTests(unittest.TestCase):
    """Ordinary words and numbers stay in the title (BUG-5, BUG-6)."""

    def assertKept(self, text):
        r = p(text)
        self.assertEqual((r["title"], r["date"], r["time"], r["found"]), (text, BASE, None, []), text)

    def test_numbers_are_not_dates_or_times(self):
        for text in ("buy 3/4 cup flour", "read pages 1-12", "chapter 2/3 done", "score 3-1",
                     "pay 2.50 for coffee", "version 2.10 release", "pay 2.50", "add 2 3/4", "steps 1/2/3"):
            self.assertKept(text)

    def test_sun_and_sat_as_words(self):
        for text in ("buy sun cream", "the sun also rises", "sat with grandma", "sat exam prep", "sun cream"):
            self.assertKept(text)

    def test_iso_date(self):
        r = p("2026-11-05 dentist")
        self.assertEqual((r["title"], r["date"]), ("dentist", date(2026, 11, 5)))
        self.assertEqual(p("dentist on 2026-11-05")["date"], date(2026, 11, 5))

    def test_short_weekday_where_it_is_a_date(self):
        sat, sun = BASE, date(2026, 10, 25)
        for text, day in (("gym sat", sat), ("gym sun", sun), ("brunch on sun", sun), ("buy sun cream on sat", sat),
                          ("next sun", date(2026, 11, 1))):
            r = p(text)
            self.assertEqual(r["date"], day, text)
        r = p("gym sat 7am")
        self.assertEqual((r["title"], r["date"], r["time"]), ("gym", sat, "07:00"))
        r = p("sun 10am brunch")
        self.assertEqual((r["title"], r["date"], r["time"]), ("brunch", sun, "10:00"))
        r = p("swim every sat")
        self.assertEqual((r["title"], r["weekdays"]), ("swim", [5]))
        self.assertEqual(p("gym saturday")["title"], "gym")
        self.assertEqual(p("saturday gym")["date"], sat)

    def test_slash_date_with_context(self):
        self.assertEqual(p("party on 3/4")["date"], date(2027, 4, 3))
        r = p("dentist 5/11 3pm")
        self.assertEqual((r["title"], r["date"], r["time"]), ("dentist", date(2026, 11, 5), "15:00"))
        self.assertEqual(p("trip 5-11-26")["date"], date(2026, 11, 5))
        self.assertEqual(p("trip on 5-11")["date"], date(2026, 11, 5))

    def test_dot_time_needs_am_pm_or_at(self):
        self.assertEqual(p("call 9.30am")["time"], "09:30")
        r = p("train at 19.00")
        self.assertEqual((r["title"], r["time"]), ("train", "19:00"))
        self.assertEqual(p("pay 2.50 at 19:30")["title"], "pay 2.50")


class TaskFromQuickTests(unittest.TestCase):
    def test_fields_copied(self):
        from calendardesk.model import task_from_quick
        t = task_from_quick(p("standup every mon and thu 9:30 remind me"))
        self.assertEqual((t["title"], t["date"], t["time"], t["repeat"], t["weekdays"], t["remind"]),
                         ("standup", "2026-10-26", "09:30", "weekly", [0, 3], True))
        self.assertEqual(t["items"], [])
