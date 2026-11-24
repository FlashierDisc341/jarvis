"""Mocked/pure tests: no app focus changes, volume changes, microphone or real timers."""
from decimal import Decimal
import unittest
from unittest.mock import patch

from jarvis_actions import Actions, Result, Target
from jarvis_time import CalendarTimers, ParseError
from jarvis_math import calculator, number
from jarvis_desktop import volume_command


class CalculatorTests(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(number("negative five"), Decimal("-5"))
        self.assertEqual(number("two point zero five"), Decimal("2.05"))
        self.assertEqual(number("one and a half"), Decimal("1.5"))

    def test_arithmetic(self):
        for phrase, expected in (
            ("calculate twelve times eight", "96"),
            ("what is fifteen percent of eighty", "12"),
            ("calculate five divided by two", "2.5"),
            ("calculate 0.1 plus 0.2", "0.3"),
            ("calculate negative five minus negative two", "-3"),
            ("calculate 2+3", "5"),
        ):
            self.assertIn("is " + expected, calculator(phrase), phrase)
        self.assertIn("undefined", calculator("calculate two divided by zero"))
        self.assertIn("approximately", calculator("calculate one divided by three"))

    def test_conversions(self):
        self.assertIn("25.4 centimetres", calculator("convert ten inches to centimetres"))
        self.assertIn("0 celsius", calculator("convert thirty two fahrenheit to celsius"))
        self.assertIn("2.204", calculator("convert one kilogram to pounds"))
        self.assertIn("different quantities", calculator("convert five metres to kilograms"))
        self.assertIn("below absolute zero", calculator("convert negative one kelvin to celsius"))

    def test_not_arbitrary_execution(self):
        self.assertIsNone(calculator("open chrome"))
        self.assertNotIn("is 14", calculator("calculate two plus three times four"))
        self.assertIn("Try calculate", calculator("calculate __import__('os').system('whoami')"))


class VolumeParsingTests(unittest.TestCase):
    def test_volume_phrases(self):
        for phrase, expected in (
            ("volume up", ("up", 5.0)),
            ("turn the volume down", ("down", 5.0)),
            ("volume up by ten percent", ("up", 10.0)),
            ("volume up by ten", ("up", 10.0)),
            ("set volume to thirty percent", ("set", 30.0)),
            ("volume 25", ("set", 25.0)),
            ("mute", ("mute", None)),
            ("unmute", ("unmute", None)),
            ("what is the volume", ("status", None)),
        ):
            self.assertEqual(volume_command(phrase), expected, phrase)
        self.assertIsNone(volume_command("mute microphone"))
        self.assertIsNone(volume_command("open chrome"))

    def test_invalid_volume(self):
        for phrase in ("set volume to 101 percent", "set volume to negative five percent"):
            with self.assertRaises(ParseError):
                volume_command(phrase)


class DispatcherTests(unittest.TestCase):
    def setUp(self):
        self.actions = Actions.__new__(Actions)
        self.actions.calendar = CalendarTimers()
        self.actions.last_reply = "The time is five PM, sir."
        self.actions.apps = []
        self.actions.blocked = set()
        self.actions.catalogue_error = None
        self.state = {"id": "FAKE_DEVICE", "name": "Mock speaker", "level": 30.0, "muted": False}

    def test_repeat_does_not_repeat_action(self):
        pending = (Target("life_confirm", "Notepad", "[]"),)
        with patch.object(self.actions, "lifecycle_action") as destructive:
            result = self.actions.handle("repeat that", pending)
            self.assertEqual(result.reply, self.actions.last_reply)
            self.assertEqual(result.choices, pending)
            destructive.assert_not_called()

    def test_normal_volume_dispatch_mocked(self):
        with patch("jarvis_desktop.inspect_volume", return_value=self.state):
            with patch("jarvis_desktop.apply_volume", return_value="mock reply") as apply:
                result = self.actions.handle("set volume to forty percent")
                apply.assert_called_once_with("set", 40.0, self.state)
                self.assertEqual(result.reply, "mock reply")

    def test_loud_volume_confirmation(self):
        with patch("jarvis_desktop.inspect_volume", return_value=self.state):
            with patch("jarvis_desktop.apply_volume", return_value="mock reply") as apply:
                result = self.actions.handle("set volume to ninety percent")
                self.assertEqual(result.choices[0].kind, "volume_confirm")
                apply.assert_not_called()
                self.actions.handle("yes", result.choices)
                apply.assert_not_called()
                self.actions.handle("confirm volume", result.choices)
                apply.assert_called_once_with("set", 90.0, self.state)

    def test_window_dispatch_mocked(self):
        window = {"hwnd": 123, "pid": 456, "title": "Mock"}
        group = {"name": "Google Chrome", "aliases": ["chrome"],
                 "windows": [window], "processes": []}
        with patch("jarvis_processes.discover", return_value=[group]):
            with patch("jarvis_desktop.window_action", return_value="mock window") as move:
                result = self.actions.handle("switch to chrome")
                move.assert_called_once_with("switch", group, window)
                self.assertEqual(result.reply, "mock window")

    def test_multiple_windows_ask(self):
        group = {"name": "Notepad", "aliases": ["notepad"], "processes": [],
                 "windows": [
                     {"hwnd": 1, "pid": 4, "title": "One"},
                     {"hwnd": 2, "pid": 4, "title": "Two"},
                 ]}
        with patch("jarvis_processes.discover", return_value=[group]):
            with patch("jarvis_desktop.window_action") as move:
                result = self.actions.handle("minimize notepad")
                self.assertEqual(len(result.choices), 2)
                move.assert_not_called()

    def test_help_and_no_playback(self):
        with patch("builtins.print"):
            self.assertIn("command list", self.actions.handle("what can you do").reply)
        self.assertIn("not configured", self.actions.handle("next track").reply)
        self.assertIn("not configured", self.actions.handle("pause music").reply)

    def test_calc_and_suffix_date_fix_kept(self):
        self.assertIn("is 96", self.actions.handle("calculate twelve times eight").reply)
        self.assertNotIn("not configured", self.actions.handle("what date will be in ten weeks").reply)


if __name__ == "__main__":
    unittest.main()
