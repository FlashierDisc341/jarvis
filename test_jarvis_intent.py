r"""Offline routing regression tests. No microphone, Ollama or Windows actions.
Run: .\.venv-whisper\Scripts\python.exe -B .\test_jarvis_intent.py
"""
import ast
from dataclasses import dataclass
import json
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch

import jarvis_intent as ji
from jarvis_dialogue import command_for_transcript


@dataclass(frozen=True)
class Result:
    reply: str
    choices: tuple = ()
    stop: bool = False
    handled: bool = True


@dataclass(frozen=True)
class Choice:
    kind: str


class FakeActions:
    def __init__(self):
        self.calls = []

    def handle(self, command, pending=()):
        self.calls.append((command, pending))
        if pending:
            return Result("native pending", tuple(pending))
        if command.startswith(("open ", "end the task ", "set volume ", "set a timer ")):
            if command.startswith("end the task "):
                return Result("confirm end task", (Choice("life_confirm"),))
            if command == "set volume to 90 percent":
                return Result("confirm volume", (Choice("volume_confirm"),))
            return Result("native action")
        if command in {"what time is it", "what is the date", "take a note"}:
            return Result("native reply")
        if command in {"stop listening", "quit", "exit", "goodbye"}:
            return Result("stopped", stop=True)
        if command in {"cancel", "no"}:
            return Result("cancelled")
        return Result("That command is not configured, sir.", handled=False)


class RoutingTests(unittest.TestCase):
    def router(self, intent="time", argument="", enabled=True):
        actions = FakeActions()
        model_calls = []

        def model(command):
            model_calls.append(command)
            return {"intent": intent, "argument": argument}

        return actions, model_calls, ji.IntentRouter(actions, Result, enabled, model)

    def test_exact_command_bypasses_model(self):
        actions, calls, router = self.router()
        result = router.handle("open Notepad")
        self.assertTrue(result.handled)
        self.assertEqual(calls, [])
        self.assertEqual(len(actions.calls), 1)

    def test_readonly_paraphrase_uses_validated_command(self):
        actions, calls, router = self.router()
        router.handle("could you tell me the current hour")
        self.assertEqual(len(calls), 1)
        self.assertEqual(actions.calls[-1][0], "what time is it")

    def test_mutation_requires_specific_confirmation(self):
        actions, calls, router = self.router("open", "Notepad")
        result = router.handle("get Notepad up for me")
        self.assertEqual(len(actions.calls), 1)
        self.assertEqual(result.choices[0].kind, "intent_confirm")
        unchanged = router.handle("yes", result.choices)
        self.assertEqual(unchanged.choices, result.choices)
        self.assertEqual(len(actions.calls), 1)
        router.handle("confirm interpretation", result.choices)
        self.assertEqual(actions.calls[-1][0], "open Notepad")
        self.assertEqual(len(calls), 1)

    def test_short_confirm_accepts_only_pending_interpretation(self):
        actions, calls, router = self.router("open", "Notepad")
        first = router.handle("get Notepad up")
        router.handle("confirm", first.choices)
        self.assertEqual(actions.calls[-1][0], "open Notepad")
        self.assertEqual(len(calls), 1)

    def test_partial_confirmation_is_not_accepted(self):
        for phrase in ("interpretation", "firm interpretation", "confirm confirm interpretation"):
            with self.subTest(phrase=phrase):
                actions, calls, router = self.router("open", "Notepad")
                first = router.handle("get Notepad up")
                result = router.handle(phrase, first.choices)
                self.assertEqual(result.choices, first.choices)
                self.assertEqual(len(actions.calls), 1)

    def test_confirm_without_pending_has_no_saved_action(self):
        actions, calls, router = self.router("unknown")
        result = router.handle("confirm")
        self.assertEqual(actions.calls, [("confirm", ())])
        self.assertFalse(result.choices)

    def test_short_confirm_preserves_native_confirmation(self):
        actions, calls, router = self.router("end_task", "Notepad")
        first = router.handle("force terminate Notepad")
        result = router.handle("confirm", first.choices)
        self.assertEqual(result.choices[0].kind, "life_confirm")

    def test_interpretation_can_be_cancelled(self):
        actions, calls, router = self.router("open", "Notepad")
        result = router.handle("get Notepad up")
        self.assertFalse(router.handle("cancel", result.choices).choices)
        self.assertEqual(len(actions.calls), 1)

    def test_stop_during_interpretation_confirmation(self):
        actions, calls, router = self.router("open", "Notepad")
        result = router.handle("get Notepad up")
        self.assertTrue(router.handle("stop listening", result.choices).stop)

    def test_force_end_keeps_native_confirmation(self):
        actions, calls, router = self.router("end_task", "Notepad")
        first = router.handle("force terminate Notepad")
        second = router.handle("confirm interpretation", first.choices)
        self.assertEqual(second.choices[0].kind, "life_confirm")
        router.handle("confirm end task", second.choices)
        self.assertEqual(len(calls), 1)
        self.assertEqual(actions.calls[-1][0], "confirm end task")

    def test_loud_volume_keeps_native_confirmation(self):
        actions, calls, router = self.router("volume_set", "90")
        first = router.handle("make the output ninety percent")
        second = router.handle("confirm interpretation", first.choices)
        self.assertEqual(second.choices[0].kind, "volume_confirm")

    def test_all_native_pending_bypass_ollama(self):
        for kind in ("organizer_dictate", "organizer_note_save",
                     "organizer_reminder_save", "life_confirm",
                     "volume_confirm", "app", "desktop_window", "monitor_memory"):
            with self.subTest(kind=kind):
                actions, calls, router = self.router("open", "Notepad")
                pending = (Choice(kind),)
                result = router.handle("some text", pending)
                self.assertEqual(calls, [])
                self.assertEqual(result.choices, pending)
                self.assertEqual(actions.calls[-1], ("some text", pending))

    def test_unknown_executes_nothing_else(self):
        actions, calls, router = self.router("unknown")
        result = router.handle("will I need an umbrella")
        self.assertFalse(result.handled)
        self.assertEqual(len(actions.calls), 1)

    def test_disabled_model_is_not_called(self):
        actions, calls, router = self.router(enabled=False)
        router.handle("tell me the current hour please")
        self.assertEqual(calls, [])

    def test_invalid_model_output_is_not_executed(self):
        actions, calls, router = self.router("shell", "powershell")
        result = router.handle("unrecognized")
        self.assertIn("invalid", result.reply)
        self.assertEqual(len(actions.calls), 1)

    def test_interpreter_failure_is_contained(self):
        actions = FakeActions()

        def broken(text):
            raise OSError("offline")

        result = ji.IntentRouter(actions, Result, interpreter=broken).handle("unrecognized")
        self.assertIn("unavailable", result.reply)
        self.assertEqual(len(actions.calls), 1)

    def test_due_alert_skips_interpreter(self):
        actions, calls, router = self.router()
        result = router.handle("unrecognized", interrupted=lambda: True)
        self.assertEqual(result.reply, "")
        self.assertEqual(calls, [])

    def test_due_alert_cancels_inflight_result(self):
        actions = FakeActions()
        entered, release = threading.Event(), threading.Event()

        def slow(text):
            entered.set()
            release.wait(1)
            return {"intent": "open", "argument": "Notepad"}

        router = ji.IntentRouter(actions, Result, interpreter=slow, timeout=1)
        result = router.handle("unrecognized", interrupted=entered.is_set)
        self.assertEqual(result.reply, "")
        release.set()
        router.worker.join(1)
        self.assertEqual(len(actions.calls), 1)

    def test_timeout_never_executes_late_result(self):
        actions = FakeActions()
        release = threading.Event()

        def slow(text):
            release.wait(1)
            return {"intent": "open", "argument": "Notepad"}

        router = ji.IntentRouter(actions, Result, interpreter=slow, timeout=0.02)
        result = router.handle("unrecognized")
        self.assertIn("unavailable", result.reply)
        release.set()
        router.worker.join(1)
        self.assertEqual(len(actions.calls), 1)

    def test_alert_cancels_confirmed_interpretation(self):
        actions, calls, router = self.router("open", "Notepad")
        first = router.handle("get Notepad up")
        result = router.handle("confirm interpretation", first.choices, lambda: True)
        self.assertEqual(result.reply, "")
        self.assertEqual(len(actions.calls), 1)


class ValidationTests(unittest.TestCase):
    def test_fixed_intents(self):
        for intent, (command, needs_argument, confirmation) in ji.COMMANDS.items():
            if not needs_argument:
                with self.subTest(intent=intent):
                    plan = ji.validate_plan({"intent": intent, "argument": ""})
                    self.assertEqual(plan.command, command)
                    self.assertEqual(plan.confirmation, confirmation)

    def test_reject_invalid_schema_and_commands(self):
        values = [
            [], None, {}, {"intent": "time"},
            {"intent": "time", "argument": "", "command": "open Notepad"},
            {"intent": "shell", "argument": "calc.exe"},
            {"intent": False, "argument": ""},
            {"intent": "volume_set", "argument": 30},
            {"intent": "time", "argument": "tomorrow"},
            {"intent": "unknown", "argument": "open Notepad"},
            {"intent": "open", "argument": ""},
        ]
        for value in values:
            with self.subTest(value=value), self.assertRaises(ji.IntentError):
                ji.validate_plan(value)

    def test_targets_are_names_not_shell_or_paths(self):
        for name in (r"C:\Windows\notepad.exe", "https://example.com", "foo;bar",
                     "foo & bar", "$(cmd)", "../test", "--help", "it", "x\nopen Notepad"):
            with self.subTest(name=name), self.assertRaises(ji.IntentError):
                ji.validate_plan({"intent": "open", "argument": name})

    def test_named_targets(self):
        for name in ("Notepad", "FL Studio 2025", "Visual Studio Code", "downloads"):
            self.assertEqual(
                ji.validate_plan({"intent": "open", "argument": name}).command,
                "open " + name,
            )

    def test_volume_bounds(self):
        for argument in ("101", "-1", "10.5", "loud", "9" * 200):
            with self.subTest(argument=argument), self.assertRaises(ji.IntentError):
                ji.validate_plan({"intent": "volume_set", "argument": argument})
        with self.assertRaises(ji.IntentError):
            ji.validate_plan({"intent": "volume_up", "argument": "0"})
        self.assertEqual(ji.validate_plan({"intent": "volume_set", "argument": "0"}).command,
                         "set volume to 0 percent")

    def test_timer_uses_existing_parser(self):
        plan = ji.validate_plan({"intent": "timer_start", "argument": "two minutes"})
        self.assertEqual(plan.command, "set a timer for 2 minutes")
        for text in ("later", "0 seconds", "8 days", "two minutes called pasta"):
            with self.subTest(text=text), self.assertRaises(ji.IntentError):
                ji.validate_plan({"intent": "timer_start", "argument": text})

    def test_valid_ollama_response(self):
        value = {"intent": "time", "argument": ""}
        response = {"done": True, "message": {"content": json.dumps(value)}}
        with patch.object(ji, "request_json", return_value=response) as request:
            self.assertEqual(ji.understand("tell me the hour"), value)
            path, body = request.call_args.args
            self.assertEqual(path, "/api/chat")
            self.assertFalse(body["stream"])
            self.assertEqual(body["format"], ji.SCHEMA)
            self.assertEqual(body["model"], "qwen2.5:3b")

    def test_invalid_ollama_envelope(self):
        for response in ([], {}, {"done": False},
                         {"done": True, "message": {"content": "no"}},
                         {"done": True, "done_reason": "length", "message": {}},
                         {"done": True, "message": {"content": "{}", "tool_calls": [1]}}):
            with self.subTest(response=response):
                with patch.object(ji, "request_json", return_value=response):
                    with self.assertRaises(ji.IntentError):
                        ji.understand("hello")

    def test_wake_phrase_is_still_required(self):
        self.assertIsNone(command_for_transcript("open Notepad"))
        self.assertEqual(command_for_transcript("Jarvis, open Notepad"), "open Notepad")
        self.assertEqual(command_for_transcript("open Notepad, Jarvis"), "open Notepad")

    def test_note_dictation_preserves_literal_jarvis(self):
        self.assertEqual(
            command_for_transcript("Jarvis, open Chrome", True, (Choice("organizer_dictate"),)),
            "Jarvis, open Chrome",
        )



class RequestGuardTests(unittest.TestCase):
    BLOCKED = (
        "don't open Chrome", "do not open Chrome", "DON’T open Chrome",
        "never close Notepad", "open Chrome and close Discord",
        "open Chrome, then close Discord", "open Chrome; close Discord",
        "open Chrome & close Discord", "open Chrome or Firefox",
        "open Chrome\nclose Discord", "close Chrome without opening Firefox",
        "if I ask, open Chrome", "don't stop listening",
    )

    def test_guard_blocks_before_any_model_call(self):
        for text in self.BLOCKED:
            with self.subTest(text=text):
                with patch.object(ji, "request_json") as request:
                    self.assertEqual(ji.understand(text),
                                     {"intent": "unknown", "argument": ""})
                    request.assert_not_called()

    def test_guard_blocks_before_native_actions_too(self):
        for text in self.BLOCKED:
            with self.subTest(text=text):
                actions = FakeActions()
                with patch.object(ji, "understand") as model:
                    result = ji.IntentRouter(actions, Result).handle(text)
                    self.assertIn("Nothing was executed", result.reply)
                    self.assertEqual(actions.calls, [])
                    model.assert_not_called()

    def test_pending_dictation_bypasses_guard(self):
        actions = FakeActions()
        pending = (Choice("organizer_dictate"),)
        with patch.object(ji, "understand") as model:
            text = "don't open Chrome and close Discord"
            ji.IntentRouter(actions, Result).handle(text, pending)
            self.assertEqual(actions.calls, [(text, pending)])
            model.assert_not_called()

    def test_pending_confirmation_does_not_execute_negative(self):
        actions = FakeActions()
        router = ji.IntentRouter(actions, Result, interpreter=lambda text:
                                 {"intent": "open", "argument": "Notepad"})
        first = router.handle("bring up Notepad for me")
        count = len(actions.calls)
        result = router.handle("don't confirm", first.choices)
        self.assertEqual(result.choices, first.choices)
        self.assertEqual(len(actions.calls), count)

    def test_normal_requests_pass_gate(self):
        for text in ("open Notepad", "close Discord", "stop listening",
                     "how hard is my processor working",
                     "how much memory am I using", "what's eating up my processor",
                     "bring up Notepad for me", "set volume to 30 percent"):
            with self.subTest(text=text):
                self.assertIsNone(ji.request_rejection(text))


if __name__ == "__main__":
    unittest.main(verbosity=2)
