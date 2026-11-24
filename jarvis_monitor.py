"""Read-only PC reports. No process management, shell, file scan or telemetry log.
Uses the already-installed psutil dependency. Metrics are snapshots, not diagnoses.
"""
import math
import os
from pathlib import PureWindowsPath
import re
import time

import psutil

SAMPLE_SECONDS = 1.0
SCAN_SECONDS = 2.5
MAX_PROCESSES = 4096


class MonitorError(RuntimeError):
    pass


def request(command):
    text = " ".join(command.casefold().replace("\u2019", "'").strip(" .,?!").split())
    text = re.sub(r"\bwhat(?:'s|s)\b", "what is", text)
    text = re.sub(r"\bc[ .]*p[ .]*u\b", "cpu", text)
    if text in {"system report", "system status", "pc status", "pc report", "resource report"}:
        return "system", None
    if text in {"cpu usage", "what is the cpu usage", "what is my cpu usage",
                "how much cpu am i using", "how much cpu is being used"}:
        return "cpu", None
    if text in {"ram usage", "memory usage", "what is my ram usage",
                "what is the ram usage", "how much ram is being used",
                "how much ram am i using", "how much ram is available"}:
        return "ram", None
    if text in {"disk space", "storage report", "how much disk space is free",
                "how much free disk space do i have", "how much storage is left",
                "how much disk space do i have"}:
        return "disk", None
    if text in {"what is using the most cpu", "which app is using the most cpu",
                "what is using my cpu", "top cpu usage"}:
        return "top_cpu", None
    match = re.fullmatch(r"how much (?:memory|ram) (?:is|does) (.+?) (?:using|use)", text)
    if not match:
        match = re.fullmatch(r"(?:memory|ram) usage (?:for|of)\s+(.+)", text)
    if match:
        return "app_memory", match.group(1).strip()
    return None


def byte_label(value):
    if value < 0 or not math.isfinite(value):
        raise MonitorError("Invalid memory/disk reading")
    if value >= 1024 ** 3:
        return f"{value / 1024 ** 3:.2f} gibibytes"
    return f"{value / 1024 ** 2:.1f} mebibytes"


def windows_drive(environ=None):
    environ = os.environ if environ is None else environ
    drive = PureWindowsPath(environ.get("SystemRoot", "")).drive
    if not re.fullmatch(r"[a-zA-Z]:", drive):
        raise MonitorError("Windows did not supply a valid SystemRoot drive")
    return drive.upper() + "\\"


def cpu_share(before, after, elapsed, logical_cpus):
    if elapsed <= 0 or logical_cpus < 1 or after < before:
        raise MonitorError("The CPU sample changed or is invalid")
    value = (after - before) / elapsed / logical_cpus * 100
    if not math.isfinite(value) or value < 0:
        raise MonitorError("Invalid CPU reading")
    return min(value, 100.0)


def group_label(executable, friendly, catalogue):
    path = PureWindowsPath(executable)
    name = friendly.get(path.name.casefold(), path.stem)
    aliases = [path.stem, path.name, name]
    for app_name, app_id in catalogue:
        app_id = app_id.replace("/", "\\").casefold()
        candidate = executable.replace("/", "\\").casefold()
        matches = (candidate.endswith(app_id.split("}", 1)[1])
                   if app_id.startswith("{") and "}\\" in app_id else candidate == app_id)
        if matches:
            aliases.append(app_name)
            name = app_name
    if name == "FL Studio":
        year = re.search(r"FL Studio\s+(\d{2,4})", executable, re.I)
        if year:
            name += " " + year.group(1)
    aliases.append(name)
    return name, aliases


class Backend:
    def __init__(self, clock=time.monotonic, sleep=time.sleep):
        self.clock = clock
        self.sleep = sleep
        self._scope = None

    def scope(self):
        if self._scope is None:
            from jarvis_processes import session_id
            me = psutil.Process()
            self._scope = (me.username().casefold(), session_id(me.pid))
        return self._scope

    def same_session(self, process):
        from jarvis_processes import session_id
        user, session = self.scope()
        return process.username().casefold() == user and session_id(process.pid) == session

    def inventory(self, catalogue=()):
        from jarvis_processes import APP_NAMES
        self.scope()  # Fail explicitly if the caller's own scope cannot be checked.
        groups = {}
        skipped = 0
        truncated = False
        end = self.clock() + SCAN_SECONDS
        seen = 0
        for process in psutil.process_iter():
            seen += 1
            if seen > MAX_PROCESSES or self.clock() >= end:
                truncated = True
                break
            if process.pid <= 4:
                continue
            try:
                if not self.same_session(process):
                    continue
                # Fresh object prevents using process_iter's cached identity metadata.
                fresh = psutil.Process(process.pid)
                if not self.same_session(fresh):
                    continue
                created = fresh.create_time()
                executable = fresh.exe()
                if not executable:
                    skipped += 1
                    continue
                path = executable.replace("/", "\\").casefold()
                name, aliases = group_label(executable, APP_NAMES, catalogue)
                group = groups.setdefault(path, {
                    "path": path, "name": name, "aliases": aliases, "items": [],
                })
                group["items"].append({"pid": fresh.pid, "created": created, "path": path})
            except (psutil.Error, OSError):
                skipped += 1
        return {"groups": sorted(groups.values(), key=lambda g: (g["name"].casefold(), g["path"])),
                "skipped": skipped, "truncated": truncated}

    def checked(self, item):
        process = psutil.Process(item["pid"])
        if (process.create_time() != item["created"]
                or process.exe().replace("/", "\\").casefold() != item["path"]
                or not self.same_session(process)):
            raise MonitorError("That process exited or changed identity")
        return process

    def rss(self, item):
        process = self.checked(item)
        value = process.memory_info().rss
        # Recheck PID identity after the reading, not just before.
        self.checked(item)
        return value

    def cpu_counter(self, item):
        process = self.checked(item)
        value = process.cpu_times()
        stamp = self.clock()
        self.checked(item)
        return value.user + value.system, stamp

    def logical_cpus(self):
        value = psutil.cpu_count(logical=True)
        if not value or value < 1:
            raise MonitorError("The logical CPU count is unavailable")
        return value

    def total_cpu(self):
        return psutil.cpu_percent(interval=SAMPLE_SECONDS)

    def ram(self):
        return psutil.virtual_memory()

    def disk(self):
        root = windows_drive()
        return root, psutil.disk_usage(root)


class Monitor:
    def __init__(self, backend=None):
        self.backend = backend if backend is not None else Backend()

    def groups(self, catalogue=()):
        return self.backend.inventory(catalogue)

    def cpu_report(self):
        value = self.backend.total_cpu()
        if not math.isfinite(value) or not 0 <= value <= 100:
            raise MonitorError("Invalid total CPU reading")
        return f"Total CPU usage averaged {value:.1f} percent over a one second sample"

    def ram_report(self):
        memory = self.backend.ram()
        if not 0 <= memory.available <= memory.total or memory.total <= 0:
            raise MonitorError("Invalid RAM reading")
        used = 100 * (memory.total - memory.available) / memory.total
        return (f"RAM usage is {used:.1f} percent, with {byte_label(memory.available)} available "
                f"out of {byte_label(memory.total)}")

    def disk_report(self):
        root, usage = self.backend.disk()
        return (f"The Windows {root[:1]} drive has {byte_label(usage.free)} free "
                f"out of {byte_label(usage.total)}")

    def basic_report(self, kind):
        readers = {
            "system": (self.cpu_report, self.ram_report, self.disk_report),
            "cpu": (self.cpu_report,), "ram": (self.ram_report,), "disk": (self.disk_report,),
        }
        # Individual failures must not turn missing information into zero usage.
        lines = []
        labels = {self.cpu_report: "CPU", self.ram_report: "RAM", self.disk_report: "disk"}
        for reader in readers[kind]:
            try:
                lines.append(reader())
            except (psutil.Error, OSError, MonitorError, ValueError) as error:
                label = labels[reader]
                print(label + " report error:", type(error).__name__, error, flush=True)
                lines.append(f"The {label} reading is unavailable")
        return ". ".join(lines) + ", sir."

    def memory_report(self, path, catalogue=()):
        inventory = self.groups(catalogue)
        group = next((g for g in inventory["groups"] if g["path"] == path), None)
        if group is None:
            return ("That app is no longer in the readable process list. "
                    "It may have closed or could not be inspected, sir.")
        total = 0
        count = 0
        skipped = 0
        end = self.backend.clock() + SCAN_SECONDS
        for item in group["items"]:
            if self.backend.clock() >= end:
                skipped += len(group["items"]) - count - skipped
                break
            try:
                value = self.backend.rss(item)
                if value < 0 or not math.isfinite(value):
                    raise MonitorError("Invalid process memory reading")
                total += value
                count += 1
            except (psutil.Error, OSError, MonitorError):
                skipped += 1
        if not count:
            return "I could not read memory for any of that app's captured processes, sir."
        partial = bool(skipped or inventory["truncated"] or inventory["skipped"])
        print(f"APP MEMORY: {group['name']}; RSS={total}; readable={count}; "
              f"measurement_skips={skipped}; discovery_skips={inventory['skipped']}; "
              f"scan_truncated={inventory['truncated']}", flush=True)
        prefix = "The partial reading for" if partial else "The reading for"
        return (f"{prefix} {group['name']} is a combined working set of about {byte_label(total)} "
                f"across {count} readable processes from the same executable. "
                "Shared memory can be counted more than once, sir.")

    def top_cpu_report(self, catalogue=()):
        inventory = self.groups(catalogue)
        cpus = self.backend.logical_cpus()
        baseline = []
        skipped = 0
        limited = inventory["truncated"]
        end = self.backend.clock() + SCAN_SECONDS
        for group in inventory["groups"]:
            for item in group["items"]:
                if self.backend.clock() >= end:
                    limited = True
                    break
                try:
                    counter, stamp = self.backend.cpu_counter(item)
                    baseline.append((group, item, counter, stamp))
                except (psutil.Error, OSError, MonitorError):
                    skipped += 1
            if limited and self.backend.clock() >= end:
                break
        if not baseline:
            return "I could not obtain a CPU baseline for readable processes in your Windows session, sir."
        self.backend.sleep(SAMPLE_SECONDS)
        totals = {}
        measurements = 0
        elapsed_values = []
        end = self.backend.clock() + SCAN_SECONDS
        for group, item, counter, stamp in baseline:
            if self.backend.clock() >= end:
                limited = True
                break
            try:
                current, now = self.backend.cpu_counter(item)
                percent = cpu_share(counter, current, now - stamp, cpus)
                total = totals.setdefault(group["path"], {"name": group["name"], "percent": 0.0, "count": 0})
                total["percent"] += percent
                total["count"] += 1
                elapsed_values.append(now - stamp)
                measurements += 1
            except (psutil.Error, OSError, MonitorError):
                skipped += 1
        if not measurements:
            return "The captured CPU samples became unavailable. Please ask again, sir."
        ranked = sorted(totals.values(), key=lambda row: (-row["percent"], row["name"].casefold()))
        for row in ranked:
            # Different per-process measurement endpoints can introduce small jitter.
            row["percent"] = min(row["percent"], 100.0)
        print(f"CPU SAMPLE: logical_cpus={cpus}; measured={measurements}; "
              f"seconds={min(elapsed_values):.3f}..{max(elapsed_values):.3f}; "
              f"measurement_skips={skipped}; discovery_skips={inventory['skipped']}; "
              f"limited={limited}", flush=True)
        for row in ranked[:10]:
            print(f"{row['name']}: {row['percent']:.3f}% total CPU; "
                  f"{row['count']} measured processes", flush=True)
        if not ranked or ranked[0]["percent"] < 0.05:
            return ("No measured executable group exceeded 0.05 percent of total CPU capacity "
                    "in this short sample. Unreadable and other-session processes are excluded, sir.")
        leaders = "; ".join(f"{row['name']}, about {row['percent']:.1f} percent"
                            for row in ranked[:3] if row["percent"] >= 0.05)
        qualifier = " This is a partial sample." if skipped or inventory["skipped"] or limited else ""
        return (f"Among readable processes in your Windows session, the largest CPU users "
                f"in this short sample were {leaders}. Percentages use total logical CPU capacity."
                f"{qualifier} Unreadable and other-session processes are excluded, sir.")


if __name__ == "__main__":
    print("Read-only system report. No applications or settings are changed.")
    print(Monitor().basic_report("system"))
