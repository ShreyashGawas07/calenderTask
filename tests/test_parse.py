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
