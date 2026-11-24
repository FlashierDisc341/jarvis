"""Mocked read-only report tests. No microphone, model, live process sampling or files."""
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import psutil
from jarvis_monitor import (
    Backend, Monitor, MonitorError, byte_label, cpu_share, group_label, request, windows_drive,
)


class FakeBackend:
    def __init__(self):
        self.now = 0.0
        self.calls = {}
        self.bad_rss = set()
        self.bad_cpu = set()
        self.truncated = False
        self.discovery_skips = 0
        self.rows = [
            {"path": "chrome-path", "name": "Google Chrome", "aliases": ["chrome"],
             "items": [{"pid": 10}, {"pid": 11}]},
            {"path": "obs-path", "name": "OBS Studio", "aliases": ["obs"],
             "items": [{"pid": 20}]},
        ]

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds

    def inventory(self, catalogue=()):
        return {"groups": self.rows, "skipped": self.discovery_skips, "truncated": self.truncated}

    def logical_cpus(self):
        return 4

    def cpu_counter(self, item):
        pid = item["pid"]
        if pid in self.bad_cpu:
            raise psutil.AccessDenied(pid)
        calls = self.calls.get(pid, 0)
        self.calls[pid] = calls + 1
        return 100.0 + calls * {10: 1.0, 11: 0.5, 20: 0.25}[pid], self.now

    def rss(self, item):
        if item["pid"] in self.bad_rss:
            raise psutil.AccessDenied(item["pid"])
        return {10: 100, 11: 50, 20: 25}[item["pid"]] * 1024 ** 2

    def total_cpu(self):
        return 25.0

    def ram(self):
        return SimpleNamespace(total=16 * 1024 ** 3, available=10 * 1024 ** 3)

    def disk(self):
        return "D:\\", SimpleNamespace(total=500 * 1024 ** 3, free=200 * 1024 ** 3)


class ParserTests(unittest.TestCase):
    def test_commands_and_unrelated_commands(self):
        cases = {
            "system report": ("system", None),
            "PC status": ("system", None),
            "CPU usage": ("cpu", None),
            "RAM usage": ("ram", None),
            "how much disk space is free": ("disk", None),
            "what's using the most CPU?": ("top_cpu", None),
            "what is using the most C P U": ("top_cpu", None),
            "how much memory is Chrome using?": ("app_memory", "chrome"),
            "how much RAM does Discord use": ("app_memory", "discord"),
            "memory usage for FL Studio 2026": ("app_memory", "fl studio 2026"),
        }
        for text, expected in cases.items():
            self.assertEqual(request(text), expected, text)
        for text in ("open Chrome", "close Notepad", "take a note", "set volume to 30",
                     "what's 3 to the power of 7", "cancel reminder one", "status report",
                     "what is the GPU temperature"):
            self.assertIsNone(request(text), text)

    def test_units_and_drive(self):
        self.assertEqual(byte_label(1024 ** 3), "1.00 gibibytes")
        self.assertEqual(byte_label(100 * 1024 ** 2), "100.0 mebibytes")
        self.assertEqual(windows_drive({"SystemRoot": r"D:\Windows"}), "D:\\")
        with self.assertRaises(MonitorError):
            windows_drive({})
        with self.assertRaises(MonitorError):
            windows_drive({"SystemRoot": r"\\server\share\Windows"})

    def test_cpu_normalization_and_invalid_counter(self):
        self.assertEqual(cpu_share(10, 11, 1, 4), 25)
        self.assertEqual(cpu_share(10, 12, 2, 4), 25)
        for args in ((10, 9, 1, 4), (10, 11, 0, 4), (10, 11, 1, 0)):
            with self.assertRaises(MonitorError):
                cpu_share(*args)

    def test_friendly_name_and_install_version(self):
        name, aliases = group_label(
            r"C:\Apps\FL Studio 2026\FL64.exe", {"fl64.exe": "FL Studio"}, ()
        )
        self.assertEqual(name, "FL Studio 2026")
        self.assertIn("FL64.exe", aliases)
        name, aliases = group_label(
            r"C:\Apps\Example\thing.exe", {},
            (("Example Editor", r"C:\Apps\Example\thing.exe"),),
        )
        self.assertEqual(name, "Example Editor")


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend()
        self.monitor = Monitor(self.backend)

    def test_system_report(self):
        reply = self.monitor.basic_report("system")
        self.assertIn("25.0 percent", reply)
        self.assertIn("37.5 percent", reply)
        self.assertIn("10.00 gibibytes available", reply)
        self.assertIn("Windows D drive", reply)
        self.assertIn("200.00 gibibytes free", reply)

    def test_failure_does_not_invent_zero_or_drop_other_readings(self):
        with patch.object(self.backend, "total_cpu", side_effect=psutil.AccessDenied()), \
             patch("builtins.print"):
            reply = self.monitor.basic_report("system")
        self.assertIn("CPU reading is unavailable", reply)
        self.assertIn("RAM usage", reply)
        self.assertIn("Windows D drive", reply)

    def test_memory_combines_same_executable_only(self):
        with patch("builtins.print"):
            reply = self.monitor.memory_report("chrome-path")
        self.assertIn("150.0 mebibytes", reply)
        self.assertIn("2 readable processes", reply)
        self.assertIn("Shared memory can be counted more than once", reply)

    def test_partial_and_unavailable_memory(self):
        self.backend.bad_rss = {11}
        with patch("builtins.print"):
            reply = self.monitor.memory_report("chrome-path")
        self.assertIn("partial reading", reply)
        self.assertIn("100.0 mebibytes", reply)
        self.backend.bad_rss = {10, 11}
        self.assertIn("could not read memory", self.monitor.memory_report("chrome-path"))
        self.assertIn("no longer", self.monitor.memory_report("missing"))

    def test_discovery_limits_are_not_complete_app_totals(self):
        self.backend.truncated = True
        with patch("builtins.print"):
            self.assertIn("partial reading", self.monitor.memory_report("chrome-path"))

    def test_cpu_ranking_aggregates_and_normalizes(self):
        with patch("builtins.print"):
            reply = self.monitor.top_cpu_report()
        self.assertIn("Google Chrome, about 37.5 percent", reply)
        self.assertIn("OBS Studio, about 6.2 percent", reply)
        self.assertIn("your Windows session", reply)
        self.assertIn("total logical CPU capacity", reply)
        self.assertEqual(self.backend.now, 1.0)

    def test_unreadable_cpu_is_not_reported_as_idle(self):
        self.backend.bad_cpu = {10, 11, 20}
        self.assertIn("could not obtain a CPU baseline", self.monitor.top_cpu_report())

    def test_partial_cpu_sample_is_labelled(self):
        self.backend.bad_cpu = {20}
        with patch("builtins.print"):
            reply = self.monitor.top_cpu_report()
        self.assertIn("partial sample", reply)


class IdentityTests(unittest.TestCase):
    def test_pid_reuse_is_rejected(self):
        backend = Backend()
        process = SimpleNamespace(create_time=lambda: 200, exe=lambda: r"C:\Apps\chrome.exe")
        item = {"pid": 10, "created": 100, "path": r"c:\apps\chrome.exe"}
        with patch("jarvis_monitor.psutil.Process", return_value=process), \
             patch.object(backend, "same_session", return_value=True):
            with self.assertRaises(MonitorError):
                backend.checked(item)

    def test_changed_path_or_session_is_rejected(self):
        backend = Backend()
        item = {"pid": 10, "created": 100, "path": r"c:\apps\chrome.exe"}
        for exe, permitted in ((r"C:\Other\chrome.exe", True), (r"C:\Apps\chrome.exe", False)):
            process = SimpleNamespace(create_time=lambda: 100, exe=lambda: exe)
            with patch("jarvis_monitor.psutil.Process", return_value=process), \
                 patch.object(backend, "same_session", return_value=permitted):
                with self.assertRaises(MonitorError):
                    backend.checked(item)


@unittest.skipUnless(os.name == "nt", "Windows dispatcher integration")
class DispatcherTests(unittest.TestCase):
    def setUp(self):
        from jarvis_actions import Actions
        from jarvis_time import CalendarTimers
        self.actions = Actions.__new__(Actions)
        self.actions._monitor = Monitor(FakeBackend())
        self.actions.apps = []
        self.actions.blocked = set()
        self.actions.catalogue_error = None
        self.actions.calendar = CalendarTimers()
        self.actions.last_reply = ""

    def test_system_report_does_not_launch_or_close(self):
        with patch.object(self.actions, "open_request") as launch, \
             patch.object(self.actions, "lifecycle_request") as close, \
             patch.object(self.actions, "volume_request") as volume:
            reply = self.actions.handle("system report")
            self.assertIn("CPU usage", reply.reply)
            launch.assert_not_called()
            close.assert_not_called()
            volume.assert_not_called()

    def test_app_memory_and_ambiguity(self):
        with patch("builtins.print"):
            reply = self.actions.handle("how much memory is Chrome using")
        self.assertIn("150.0 mebibytes", reply.reply)
        self.actions._monitor.backend.rows.append({
            "path": "chrome-other", "name": "Google Chrome", "aliases": ["chrome"],
            "items": [{"pid": 30}],
        })
        with patch("builtins.print"):
            choices = self.actions.handle("how much memory is Chrome using")
        self.assertEqual(len(choices.choices), 2)
        self.assertTrue(all(item.kind == "monitor_memory" for item in choices.choices))
        with patch("builtins.print"):
            selected = self.actions.handle("one", choices.choices)
        self.assertIn("150.0 mebibytes", selected.reply)

    def test_report_replaces_old_force_confirmation_without_executing(self):
        from jarvis_actions import Target
        pending = (Target("life_confirm", "Notepad", "[]"),)
        with patch.object(self.actions, "lifecycle_action") as force:
            result = self.actions.handle("system report", pending)
            self.assertFalse(result.choices)
            force.assert_not_called()

    def test_dictation_still_routes_to_organizer_not_monitor(self):
        from jarvis_actions import Target, Result
        pending = (Target("organizer_dictate", "Organizer", "{}"),)
        with patch.object(self.actions, "organizer_action", return_value=Result("note draft")) as notes, \
             patch.object(self.actions, "monitor_request") as report:
            result = self.actions.handle("system report", pending)
            self.assertEqual(result.reply, "note draft")
            notes.assert_called_once()
            report.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
