"""Run with your venv Python. Only matching tests; nothing opens or closes."""
import unittest
from unittest.mock import patch

from jarvis_actions import Actions, Target, choose, key, Result
from jarvis_time import CalendarTimers


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.choices = (
            Target("app", "FL Studio 2025", "fake25"),
            Target("app", "FL Studio 2026", "fake26"),
        )
        self.actions = Actions.__new__(Actions)
        self.actions.calendar = CalendarTimers()
        self.actions.apps = list(self.choices)
        self.actions.blocked = set()
        self.actions.catalogue_error = None

    def test_year_answers(self):
        for phrase in ("2026", "twenty twenty six", "two thousand twenty six",
                       "two thousand and twenty six", "FL Studio 2026"):
            self.assertEqual(choose(phrase, self.choices), self.choices[1])
        self.assertIsNone(choose("FL Studio", self.choices))
        self.assertEqual(choose("second", self.choices), self.choices[1])
        self.assertEqual(key("note pad"), key("Notepad"))

    def test_open_partial_year(self):
        result = self.actions.handle("open twenty twenty six")
        self.assertEqual(result.choices, (self.choices[1],))
        with patch.object(self.actions, "launch", return_value=Result("mock")) as launch:
            self.actions.handle("twenty twenty six", self.choices)
            launch.assert_called_once_with(self.choices[1])

    def test_close_and_end_task_are_different(self):
        for phrase, force in (
            ("close notepad", False), ("end notepad", False),
            ("end the task notepad", True), ("end task, notepad", True),
        ):
            with patch.object(self.actions, "lifecycle_request",
                              return_value=Result("mock")) as action:
                self.actions.handle(phrase)
                if force:
                    action.assert_called_once_with("notepad", force=True)
                else:
                    action.assert_called_once_with("notepad")

    def test_force_requires_exact_confirmation(self):
        pending = (Target("life_confirm", "Notepad", "[]"),)
        with patch.object(self.actions, "lifecycle_action",
                          return_value=Result("mock")) as action:
            for answer in ("yes", "one", "notepad", "confirm"):
                self.assertEqual(self.actions.handle(answer, pending).choices, pending)
            action.assert_not_called()
            self.assertEqual(self.actions.handle("cancel", pending).choices, ())
            action.assert_not_called()
            self.actions.handle("confirm end task", pending)
            action.assert_called_once_with(pending[0])

    def test_new_request_discards_confirmation(self):
        pending = (Target("life_confirm", "Notepad", "[]"),)
        with patch.object(self.actions, "lifecycle_action") as action:
            with patch.object(self.actions, "open_request",
                              return_value=Result("mock")) as open_request:
                self.actions.handle("open chrome", pending)
                open_request.assert_called_once_with("chrome")
                action.assert_not_called()


if __name__ == "__main__":
    unittest.main()
