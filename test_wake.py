"""Wake-word parsing only. Does not load speech models or open the microphone."""
import unittest
from jarvis import remove_wake_marker


class WakeTests(unittest.TestCase):
    def test_prefix(self):
        self.assertEqual(remove_wake_marker("jarvis what day of the week is it"),
                         "what day of the week is it")

    def test_suffix(self):
        self.assertEqual(remove_wake_marker("what day of the week is it jarvis"),
                         "what day of the week is it")

    def test_hey_jarvis(self):
        self.assertEqual(remove_wake_marker("hey jarvis what time is it"),
                         "what time is it")
        self.assertEqual(remove_wake_marker("what time is it hey jarvis"),
                         "what time is it")

    def test_punctuation(self):
        self.assertEqual(remove_wake_marker("What time is it, Jarvis?"),
                         "what time is it")
        self.assertEqual(remove_wake_marker("Jarvis, what time is it?"),
                         "what time is it")

    def test_standalone(self):
        self.assertEqual(remove_wake_marker("jarvis"), "")
        self.assertEqual(remove_wake_marker("hey jarvis"), "")

    def test_not_addressed(self):
        self.assertIsNone(remove_wake_marker("what time is it"))
        self.assertIsNone(remove_wake_marker("i told jarvis what time it was"))
        self.assertIsNone(remove_wake_marker("what time is it myjarvis"))
        self.assertIsNone(remove_wake_marker("jarvisian what time is it"))

    def test_preserve_jarvis_folder_target(self):
        self.assertEqual(remove_wake_marker("jarvis open jarvis"), "open jarvis")
        self.assertEqual(remove_wake_marker("open jarvis jarvis"), "open jarvis")

    def test_keep_time_colon(self):
        self.assertEqual(remove_wake_marker("how many minutes until 5:30 pm jarvis"),
                         "how many minutes until 5:30 pm")


if __name__ == "__main__":
    unittest.main()
