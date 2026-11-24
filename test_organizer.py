"""Uses temporary SQLite files, fake clocks and mocked application/audio actions.
Does NOT open the microphone, load a model, control apps or touch your real notebook.
Windows-only dispatcher/frontend tests also exercise the installed integration.
"""
from datetime import datetime
import os
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from jarvis_dialogue import command_for_transcript, remove_wake_marker
from jarvis_organizer import (
    Draft, Organizer, Store, StoreError, reminder_request, schedule,
    unique_local_timestamp,
)
from jarvis_time import ParseError


class TempOrganizer(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "organizer.sqlite3"
        self.now = datetime(2026, 9, 18, 12, 0).timestamp()
        self.org = Organizer(self.path, clock=lambda: self.now)

    def tearDown(self):
        self.org.close()
        self.temp.cleanup()

    def restart(self):
        self.org.close()
        self.org = Organizer(self.path, clock=lambda: self.now)

    def save_reminder(self, command="remind me in two minutes to Stretch"):
        proposal = self.org.handle(command)
        self.assertEqual(proposal.draft.kind, "organizer_reminder_save", proposal.text)
        saved = self.org.handle("save reminder", proposal.draft)
        self.assertIsNone(saved.draft)
        self.assertIn("is saved", saved.text)
        return self.org.store.get_reminder(1)


class NoteTests(TempOrganizer):
    def test_two_step_dictation_confirmation_and_restart(self):
        question = self.org.handle("take a note")
        self.assertEqual(question.draft.kind, "organizer_dictate")
        proposal = self.org.handle("Bring the Blue Folder.", question.draft)
        self.assertEqual(self.org.store.notes_page(), [])
        not_saved = self.org.handle("yes", proposal.draft)
        self.assertEqual(not_saved.draft, proposal.draft)
        self.assertEqual(self.org.store.notes_page(), [])
        self.org.handle("save note", proposal.draft)
        self.restart()
        self.assertEqual(self.org.store.get_note(1)["body"], "Bring the Blue Folder.")
        self.assertIn("Blue Folder", self.org.handle("read my notes").text)

    def test_inline_and_change_note(self):
        proposal = self.org.handle("take a note: Buy Blue Paint")
        self.assertEqual(proposal.draft.data["body"], "Buy Blue Paint")
        retry = self.org.handle("change note", proposal.draft)
        second = self.org.handle("Buy Red Paint", retry.draft)
        self.org.handle("save note", second.draft)
        self.assertEqual(self.org.store.get_note(1)["body"], "Buy Red Paint")

    def test_unsaved_drafts_do_not_persist(self):
        self.org.handle("take a note: Unsaved text")
        self.restart()
        self.assertEqual(self.org.store.notes_page(), [])

    def test_literal_sql_like_text(self):
        body = "Robert'); DROP TABLE notes; --"
        proposal = self.org.handle("note that " + body)
        self.org.handle("save note", proposal.draft)
        self.assertEqual(self.org.store.get_note(1)["body"], body)
        self.org.store.add_note("Still here", self.now)
        self.assertEqual(len(self.org.store.notes_page()), 2)

    def test_archive_restore_preserve_text(self):
        self.org.store.add_note("Keep this", self.now)
        proposal = self.org.handle("delete note one")
        self.assertIn("not permanently delete", proposal.text)
        self.assertEqual(self.org.store.get_note(1)["archived"], 0)
        self.org.handle("confirm archive", proposal.draft)
        self.assertEqual(self.org.store.notes_page(), [])
        self.assertEqual(self.org.store.get_note(1)["body"], "Keep this")
        restore = self.org.handle("restore note one")
        self.org.handle("confirm restore", restore.draft)
        self.assertEqual(self.org.store.get_note(1)["archived"], 0)

    def test_stale_confirmation_and_length(self):
        self.org.store.add_note("One", self.now)
        proposal = self.org.handle("archive note one")
        self.org.store.change_note(1, 1, True)
        reply = self.org.handle("confirm archive", proposal.draft)
        self.assertIn("changed", reply.text)
        reply = self.org.handle("note that " + "x" * 401)
        self.assertIsNone(reply.draft)
        self.assertIn("400", reply.text)

    def test_pagination_ids_are_stable(self):
        for index in range(5):
            self.org.store.add_note(f"Item {index}", self.now)
        first = self.org.handle("read my notes")
        self.assertIn("read notes after 3", first.text)
        second = self.org.handle("read notes after three")
        self.assertIn("Note 4", second.text)
        self.assertIn("Note 5", second.text)
        self.assertNotIn("Note 1", second.text)


class ReminderTests(TempOrganizer):
    def test_schedule_confirmation_before_persistence(self):
        proposal = self.org.handle("remind me tomorrow at six PM to Practise Guitar")
        self.assertIn("2026", proposal.text)
        self.assertIn("UTC", proposal.text)
        self.assertEqual(self.org.store.reminders_page(), [])
        self.org.handle("yes", proposal.draft)
        self.assertEqual(self.org.store.reminders_page(), [])
        self.org.handle("save reminder", proposal.draft)
        self.restart()
        row = self.org.store.get_reminder(1)
        self.assertEqual(row["body"], "Practise Guitar")
        self.assertEqual(datetime.fromtimestamp(row["due"]), datetime(2026, 9, 19, 18, 0))

    def test_due_after_restart_acknowledged_only_once(self):
        row = self.save_reminder()
        self.now = row["due"] + 10
        self.restart()
        self.assertTrue(self.org.has_due())
        rows = self.org.due_rows()
        with patch("builtins.print"):
            self.assertIn("Missed reminder 1", self.org.alert_text(rows, self.now))
        # Generating a readback is not a successful announcement.
        self.assertIsNone(self.org.store.get_reminder(1)["announced_at"])
        self.org.acknowledge(rows)
        self.assertFalse(self.org.has_due())
        self.restart()
        self.assertFalse(self.org.has_due())
        self.assertIn("not a completion confirmation", self.org.handle("read reminder one").text)

    def test_cancel_and_restore(self):
        self.save_reminder()
        proposal = self.org.handle("cancel reminder one")
        self.assertEqual(self.org.store.get_reminder(1)["cancelled"], 0)
        self.org.handle("confirm cancel", proposal.draft)
        self.now += 600
        self.assertFalse(self.org.has_due())
        restore = self.org.handle("restore reminder one")
        self.assertIn("time has passed", restore.text)
        self.org.handle("confirm restore", restore.draft)
        self.assertTrue(self.org.has_due())

    def test_confirmation_expired_before_save(self):
        proposal = self.org.handle("remind me in ten seconds to Stretch")
        self.now += 20
        reply = self.org.handle("save reminder", proposal.draft)
        self.assertIn("passed before confirmation", reply.text)
        self.assertEqual(self.org.store.reminders_page(), [])

    def test_missing_am_pm_and_past_time(self):
        for command in (
            "remind me tomorrow at six to Stretch",
            "remind me today at ten AM to Stretch",
            "remind me yesterday at six PM to Stretch",
        ):
            with self.subTest(command=command):
                reply = self.org.handle(command)
                self.assertIsNone(reply.draft)
                self.assertEqual(self.org.store.reminders_page(), [])

    def test_quarter_to_and_task_containing_to(self):
        due, body = reminder_request("remind me tomorrow at quarter to six PM to Go to the Shop", self.now)
        self.assertEqual(datetime.fromtimestamp(due), datetime(2026, 9, 19, 17, 45))
        self.assertEqual(body, "Go to the Shop")

    def test_relative_and_named_date(self):
        self.assertEqual(schedule("in two minutes", self.now), self.now + 120)
        self.assertEqual(datetime.fromtimestamp(schedule("on September twentieth at noon", self.now)),
                         datetime(2026, 9, 20, 12, 0))
        self.assertEqual(datetime.fromtimestamp(schedule("at ten AM", self.now)),
                         datetime(2026, 9, 19, 10, 0))

    def test_backlog_summary_does_not_claim_all_text_spoken(self):
        for index in range(5):
            self.org.store.add_reminder(f"Task {index}", self.now + 30, "test label", self.now)
        self.org.refresh_deadline()
        self.now += 60
        rows = self.org.due_rows()
        with patch("builtins.print"):
            text = self.org.alert_text(rows, self.now)
        self.assertIn("2 more due reminders", text)
        self.assertIn("listed in the terminal", text)
        self.org.acknowledge(rows)
        self.assertFalse(self.org.has_due())


class ParsingAndStorageTests(unittest.TestCase):
    def test_wake_and_literal_note_content(self):
        self.assertEqual(remove_wake_marker("Jarvis, open Jarvis."), "open jarvis")
        self.assertEqual(remove_wake_marker("Read my notes, Jarvis."), "read my notes")
        self.assertIsNone(remove_wake_marker("we told Jarvis about the note"))
        self.assertEqual(command_for_transcript("Jarvis, take a note: Blue Folder"),
                         "take a note: Blue Folder")
        pending = (SimpleNamespace(kind="organizer_dictate"),)
        self.assertEqual(command_for_transcript("Jarvis is a character.", True, pending),
                         "Jarvis is a character.")
        self.assertEqual(command_for_transcript("Open Chrome.", True, pending), "Open Chrome.")
        self.assertIsNone(command_for_transcript("Open Chrome.", False, ()))
        self.assertEqual(command_for_transcript("Save note.", True, ()), "Save note")

    def test_clock_gap_and_fold_rejection_logic(self):
        target = Mock()
        target.replace.side_effect = [SimpleNamespace(timestamp=lambda: 100),
                                      SimpleNamespace(timestamp=lambda: 200)]
        with patch("jarvis_organizer.datetime") as local:
            local.fromtimestamp.return_value = target
            with self.assertRaises(ParseError):
                unique_local_timestamp(target)
        target = Mock()
        target.replace.return_value = SimpleNamespace(timestamp=lambda: 100)
        with patch("jarvis_organizer.datetime") as local:
            local.fromtimestamp.return_value = object()
            with self.assertRaises(ParseError):
                unique_local_timestamp(target)

    def test_corrupt_database_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.sqlite3"
            before = b"this is not a SQLite database"
            path.write_bytes(before)
            with self.assertRaises(StoreError):
                Store(path)
            self.assertEqual(path.read_bytes(), before)

    def test_unrecognized_database_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "other.sqlite3"
            db = sqlite3.connect(path)
            db.execute("CREATE TABLE unrelated (id INTEGER)")
            db.commit()
            db.close()
            with self.assertRaises(StoreError):
                Store(path)
            db = sqlite3.connect(path)
            self.assertIsNotNone(db.execute(
                "SELECT name FROM sqlite_master WHERE name='unrelated'"
            ).fetchone())
            db.close()


@unittest.skipUnless(os.name == "nt", "Windows dispatcher integration")
class DispatcherTests(TempOrganizer):
    def setUp(self):
        super().setUp()
        from jarvis_actions import Actions
        from jarvis_time import CalendarTimers
        self.actions = Actions.__new__(Actions)  # No Start-app scan or live actions.
        self.actions.organizer = self.org
        self.actions.calendar = CalendarTimers()
        self.actions.last_reply = ""
        self.actions.apps = []
        self.actions.blocked = set()
        self.actions.catalogue_error = None

    def test_dictated_commands_are_never_executed(self):
        for content in ("Open Chrome", "Close Notepad", "Set volume to ninety percent",
                        "End the task Notepad"):
            with self.subTest(content=content):
                first = self.actions.handle("take a note")
                with patch.object(self.actions, "open_request") as launch, \
                     patch.object(self.actions, "lifecycle_request") as close, \
                     patch.object(self.actions, "volume_request") as volume:
                    result = self.actions.handle(content, first.choices)
                    self.assertEqual(result.choices[0].kind, "organizer_note_save")
                    launch.assert_not_called()
                    close.assert_not_called()
                    volume.assert_not_called()
                self.actions.handle("cancel", result.choices)
                self.assertEqual(self.org.store.notes_page(), [])

    def test_existing_choice_answers_still_select(self):
        from jarvis_actions import Target, Result
        choices = (Target("app", "One", "mock"), Target("app", "Two", "mock2"))
        with patch.object(self.actions, "launch", return_value=Result("mock")) as launch:
            self.actions.handle("one", choices)
            launch.assert_called_once_with(choices[0])

    def test_organizer_save_requires_its_own_confirmation(self):
        proposal = self.actions.handle("take a note: Blue Folder")
        reply = self.actions.handle("confirm end task", proposal.choices)
        self.assertEqual(reply.choices, proposal.choices)
        self.assertEqual(self.org.store.notes_page(), [])
        saved = self.actions.handle("save note", reply.choices)
        self.assertFalse(saved.choices)
        self.assertEqual(self.org.store.get_note(1)["body"], "Blue Folder")

    def test_cancel_and_stop_do_not_save(self):
        proposal = self.actions.handle("take a note: Temporary")
        self.assertFalse(self.actions.handle("cancel", proposal.choices).choices)
        self.assertTrue(self.actions.handle("stop listening", proposal.choices).stop)
        self.assertEqual(self.org.store.notes_page(), [])


@unittest.skipUnless(os.name == "nt", "Windows frontend integration")
class FrontendTests(TempOrganizer):
    def run_frontend(self, fail_alert=False):
        import jarvis_whisper as frontend
        from jarvis_actions import Result
        fake_actions = SimpleNamespace(
            organizer=self.org,
            calendar=SimpleNamespace(take_alerts=lambda: [], timers={}),
            has_due=self.org.has_due,
            handle=lambda command, pending: Result("Stopping, sir.", stop=True),
            close=Mock(),
            last_reply="",
        )
        listener = SimpleNamespace(
            capture=lambda *args, **kwargs: SimpleNamespace(kind="audio", audio=None),
            transcribe=lambda audio: "Jarvis, stop listening.",
        )
        piper = SimpleNamespace(PiperVoice=SimpleNamespace(load=lambda path: object()))
        calls = []

        def speech(voice, text):
            calls.append(text)
            if fail_alert and len(calls) == 2:
                raise RuntimeError("simulated speech failure")

        with patch.object(frontend, "WhisperListener", return_value=listener), \
             patch.object(frontend, "VOICE_PATH") as voice_path, \
             patch.object(frontend, "speak", side_effect=speech), \
             patch.object(frontend.winsound, "Beep"), \
             patch("jarvis_actions.Actions", return_value=fake_actions), \
             patch.dict("sys.modules", {"piper": piper}), \
             patch("builtins.print"):
            voice_path.is_file.return_value = True
            frontend.main()
        fake_actions.close.assert_called_once()
        return calls

    def test_startup_announces_saved_overdue_reminder(self):
        row = self.save_reminder()
        self.now = row["due"] + 10
        self.restart()
        calls = self.run_frontend()
        self.assertTrue(any("Stretch" in text for text in calls))
        self.assertIsNotNone(self.org.store.get_reminder(1)["announced_at"])

    def test_failed_speech_keeps_reminder_due(self):
        row = self.save_reminder()
        self.now = row["due"] + 10
        with self.assertRaises(RuntimeError):
            self.run_frontend(fail_alert=True)
        self.assertIsNone(self.org.store.get_reminder(1)["announced_at"])
        self.assertTrue(self.org.has_due())


if __name__ == "__main__":
    unittest.main(verbosity=2)
