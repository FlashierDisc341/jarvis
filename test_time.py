"""Pure calendar/timer tests. No microphone, real waiting, or app actions."""
from datetime import date, datetime
import unittest

from jarvis_time import (
    CalendarTimers, ParseError, clean, integer, amount,
    duration_seconds, parse_date, parse_clock, until_clock,
)

NOW = datetime(2026, 9, 17, 15, 0, 0)


class NumberAndDurationTests(unittest.TestCase):
    def test_numbers(self):
        for text, value in (
            ("twenty five", 25), ("one hundred and twenty", 120),
            ("two thousand twenty six", 2026), ("18", 18),
        ):
            self.assertEqual(integer(text), value)
        self.assertEqual(integer("twenty-first", ordinal=True), 21)
        self.assertEqual(integer("eighteenth", ordinal=True), 18)
        self.assertEqual(integer("18th", ordinal=True), 18)
        with self.assertRaises(ParseError):
            integer("one two")

    def test_durations(self):
        for text, seconds in (
            ("ten minutes", 600), ("1 hour and 30 minutes", 5400),
            ("one hour thirty minutes", 5400), ("half an hour", 1800),
            ("one and a half hours", 5400), ("an hour and a half", 5400),
            ("a minute", 60), ("one minute and thirty seconds", 90),
            ("0.5 minutes", 30), ("two days", 172800),
        ):
            self.assertEqual(duration_seconds(text), seconds, text)

    def test_bad_durations(self):
        for text in ("zero minutes", "-10 minutes", "minus ten minutes",
                     "ten", "ten minutes nonsense", "one hour and thirty",
                     "one minute two minutes", "eight days"):
            with self.assertRaises(ParseError, msg=text):
                duration_seconds(text)


class DateTests(unittest.TestCase):
    def test_named_dates(self):
        for text in ("december eighteenth", "December 18th", "18 December",
                     "the eighteenth of december", "december eighteenth twenty twenty six"):
            self.assertEqual(parse_date(text, NOW.date()), date(2026, 12, 18), text)
        self.assertEqual(parse_date("january first", NOW.date()), date(2027, 1, 1))
        self.assertEqual(parse_date("september seventeenth", NOW.date()), NOW.date())
        self.assertEqual(parse_date("january first 2026", NOW.date()), date(2026, 1, 1))

    def test_leap_day(self):
        self.assertEqual(parse_date("february twenty ninth", NOW.date()), date(2028, 2, 29))
        with self.assertRaises(ParseError):
            parse_date("february twenty ninth 2027", NOW.date())

    def test_invalid_dates(self):
        for text in ("february thirtieth", "april thirty first", "03/04", "december",
                     "december eighteenth bananas"):
            with self.assertRaises(ParseError, msg=text):
                parse_date(text, NOW.date())

    def test_relative_dates(self):
        self.assertEqual(parse_date("tomorrow", NOW.date()), date(2026, 9, 18))
        self.assertEqual(parse_date("friday", NOW.date()), date(2026, 9, 18))
        self.assertEqual(parse_date("next thursday", NOW.date()), date(2026, 9, 24))
        self.assertEqual(parse_date("in two weeks", NOW.date()), date(2026, 10, 1))


class ClockTests(unittest.TestCase):
    def test_times(self):
        for text, expected in (
            ("five thirty pm", (17, 30)), ("5:30 PM", (17, 30)),
            ("five thirty p m", (17, 30)), ("seventeen thirty", (17, 30)),
            ("12 am", (0, 0)), ("12 pm", (12, 0)),
            ("noon", (12, 0)), ("midnight", (0, 0)),
            ("05:00", (5, 0)), ("five oh five pm", (17, 5)),
            ("half past five pm", (17, 30)), ("quarter to twelve am", (23, 45)),
        ):
            self.assertEqual(parse_clock(text), expected, text)

    def test_ambiguous_and_invalid(self):
        for text in ("five", "five thirty", "twenty five pm", "17:99", "25:00"):
            with self.assertRaises(ParseError, msg=text):
                parse_clock(text)

    def test_until_clock(self):
        seconds, target = until_clock("five pm", NOW)
        self.assertEqual(target, datetime(2026, 9, 17, 17))
        self.assertEqual(seconds, 7200)
        _, target = until_clock("two pm", NOW)
        self.assertEqual(target, datetime(2026, 9, 18, 14))
        with self.assertRaises(ParseError):
            until_clock("today at two pm", NOW)


class CommandsAndTimerTests(unittest.TestCase):
    def setUp(self):
        self.tick = 1000.0
        self.manager = CalendarTimers(clock=lambda: self.tick)

    def test_screenshot_questions(self):
        self.assertIn("September 17", self.manager.handle("what's the date today", NOW))
        self.assertIn("Thursday", self.manager.handle("what day of the week is it", NOW))
        self.assertIn("92 calendar days", self.manager.handle(
            "how many days until december eighteenth", NOW))

    def test_clock_questions(self):
        self.assertIn("120 minutes", self.manager.handle("how many minutes until five pm", NOW))
        self.assertIn("2 hours", self.manager.handle("how long until five pm", NOW))
        self.assertIn("tomorrow", self.manager.handle("how long until tomorrow at five pm", NOW))
        self.assertIn("AM or PM", self.manager.handle("how many minutes until five", NOW))

    def test_date_questions(self):
        self.assertIn("Friday", self.manager.handle("what day is december eighteenth", NOW))
        self.assertIn("October 1", self.manager.handle("what date will it be in two weeks", NOW))
        self.assertIn("October 1", self.manager.handle("what day is it in two weeks", NOW))

    def test_date_question_without_it(self):
        for phrase in (
            "what date will be in ten weeks",
            "what date will it be in ten weeks",
            "what date is in ten weeks",
            "what date is it in ten weeks",
            "what day will be in ten weeks",
        ):
            self.assertIn("November 26", self.manager.handle(phrase, NOW), phrase)

    def test_timer_expiry_once(self):
        result = self.manager.handle("set a timer for ten seconds", NOW)
        self.assertIn("Timer 1", result)
        self.assertFalse(self.manager.has_due())
        self.tick += 10
        self.assertTrue(self.manager.has_due())
        self.assertEqual(self.manager.take_alerts(), ["Timer 1 has finished, sir."])
        self.assertEqual(self.manager.take_alerts(), [])
        self.assertFalse(self.manager.has_due())

    def test_multiple_and_cancel(self):
        self.manager.handle("set a timer for two minutes called pasta", NOW)
        self.manager.handle("set a timer for one minute", NOW)
        self.assertIn("more than one", self.manager.handle("cancel timer", NOW))
        self.assertEqual(len(self.manager.timers), 2)
        self.assertIn("pasta is cancelled", self.manager.handle("cancel timer pasta", NOW))
        self.assertIn("Timer 2", self.manager.handle("list timers", NOW))
        self.assertIn("cancelled", self.manager.handle("cancel timer two", NOW))
        self.assertFalse(self.manager.timers)

    def test_time_remaining_and_cancel_all(self):
        self.manager.handle("set a timer for thirty seconds", NOW)
        self.tick += 10
        self.assertIn("20 seconds", self.manager.handle("how much time is left on my timer", NOW))
        self.manager.handle("cancel all timers", NOW)
        self.assertFalse(self.manager.timers)

    def test_unrelated_commands_and_bad_input(self):
        self.assertIsNone(self.manager.handle("open notepad", NOW))
        result = self.manager.handle("set a timer for one hour and thirty", NOW)
        self.assertIn("duration", result)
        self.assertFalse(self.manager.timers)


if __name__ == "__main__":
    unittest.main()
